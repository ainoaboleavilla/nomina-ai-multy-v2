from pathlib import Path
from shutil import copy2
import re
from openpyxl import load_workbook

from .payroll_engine import RULES, as_float_dict, build_inputs, calculate

SHEET_NAME = "AGOSTO 1-15"
BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = BASE_DIR / "templates_excel"
OUTPUT_DIR = BASE_DIR / "data" / "output"

CALC_TEMPLATE = TEMPLATE_DIR / "2026_CALCULO_DE_NOMINA.xlsx"
SIGN_TEMPLATE = TEMPLATE_DIR / "FORMATO_NOMINA_FIRMA.xlsx"
BANK_TEMPLATE = TEMPLATE_DIR / "PLANTILLA_BANCO_PAGOS_NOMINA.xlsx"

CALC_HEADERS = [
    "Nombre", "Apellido", "cedula / ppt", "Salario básico",
    "Auxilio de transporte ", "Dias Laborales",
    "Días Novedad No Justificada", "Novedad Justificada", "Dias Novedad",
    "Dias Laborados", "Sub de trans quincenal ", "Salario quincenal ",
    "Total ingreso", "Dias salud", "aportes", "Prestamos ", "No salarial",
    "No salarial Quincenal", "Total deducciones", "Dispersion Banco",
    "Pago Total nomina", "# de dias Dominical", "Valor dia dominical",
    "Dominical", "Comisiones Vendedores", "Total"
]

# Columnas calculadas por Python en el archivo de cálculo procesado.
CALCULATED_COLUMNS = {
    9: "dias_novedad",
    10: "dias_laborados",
    11: "sub_trans_quincenal",
    12: "salario_quincenal",
    13: "total_ingreso",
    15: "aportes",
    18: "no_salarial_quincenal",
    19: "total_deducciones",
    20: "dispersion_banco",
    21: "pago_total_nomina",
    23: "valor_dia_dominical",
    24: "dominical",
    26: "total",
}


def _norm(value):
    return " ".join(str(value or "").strip().lower().split())


def _id_key(value):
    if value is None:
        return ""
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value).strip()


def validate_calculation_workbook(path: Path):
    wb = load_workbook(path, data_only=False)
    ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
    headers = [ws.cell(1, c).value for c in range(1, 27)]
    expected = [_norm(h) for h in CALC_HEADERS]
    actual = [_norm(h) for h in headers]
    missing = [CALC_HEADERS[i] for i, h in enumerate(expected) if h not in actual]
    if missing:
        raise ValueError(
            "El archivo no corresponde al formato de Cálculo de Nómina. "
            "Faltan encabezados: " + ", ".join(missing)
        )
    return ws.title


def _legacy_aportes_rate(cell_value):
    """Migra la tasa histórica escrita en la fórmula O a una política explícita."""
    if isinstance(cell_value, str):
        match = re.search(r"\*(\d+(?:\.\d+)?)%", cell_value)
        if match:
            return float(match.group(1)) / 100
    return 0.08


def _legacy_transport_override(cell_value):
    """Detecta excepciones históricas tipo J-3/J-4 en el subsidio de transporte."""
    if isinstance(cell_value, str):
        match = re.search(r"J\d+-(\d+(?:\.\d+)?)", cell_value)
        if match and "-H" not in cell_value.upper():
            return float(match.group(1))
    return None


def _legacy_no_salarial_basis(cell_value):
    if isinstance(cell_value, str) and "*J" in cell_value.replace(" ", "").upper():
        return "worked_days"
    return "labor_days_minus_novelty"


