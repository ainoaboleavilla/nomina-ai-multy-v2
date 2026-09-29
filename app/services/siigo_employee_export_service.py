from __future__ import annotations

import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from openpyxl import load_workbook

from .employee_service import normalize_document, upsert_employee, get_employee


def _norm(value) -> str:
    text = str(value or "").strip().lower()
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    for ch in "./_-º°":
        text = text.replace(ch, " ")
    return " ".join(text.split())


def _find_header(headers: list[str], candidates: list[str]) -> int | None:
    normalized = [_norm(x) for x in headers]
    wanted = {_norm(x) for x in candidates}
    for i, h in enumerate(normalized):
        if h in wanted:
            return i
    for i, h in enumerate(normalized):
        if any(w and w in h for w in wanted):
            return i
    return None


def _parse_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if _norm(text) in {"no aplica", "n/a", "na", "indefinido"}:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _is_active(start, end, reference: date) -> bool:
    if start and start > reference:
        return False
    if end and end < reference:
        return False
    return True


def import_siigo_employee_export(path: Path, reference_date: date | None = None) -> dict:
    """Importa el reporte REAL `Exportar lista de empleados` de Siigo Nómina.

    Conserva el histórico de contratos y marca `in_payroll` únicamente para los
    contratos vigentes en la fecha de corte. Las novedades nunca crean la planta.
    """
    reference_date = reference_date or date.today()
    wb = load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("El archivo de empleados de Siigo está vacío.")

    header_row = None
    mapping = None
    for idx, row in enumerate(rows[:20]):
        headers = [str(x or "") for x in row]
        doc_i = _find_header(headers, ["No Identificación", "identificacion", "numero de documento", "documento", "cedula"])
        name_i = _find_header(headers, ["Nombre", "empleado", "nombre empleado", "nombre completo"])
        if doc_i is not None and name_i is not None:
            header_row = idx
            mapping = {
                "doc": doc_i,
                "name": name_i,
                "contract": _find_header(headers, ["No contrato", "numero contrato", "contrato"]),
                "start": _find_header(headers, ["Fecha inicio", "fecha de inicio"]),
                "end": _find_header(headers, ["Fecha fin", "fecha de fin", "fecha final"]),
                "salary": _find_header(headers, ["Sueldo", "salario base", "salario"]),
                "contract_type": _find_header(headers, ["Tipo de contrato", "T. Contrato"]),
            }
            break
    if header_row is None or mapping is None:
        raise ValueError("No reconocí el reporte de Siigo. Debe contener Nombre y No Identificación.")

    imported_docs = set()
    active_docs = set()
    contracts = 0
    future = 0
    ended = 0
    now = datetime.now(timezone.utc).isoformat()

    # Si una persona aparece en más de un contrato, se considera activa si al menos
    # uno de sus contratos está vigente en la fecha de corte.
    parsed = []
    for row in rows[header_row + 1:]:
        doc = normalize_document(row[mapping["doc"]] if mapping["doc"] < len(row) else "")
        if not doc:
            continue
        name = str(row[mapping["name"]] or "").strip()
        start = _parse_date(row[mapping["start"]]) if mapping["start"] is not None else None
        end = _parse_date(row[mapping["end"]]) if mapping["end"] is not None else None
        active = _is_active(start, end, reference_date)
        if start and start > reference_date:
            future += 1
        elif end and end < reference_date:
            ended += 1
        parsed.append((row, doc, name, start, end, active))
        imported_docs.add(doc)
        if active:
            active_docs.add(doc)
        contracts += 1

    # Importa/actualiza una ficha por documento usando preferentemente el contrato vigente.
    best = {}
    for item in parsed:
        row, doc, name, start, end, active = item
        if doc not in best or (active and not best[doc][5]):
            best[doc] = item

    for doc, item in best.items():
        row, _, name, start, end, active = item
        existing = get_employee(doc) or {}
        salary = existing.get("salary_base") or ""
        if mapping["salary"] is not None and row[mapping["salary"]] not in (None, ""):
            salary = row[mapping["salary"]]
        payload = {
            "document": doc,
            "name": name or existing.get("name") or doc,
            "salary_base": salary,
            "payroll_group": existing.get("payroll_group") or "",
            "bank": existing.get("bank") or "",
            "bank_account": existing.get("bank_account") or "",
            "transport_allowance": existing.get("transport_allowance") or "",
            "in_payroll": doc in active_docs,
        }
        upsert_employee(payload)

    from . import employee_service as es
    data = es._read()
    for emp in data:
        doc = normalize_document(emp.get("document"))
        if doc not in imported_docs:
            continue
        row, _, _, start, end, _ = best[doc]
        emp["in_payroll"] = doc in active_docs
        emp["roster_verified"] = True
        emp["source"] = "SIIGO_NOMINA_EXPORT"
        emp["contract_number"] = str(row[mapping["contract"]] or "").strip() if mapping["contract"] is not None else ""
        emp["contract_start"] = start.isoformat() if start else ""
        emp["contract_end"] = end.isoformat() if end else ""
        emp["contract_type"] = str(row[mapping["contract_type"]] or "").strip() if mapping["contract_type"] is not None else ""
        emp["roster_reference_date"] = reference_date.isoformat()
        emp["status"] = "ACTIVO" if doc in active_docs else "INACTIVO_PERIODO"
        emp["updated_at"] = now
    es._write(data)

    return {
        "contracts": contracts,
        "unique_employees": len(imported_docs),
        "active": len(active_docs),
        "ended_contracts": ended,
        "future_contracts": future,
        "reference_date": reference_date.isoformat(),
    }
