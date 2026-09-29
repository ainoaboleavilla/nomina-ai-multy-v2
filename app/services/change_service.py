from __future__ import annotations

from pathlib import Path
from openpyxl import load_workbook
import json

BASE_DIR = Path(__file__).resolve().parent.parent.parent
AUDIT_DIR = BASE_DIR / "data" / "audit"

FILE_LABELS = {
    "calculation": "Cálculo de Nómina",
    "signature": "Formato Nómina Firma",
    "bank": "Archivo Banco",
}

def _safe(value):
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)

def _row_label(values, file_key, row_number, headers=None):
    def v(idx):
        return str(values.get(str(idx), "") or "").strip()
    header_map = {str(h.get("name", "")).strip().lower(): str(h.get("col")) for h in (headers or [])}
    # Nuevo cálculo generado desde novedades: Documento | Empleado | ...
    if "documento" in header_map and "empleado" in header_map:
        doc = str(values.get(header_map["documento"], "") or "").strip()
        full = str(values.get(header_map["empleado"], "") or "").strip()
    elif file_key == "calculation":
        full, doc = " ".join(x for x in [v(1), v(2)] if x).strip(), v(3)
    elif file_key == "signature":
        full, doc = " ".join(x for x in [v(2), v(3)] if x).strip(), v(4)
    else:
        full, doc = " ".join(x for x in [v(3), v(4)] if x).strip(), v(2)
    if doc:
        return f"{full or 'Registro'} · {doc} · fila {row_number}"
    return f"{full or 'Registro'} · fila {row_number}"

def workbook_catalog(path: Path, file_key: str):
    wb = load_workbook(path, data_only=True)
    ws = wb[wb.sheetnames[0]]

    headers = []
    for col in range(1, ws.max_column + 1):
        header = ws.cell(1, col).value
        if header not in (None, ""):
            headers.append({
                "col": col,
                "name": str(header).strip(),
            })

    rows = []
    # Los formatos reales de nómina manejan el cuerpo de empleados desde la fila 2.
    # Se limita a 100 filas para evitar incluir áreas auxiliares/plantillas vacías.
    for row in range(2, min(ws.max_row, 101) + 1):
        values = {str(h["col"]): _safe(ws.cell(row, h["col"]).value) for h in headers}
        if not any(value not in ("", None) for value in values.values()):
            continue

        # Excluir filas de totales evidentes.
        first_values = " ".join(str(x or "") for x in list(values.values())[:4]).upper()
        if "TOTAL" in first_values and not any(char.isdigit() for char in first_values):
            continue

        rows.append({
            "row": row,
            "label": _row_label(values, file_key, row, headers),
            "values": values,
        })

    return {
        "key": file_key,
        "label": FILE_LABELS[file_key],
        "sheet": ws.title,
        "headers": headers,
        "rows": rows,
    }

def build_change_catalog(output_dir: Path, generated_files: dict):
    catalog = {}
    for key in ("calculation", "signature", "bank"):
        filename = generated_files.get(key)
        if not filename:
            continue
        path = output_dir / filename
        if path.exists():
            catalog[key] = workbook_catalog(path, key)
    return catalog

def save_pending_changes(review_id: str, version: int, reviewer: str, changes: list[dict]):
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    path = AUDIT_DIR / f"pending_changes_{review_id}.json"
    payload = {
        "review_id": review_id,
        "version": version,
        "reviewer": reviewer,
        "changes": changes,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

def read_pending_changes(review_id: str):
    path = AUDIT_DIR / f"pending_changes_{review_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