def _read_source_rows(path: Path):
    """Lee únicamente datos fuente; ignora las fórmulas derivadas del Excel."""
    wb = load_workbook(path, data_only=False)
    ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
    rows = []
    for r in range(2, ws.max_row + 1):
        cedula = ws.cell(r, 3).value
        nombre = ws.cell(r, 1).value
        if cedula in (None, "") and nombre in (None, ""):
            continue
        rows.append({
            "excel_row": r,
            "nombre": ws.cell(r, 1).value,
            "apellido": ws.cell(r, 2).value,
            "cedula": cedula,
            "salario_basico": ws.cell(r, 4).value,
            "aux_transporte": ws.cell(r, 5).value,
            "dias_laborales": ws.cell(r, 6).value,
            "dnj": ws.cell(r, 7).value,
            "dj": ws.cell(r, 8).value,
            "dias_salud": ws.cell(r, 14).value,
            "prestamos": ws.cell(r, 16).value,
            "no_salarial": ws.cell(r, 17).value,
            "dias_dominical": ws.cell(r, 22).value,
            "comisiones": ws.cell(r, 25).value,
            # El Excel histórico contiene algunas excepciones implícitas: en ciertas
            # filas R está vacío (no se paga no salarial), y en otras R/W tienen un
            # valor manual. Las convertimos en políticas explícitas para que Python
            # preserve el comportamiento sin depender de evaluar fórmulas de Excel.
            "aplicar_no_salarial_quincenal": ws.cell(r, 18).value is not None,
            "no_salarial_quincenal_override": (
                ws.cell(r, 18).value
                if ws.cell(r, 18).value is not None
                and not (isinstance(ws.cell(r, 18).value, str) and ws.cell(r, 18).value.startswith("="))
                else None
            ),
            "valor_dia_dominical_override": (
                ws.cell(r, 23).value
                if ws.cell(r, 23).value is not None
                and not (isinstance(ws.cell(r, 23).value, str) and ws.cell(r, 23).value.startswith("="))
                else None
            ),
            "aportes_rate": _legacy_aportes_rate(ws.cell(r, 15).value),
            "transport_dj_days_override": _legacy_transport_override(ws.cell(r, 11).value),
            "no_salarial_basis": _legacy_no_salarial_basis(ws.cell(r, 18).value),
        })
    return rows


def _calculate_rows(path: Path):
    calculated_rows = []
    for raw in _read_source_rows(path):
        inputs = build_inputs(raw)
        calc = calculate(inputs)
        derived = as_float_dict(calc)
        item = {
            **raw,
            "salario_basico": float(inputs.salario_basico),
            "aux_transporte": float(inputs.aux_transporte),
            "dias_laborales": float(inputs.dias_laborales),
            "dnj": float(inputs.dnj),
            "dj": float(inputs.dj),
            "dias_salud": float(inputs.dias_salud),
            "prestamos": float(inputs.prestamos),
            "no_salarial": float(inputs.no_salarial),
            "dias_dominical": float(inputs.dias_dominical),
            "comisiones": float(inputs.comisiones),
            **derived,
        }
        calculated_rows.append(item)
    return calculated_rows


def process_payroll(path: Path):
    validate_calculation_workbook(path)
    rows = _calculate_rows(path)
    alerts = []
    for item in rows:
        emp_alerts = []
        if not _id_key(item["cedula"]):
            emp_alerts.append("Cédula vacía")
        if item["dias_laborales"] > 15:
            emp_alerts.append("Días laborales superiores a 15")
        if item["dias_laborales"] < 0 or item["dnj"] < 0 or item["dj"] < 0:
            emp_alerts.append("Días negativos")
        if item["dias_laborados"] < 0:
            emp_alerts.append("Días laborados negativos")
        if item["total"] < 0:
            emp_alerts.append("Total de nómina negativo")
        item["alertas"] = "; ".join(emp_alerts)
        item["estado"] = "REVISAR" if emp_alerts else "OK"
        alerts.extend(emp_alerts)

    return {
        "rows": rows,
        "summary": {
            "empleados": len(rows),
            "novedades": sum(1 for x in rows if any([
                x["dnj"], x["dj"], x["prestamos"], x["no_salarial"],
                x["dias_dominical"], x["comisiones"]
            ])),
            "alertas": sum(1 for x in rows if x["estado"] == "REVISAR"),
            "total_neto": sum(float(x["total"] or 0) for x in rows),
            "motor_calculo": "PYTHON",
        }
    }


