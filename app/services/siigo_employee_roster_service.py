from __future__ import annotations

from .employee_service import get_employee, import_siigo_employee, normalize_document
from ..integrations.siigo.client import get_siigo_client


def list_active_person_third_parties(max_pages: int = 100, page_size: int = 100) -> list[dict]:
    """Consulta terceros persona activos desde la API pública de Siigo.

    Importante: Siigo API pública expone /customers (clientes/terceros), pero no
    publica un endpoint que identifique cuáles terceros pertenecen al módulo
    Nómina Electrónica. Por eso este listado se usa como candidatos y requiere
    confirmación humana para marcar trabajadores.
    """
    client = get_siigo_client()
    out: list[dict] = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        response = client.customers(page=page, page_size=page_size)
        if isinstance(response, dict):
            rows = response.get("results") or []
            pagination = response.get("pagination") or {}
        elif isinstance(response, list):
            rows = response
            pagination = {}
        else:
            rows = []
            pagination = {}

        for item in rows:
            if not isinstance(item, dict):
                continue
            if item.get("active") is False:
                continue
            if str(item.get("person_type") or "").strip().lower().strip("'") != "person":
                continue
            document = normalize_document(item.get("identification"))
            if not document or document in seen:
                continue
            seen.add(document)
            local = get_employee(document)
            normalized = dict(item)
            normalized["document"] = document
            normalized["already_employee"] = bool(local and local.get("in_payroll", True))
            normalized["local_status"] = (local or {}).get("status", "")
            normalized["local_salary_base"] = (local or {}).get("salary_base", "")
            out.append(normalized)

        total = int(pagination.get("total_results") or 0)
        current_page_size = int(pagination.get("page_size") or page_size)
        if not rows:
            break
        if total and page * current_page_size >= total:
            break
        if len(rows) < page_size and not total:
            break

    return sorted(out, key=lambda x: _display_name(x).lower())


def _display_name(item: dict) -> str:
    value = item.get("name")
    if isinstance(value, list):
        return " ".join(str(x or "").strip() for x in value if str(x or "").strip())
    return str(value or item.get("commercial_name") or item.get("identification") or "").strip()


def import_selected_employees(candidates: list[dict], documents: list[str]) -> list[dict]:
    wanted = {normalize_document(x) for x in documents if normalize_document(x)}
    by_doc = {normalize_document(x.get("identification")): x for x in candidates}
    imported = []
    for document in sorted(wanted):
        item = by_doc.get(document)
        if not item:
            continue
        imported.append(import_siigo_employee(item))
    return imported


def refresh_confirmed_roster_from_siigo() -> dict:
    """Actualiza automáticamente desde Siigo los trabajadores YA confirmados.

    No convierte todos los terceros persona en empleados: la API pública de Siigo
    no expone una bandera de 'empleado de nómina'. La pertenencia a nómina queda
    en el maestro; en cada corrida se refrescan nombre/estado/id Siigo por cédula.
    """
    from .employee_service import list_active_employees, import_siigo_employee

    roster = list_active_employees()
    if not roster:
        return {"ok": False, "reason": "NO_CONFIRMED_ROSTER", "updated": 0, "missing": []}

    client = get_siigo_client()
    updated = 0
    missing = []
    for employee in roster:
        document = normalize_document(employee.get("document"))
        if not document:
            continue
        response = client.customers(identification=document, page=1, page_size=10)
        rows = response.get("results") if isinstance(response, dict) else response
        rows = rows if isinstance(rows, list) else []
        exact = next((x for x in rows if normalize_document(x.get("identification")) == document), None)
        if exact:
            # Conserva salario/banco/grupo locales y refresca identidad/vínculo Siigo.
            import_siigo_employee(exact)
            updated += 1
        else:
            missing.append(document)
    return {"ok": True, "updated": updated, "missing": missing, "total": len(roster)}
