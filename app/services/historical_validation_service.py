from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from openpyxl import load_workbook

from .payroll_engine import build_inputs, calculate, as_float_dict
from .payroll_service import CALCULATED_COLUMNS, CALC_HEADERS, _norm, _read_source_rows


@dataclass
class Difference:
    file: str
    sheet: str
    row: int
    employee: str
    cedula: str
    field: str
    historical: float | None
    python: float
    delta: float | None
    status: str


def _find_payroll_sheet(wb):
    expected = {_norm(h) for h in CALC_HEADERS}
    for ws in wb.worksheets:
        headers = {_norm(ws.cell(1, c).value) for c in range(1, min(ws.max_column, 40) + 1)}
        if len(expected.intersection(headers)) >= 20:
            return ws
    return None


def validate_historical_workbook(path: Path, tolerance: float = 0.01) -> dict[str, Any]:
    """Compara un Excel histórico contra el motor Python.

    Usa dos aperturas del mismo libro:
    - data_only=False: obtiene datos fuente y políticas heredadas.
    - data_only=True: obtiene los valores históricos cacheados por Excel.

    Si el archivo no contiene valores cacheados en una celda calculada, esa celda
    se marca como NO_COMPARABLE en vez de declarar un falso error.
    """
    formulas_wb = load_workbook(path, data_only=False)
    values_wb = load_workbook(path, data_only=True)
    ws_formula = _find_payroll_sheet(formulas_wb)
    if ws_formula is None:
        raise ValueError("No se encontró una hoja con la estructura de Cálculo de Nómina.")
    ws_values = values_wb[ws_formula.title]

    # _read_source_rows usa la hoja activa si no existe el nombre histórico; para
    # libros con otra hoja, creamos el cálculo manualmente a partir de la hoja hallada.
    rows = []
    for r in range(2, ws_formula.max_row + 1):
        nombre = ws_formula.cell(r, 1).value
        cedula = ws_formula.cell(r, 3).value
        if nombre in (None, "") and cedula in (None, ""):
            continue
        # Reutilizamos el extractor del servicio cuando la hoja coincide con su selección.
        rows.append(r)

    differences: list[Difference] = []
    compared = 0
    matched = 0
    not_comparable = 0

    # Para conservar todas las políticas legacy, hacemos una copia temporal lógica:
    # si el servicio reconoce la hoja normalmente, usamos sus raw rows.
    raw_rows = _read_source_rows(path)
    raw_by_excel_row = {int(r["excel_row"]): r for r in raw_rows}

    for r in rows:
        raw = raw_by_excel_row.get(r)
        if raw is None:
            continue
        calc = as_float_dict(calculate(build_inputs(raw)))
        employee = " ".join(str(x or "").strip() for x in [raw.get("nombre"), raw.get("apellido")]).strip()
        cedula = str(raw.get("cedula") or "")

        for col, key in CALCULATED_COLUMNS.items():
            py_value = float(calc[key])
            hist = ws_values.cell(r, col).value
            if hist in (None, "") or isinstance(hist, str):
                not_comparable += 1
                continue
            try:
                hist_value = float(hist)
            except (TypeError, ValueError):
                not_comparable += 1
                continue
            compared += 1
            delta = py_value - hist_value
            if abs(delta) <= tolerance:
                matched += 1
            else:
                differences.append(Difference(
                    file=path.name,
                    sheet=ws_formula.title,
                    row=r,
                    employee=employee,
                    cedula=cedula,
                    field=key,
                    historical=hist_value,
                    python=py_value,
                    delta=delta,
                    status="DIFFERENCE",
                ))

    return {
        "file": path.name,
        "sheet": ws_formula.title,
        "employees": len(rows),
        "compared": compared,
        "matched": matched,
        "differences": len(differences),
        "not_comparable": not_comparable,
        "match_rate": round((matched / compared * 100), 2) if compared else 0.0,
        "details": [asdict(x) for x in differences],
    }


def validate_historical_folder(folder: Path, tolerance: float = 0.01) -> dict[str, Any]:
    files = sorted([*folder.rglob("*.xlsx"), *folder.rglob("*.xlsm")])
    reports = []
    errors = []
    for path in files:
        if path.name.startswith("~$"):
            continue
        try:
            reports.append(validate_historical_workbook(path, tolerance=tolerance))
        except Exception as exc:
            errors.append({"file": str(path.name), "error": str(exc)})

    total_compared = sum(x["compared"] for x in reports)
    total_matched = sum(x["matched"] for x in reports)
    return {
        "files_found": len(files),
        "files_validated": len(reports),
        "files_with_error": len(errors),
        "total_compared": total_compared,
        "total_matched": total_matched,
        "total_differences": sum(x["differences"] for x in reports),
        "global_match_rate": round(total_matched / total_compared * 100, 2) if total_compared else 0.0,
        "reports": reports,
        "errors": errors,
    }