def generate_calculation_file(input_path: Path, result, review_id: str, version: int):
    """Genera cálculo procesado reemplazando fórmulas derivadas por valores Python."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / f"{review_id}_V{version}_01_CALCULO_DE_NOMINA_PROCESADO.xlsx"
    copy2(input_path, output)
    wb = load_workbook(output, data_only=False)
    ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active

    for item in result["rows"]:
        row = item["excel_row"]
        for col, key in CALCULATED_COLUMNS.items():
            ws.cell(row, col).value = item[key]

    # Hoja de trazabilidad técnica: visible y sin fórmulas ocultas.
    if "REGLAS_MOTOR_PYTHON" in wb.sheetnames:
        del wb["REGLAS_MOTOR_PYTHON"]
    rules_ws = wb.create_sheet("REGLAS_MOTOR_PYTHON")
    rules_ws["A1"] = "Campo calculado"
    rules_ws["B1"] = "Regla implementada en Python"
    rules_ws["D1"] = "Motor"
    rules_ws["E1"] = "PYTHON"
    for idx, (key, description) in enumerate(RULES.items(), start=2):
        rules_ws.cell(idx, 1).value = key
        rules_ws.cell(idx, 2).value = description

    wb.save(output)
    return output


def generate_signature_file(result, review_id: str, version: int):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / f"{review_id}_V{version}_02_FORMATO_NOMINA_FIRMA.xlsx"
    copy2(SIGN_TEMPLATE, output)
    wb = load_workbook(output)
    ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active

    for r in range(2, 34):
        for c in range(2, 16):
            ws.cell(r, c).value = None

    for idx, item in enumerate(result["rows"], start=2):
        if idx > 33:
            break
        values = [
            item["nombre"], item["apellido"], item["cedula"],
            item["salario_basico"], item["aux_transporte"], item["dias_laborales"],
            item["dnj"] or None, item["dj"] or None,
            item["salario_quincenal"], item["sub_trans_quincenal"],
            item["aportes"], item["prestamos"] or None,
            item["no_salarial_quincenal"] or None, item["total"]
        ]
        for c, value in enumerate(values, start=2):
            ws.cell(idx, c).value = value

    ws["B36"] = "TOTAL"
    ws["O36"] = sum(float(x["total"] or 0) for x in result["rows"][:32])
    wb.save(output)
    return output


def _bank_master_by_id():
    wb = load_workbook(BANK_TEMPLATE, data_only=True)
    ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
    master = {}
    for r in range(2, ws.max_row + 1):
        cedula = _id_key(ws.cell(r, 2).value)
        if not cedula:
            continue
        master[cedula] = {
            "tipo_id": ws.cell(r, 1).value,
            "codigo_banco": ws.cell(r, 5).value,
            "tipo_producto": ws.cell(r, 6).value,
            "numero_producto": ws.cell(r, 7).value,
            "referencia": ws.cell(r, 9).value or "NOMINA",
            "correo": ws.cell(r, 10).value,
            "descripcion": ws.cell(r, 11).value,
        }
    return master


def generate_bank_file(result, review_id: str, version: int):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / f"{review_id}_V{version}_03_PLANTILLA_BANCO_PAGOS_NOMINA.xlsx"
    copy2(BANK_TEMPLATE, output)
    wb = load_workbook(output)
    ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
    master = _bank_master_by_id()

    for r in range(2, 34):
        for c in range(1, 12):
            ws.cell(r, c).value = None

    bank_warnings = []
    for idx, item in enumerate(result["rows"], start=2):
        if idx > 33:
            break
        cedula = _id_key(item["cedula"])
        bank = master.get(cedula, {})
        if not bank:
            bank_warnings.append(f"Sin datos bancarios para cédula {cedula}")
        ws.cell(idx, 1).value = bank.get("tipo_id")
        ws.cell(idx, 2).value = item["cedula"]
        ws.cell(idx, 3).value = item["nombre"]
        ws.cell(idx, 4).value = item["apellido"]
        ws.cell(idx, 5).value = bank.get("codigo_banco")
        ws.cell(idx, 6).value = bank.get("tipo_producto")
        ws.cell(idx, 7).value = bank.get("numero_producto")
        ws.cell(idx, 8).value = item["dispersion_banco"]
        ws.cell(idx, 9).value = bank.get("referencia") or "NOMINA"
        ws.cell(idx, 10).value = bank.get("correo")
        ws.cell(idx, 11).value = bank.get("descripcion")

    ws["A35"] = "TOTAL "
    ws["H35"] = sum(float(x["dispersion_banco"] or 0) for x in result["rows"][:32])
    wb.save(output)
    return output, bank_warnings


def generate_all_files(input_path: Path, result, review_id: str, version: int):
    calc = generate_calculation_file(input_path, result, review_id, version)
    signature = generate_signature_file(result, review_id, version)
    bank, warnings = generate_bank_file(result, review_id, version)
    return {
        "calculation": calc,
        "signature": signature,
        "bank": bank,
        "bank_warnings": warnings,
    }
