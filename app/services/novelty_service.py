from __future__ import annotations

import json
import os
import re
import calendar
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from shutil import copy2
from copy import copy
from openpyxl import Workbook, load_workbook

from .employee_service import ensure_employee_from_novelty, normalize_document, split_name, list_active_employees, apply_roster_novelty

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = DATA_DIR / "output"
TEMPLATE_DIR = BASE_DIR / "templates_excel"
CALC_TEMPLATE = TEMPLATE_DIR / "2026_CALCULO_DE_NOMINA.xlsx"
SIGN_TEMPLATE = TEMPLATE_DIR / "FORMATO_NOMINA_FIRMA.xlsx"
BANK_TEMPLATE = TEMPLATE_DIR / "PLANTILLA_BANCO_PAGOS_NOMINA.xlsx"
PAYSLIP_TEMPLATE = TEMPLATE_DIR / "DESPRENDIBLE_DE_NOMINA.xlsx"
REGISTRY = DATA_DIR / "payroll_registry.json"
BANK_MASTER = DATA_DIR / "bank_master.json"

REQUIRED_HEADERS = ["documento"]

# Todos los demás campos son opcionales porque la fuente maestra es Empleados.
BASE_OPTIONAL_HEADERS = ["tipo_novedad", "accion", "empleado", "salario_base", "dias_trabajados", "horas_extra", "bonificacion", "descuento", "banco", "tipo_cuenta", "cuenta", "tipo_identificacion", "codigo_banco", "correo_pago", "referencia_pago", "descripcion_pago", "fecha_inicio", "fecha_fin", "dias_novedad", "grupo_nomina"]

# Campos adicionales opcionales. Permiten alimentar el formato histórico completo
# sin convertir el Excel de cálculo en fuente de verdad.
OPTIONAL_HEADERS = [
    "auxilio_transporte", "dias_novedad_no_justificada", "novedad_justificada",
    "dias_salud", "no_salarial", "dias_dominical", "comisiones",
    "dias_incapacidad_justificada", "dias_incapacidad_injustificada", "dias_vacaciones", "dias_permiso_no_remunerado"
]

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


def _d(value, default="0") -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"Valor numérico inválido: {value!r}")


def _norm(value):
    return str(value or "").strip().lower().replace(" ", "_")


def read_novelties_excel(path: Path) -> list[dict]:
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    headers = [_norm(ws.cell(1, c).value) for c in range(1, ws.max_column + 1)]
    missing = [h for h in REQUIRED_HEADERS if h not in headers]
    if missing:
        raise ValueError("El archivo debe ser el formato de NOVEDADES. Faltan columnas: " + ", ".join(missing))
    pos = {h: headers.index(h) + 1 for h in REQUIRED_HEADERS}
    optional_pos = {h: headers.index(h) + 1 for h in (BASE_OPTIONAL_HEADERS + OPTIONAL_HEADERS) if h in headers}
    rows = []
    for r in range(2, ws.max_row + 1):
        doc = ws.cell(r, pos["documento"]).value
        if doc in (None, ""):
            continue
        item = {h: ws.cell(r, pos[h]).value for h in REQUIRED_HEADERS}
        for h, c in optional_pos.items():
            item[h] = ws.cell(r, c).value
        item["documento"] = normalize_document(item["documento"])
        rows.append(item)
    if not rows:
        raise ValueError("El archivo de novedades no contiene registros con documento.")
    return rows


def _baseline_row_from_employee(employee: dict, default_days: Decimal) -> dict:
    return {
        "documento": normalize_document(employee.get("document")),
        "empleado": str(employee.get("name") or "").strip(),
        "salario_base": employee.get("salary_base") or 0,
        "dias_trabajados": float(default_days),
        "horas_extra": 0,
        "bonificacion": 0,
        "descuento": 0,
        "banco": employee.get("bank") or "",
        "tipo_cuenta": employee.get("bank_account_type") or "",
        "cuenta": employee.get("bank_account") or "",
        "tipo_identificacion": employee.get("id_type") or "CC",
        "codigo_banco": employee.get("bank_code") or "",
        "correo_pago": employee.get("payment_email") or employee.get("email") or "",
        "referencia_pago": employee.get("payment_reference") or "NOMINA",
        "descripcion_pago": employee.get("payment_description") or "",
        "auxilio_transporte": employee.get("transport_allowance") or 0,
        "dias_novedad_no_justificada": 0,
        "novedad_justificada": 0,
        "dias_salud": float(default_days),
        "no_salarial": 0,
        "dias_dominical": 0,
        "comisiones": 0,
        "_from_roster": True,
    }


def build_full_payroll_input(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Construye la corrida completa: maestro de empleados + novedades.

    Las novedades solo modifican a los empleados afectados. Los empleados activos
    del maestro siempre permanecen en la nómina aunque no tengan novedad.
    """
    # Altas y retiros se gestionan desde el mismo archivo de NOVEDADES.
    # El registro nunca se borra físicamente: se conserva para auditoría.
    roster_actions = {}
    for raw in rows:
        applied = apply_roster_novelty(raw)
        if applied:
            roster_actions[normalize_document(raw.get("documento"))] = applied

    # Después de aplicar altas/retiros, se toma la planta persistente vigente.
    roster = list_active_employees()
    if not roster:
        raise ValueError(
            "No hay un maestro de empleados confirmado. Importa el listado oficial desde "
            "Siigo Nómina > Empleados > Exportar lista de empleados, o sincroniza y confirma "
            "los trabajadores antes de calcular. Las novedades NO definen la planta."
        )

    new_employees = []
    roster_docs_initial = {normalize_document(x.get("document")) for x in roster}
    for raw in rows:
        document = normalize_document(raw.get("documento"))
        if document and document not in roster_docs_initial:
            employee, is_new = ensure_employee_from_novelty(raw)
            if is_new:
                new_employees.append({"document": employee["document"], "name": employee["name"]})

    novelty_by_doc = {normalize_document(x.get("documento")): dict(x) for x in rows if normalize_document(x.get("documento"))}
    default_days = _d(os.getenv("PAYROLL_DEFAULT_LABOR_DAYS", "15"))
    merged = []
    for employee in roster:
        document = normalize_document(employee.get("document"))
        base = _baseline_row_from_employee(employee, default_days)
        novelty = novelty_by_doc.get(document)
        if novelty:
            # La novedad pisa únicamente campos explícitos; no borra datos maestros.
            for key, value in novelty.items():
                if value not in (None, ""):
                    base[key] = value
            base["_has_novelty"] = True
        else:
            base["_has_novelty"] = False
        merged.append(base)

    # Una novedad de alguien fuera del maestro se registra como NUEVO PENDIENTE,
    # pero no se agrega silenciosamente a la nómina hasta confirmar el alta.
    return merged, new_employees


def calculate_novelties(rows: list[dict]) -> dict:
    overtime_factor = _d(os.getenv("PAYROLL_OVERTIME_FACTOR", "1.25"))
    month_hours = _d(os.getenv("PAYROLL_MONTH_HOURS", "240"))
    health_rate = _d(os.getenv("PAYROLL_EMPLOYEE_HEALTH_RATE", "0.04"))
    pension_rate = _d(os.getenv("PAYROLL_EMPLOYEE_PENSION_RATE", "0.04"))
    contribution_rate = health_rate + pension_rate
    full_rows, new_employees = build_full_payroll_input(rows)
    calculated = []
    alerts = []

    for raw in full_rows:
        employee, _ = ensure_employee_from_novelty(raw)

        salary = _d(raw.get("salario_base"))
        labor_days = _d(raw.get("dias_trabajados"))
        # Novedades de tiempo. Se conservan los campos históricos DNJ/DJ y se
        # agregan tipos explícitos para que el Excel/formulario sea entendible.
        incap_just = _d(raw.get("dias_incapacidad_justificada"))
        incap_injust = _d(raw.get("dias_incapacidad_injustificada"))
        vacation_days = _d(raw.get("dias_vacaciones"))
        unpaid_leave_days = _d(raw.get("dias_permiso_no_remunerado"))
        novelty_type = str(raw.get("tipo_novedad") or "").strip().upper()
        typed_days = _d(raw.get("dias_novedad"))
        if novelty_type == "INCAPACIDAD_JUSTIFICADA": incap_just += typed_days
        elif novelty_type == "INCAPACIDAD_INJUSTIFICADA": incap_injust += typed_days
        elif novelty_type == "VACACIONES": vacation_days += typed_days
        elif novelty_type == "PERMISO_NO_REMUNERADO": unpaid_leave_days += typed_days

        dnj = _d(raw.get("dias_novedad_no_justificada")) + incap_injust + unpaid_leave_days
        dj = _d(raw.get("novedad_justificada")) + incap_just + vacation_days
        novelty_days = dnj + dj
        # Permiso no remunerado e incapacidad injustificada descuentan el día completo.
        # Vacaciones/incapacidad justificada quedan identificadas separadamente y se
        # mantienen en DJ para trazabilidad; su regla económica puede parametrizarse.
        worked_days = labor_days - dnj
        health_days = _d(raw.get("dias_salud"), str(labor_days)) if raw.get("dias_salud") not in (None, "") else labor_days
        extra_hours = _d(raw.get("horas_extra"))
        bonus = _d(raw.get("bonificacion"))
        other_discount = _d(raw.get("descuento"))
        aux_transport = _d(raw.get("auxilio_transporte") if raw.get("auxilio_transporte") not in (None, "") else employee.get("transport_allowance", 0))
        no_salary = _d(raw.get("no_salarial") if raw.get("no_salarial") not in (None, "") else bonus)
        dominical_days = _d(raw.get("dias_dominical"))
        commissions = _d(raw.get("comisiones"))

        transport_days = max(Decimal("0"), worked_days - dj) if dj > 0 else max(Decimal("0"), worked_days)
        transport_period = aux_transport / Decimal("30") * transport_days
        base_pay = salary / Decimal("30") * worked_days
        hour_value = salary / month_hours if month_hours else Decimal("0")
        overtime_pay = hour_value * overtime_factor * extra_hours
        total_income = base_pay + transport_period + overtime_pay

        contribution_base_days = min(max(health_days, Decimal("0")), Decimal("30"))
        health_employee = salary * health_rate / Decimal("30") * contribution_base_days
        pension_employee = salary * pension_rate / Decimal("30") * contribution_base_days
        contributions = health_employee + pension_employee

        no_salary_period = no_salary / Decimal("30") * max(Decimal("0"), labor_days - novelty_days)
        deductions = contributions + other_discount
        payroll_payment = total_income + no_salary_period - deductions
        day_dominical_value = salary / Decimal("30") + aux_transport / Decimal("30")
        dominical_value = dominical_days * day_dominical_value
        net = payroll_payment + dominical_value + commissions

        first, last = split_name(raw.get("empleado") or employee.get("name") or "")
        row_alerts = []
        if salary <= 0: row_alerts.append("Falta salario base en el maestro del empleado")
        if labor_days < 0 or labor_days > 31: row_alerts.append("Días trabajados fuera de rango 0-31")
        if dnj < 0 or dj < 0 or novelty_days > labor_days: row_alerts.append("Días de novedad inválidos")
        if extra_hours < 0: row_alerts.append("Horas extra negativas")
        if net < 0: row_alerts.append("Neto negativo")
        if not raw.get("banco") or not raw.get("cuenta"): row_alerts.append("Datos bancarios incompletos")
        if row_alerts: alerts.append({"document": normalize_document(raw.get("documento")), "alerts": row_alerts})

        calculated.append({
            "nombre": first, "apellido": last, "cedula": normalize_document(raw.get("documento")),
            "empleado": str(raw.get("empleado") or employee.get("name") or "").strip(),
            "salario_basico": float(salary), "aux_transporte": float(aux_transport),
            "dias_laborales": float(labor_days), "dias_trabajados": float(labor_days),
            "dnj": float(dnj), "dj": float(dj), "dias_novedad": float(novelty_days),
            "dias_laborados": float(worked_days), "dias_salud": float(health_days),
            "horas_extra": float(extra_hours), "bonificacion": float(bonus), "descuento": float(other_discount),
            "dias_incapacidad_justificada": float(incap_just),
            "dias_incapacidad_injustificada": float(incap_injust),
            "dias_vacaciones": float(vacation_days),
            "dias_permiso_no_remunerado": float(unpaid_leave_days),
            "banco": str(raw.get("banco") or employee.get("bank") or ""),
            "tipo_cuenta": str(raw.get("tipo_cuenta") or employee.get("bank_account_type") or ""),
            "cuenta": str(raw.get("cuenta") or employee.get("bank_account") or ""),
            "tipo_identificacion": str(raw.get("tipo_identificacion") or employee.get("id_type") or "CC"),
            "codigo_banco": str(raw.get("codigo_banco") or employee.get("bank_code") or ""),
            "correo_pago": str(raw.get("correo_pago") or employee.get("payment_email") or employee.get("email") or ""),
            "referencia_pago": str(raw.get("referencia_pago") or employee.get("payment_reference") or "NOMINA"),
            "descripcion_pago": str(raw.get("descripcion_pago") or employee.get("payment_description") or ""),
            "salario_periodo": float(base_pay), "salario_quincenal": float(base_pay),
            "sub_trans_quincenal": float(transport_period),
            "valor_hora": float(hour_value), "pago_horas_extra": float(overtime_pay),
            "total_ingreso": float(total_income),
            "salud_empleado": float(health_employee), "pension_empleado": float(pension_employee),
            "aportes": float(contributions), "prestamos": float(other_discount),
            "no_salarial": float(no_salary), "no_salarial_quincenal": float(no_salary_period),
            "total_deducciones": float(deductions),
            "dispersion_banco": float(payroll_payment), "pago_total_nomina": float(payroll_payment),
            "dias_dominical": float(dominical_days), "valor_dia_dominical": float(day_dominical_value),
            "dominical": float(dominical_value), "comisiones": float(commissions),
            "payroll_group": str(employee.get("payroll_group") or ""),
            "health_provider": str(employee.get("health_provider") or ""),
            "pension_provider": str(employee.get("pension_provider") or ""),
            "arl_provider": str(employee.get("arl_provider") or ""),
            "compensation_fund": str(employee.get("compensation_fund") or ""),
            "severance_fund": str(employee.get("severance_fund") or ""),
            "email": str(employee.get("email") or ""),
            "phone": str(employee.get("phone") or ""),
            "position": str(employee.get("position") or ""),
            "contract_type": str(employee.get("contract_type") or ""),
            "contract_number": str(employee.get("contract_number") or ""),
            "contract_start": str(employee.get("contract_start") or ""),
            "contract_end": str(employee.get("contract_end") or ""),
            "salary_type": str(employee.get("salary_type") or "Ordinario"),
            "total_devengado": float(total_income + no_salary_period + dominical_value + commissions),
            "total": float(net),
            "tiene_novedad": bool(raw.get("_has_novelty")),
            "estado": "REVISAR" if row_alerts else "OK", "alertas": "; ".join(row_alerts),
        })

    roster_count = len(list_active_employees())
    if len(calculated) != roster_count:
        raise ValueError(
            f"Control de integridad: el maestro tiene {roster_count} empleados activos, "
            f"pero el cálculo produjo {len(calculated)}. Se bloqueó la salida para evitar una nómina incompleta."
        )

    with_novelties = sum(1 for x in calculated if x.get("tiene_novedad"))
    critical_incomplete = sum(
        1 for x in calculated
        if float(x.get("salario_basico") or 0) <= 0
    )
    return {
        "rows": calculated,
        "new_employees": new_employees,
        "alerts_detail": alerts,
        "summary": {
            "empleados": len(calculated),
            "empleados_maestro": len(list_active_employees()),
            "nuevos": len(new_employees),
            "con_novedades": with_novelties,
            "sin_novedades": len(calculated) - with_novelties,
            "novedades": with_novelties,
            "alertas": len(alerts),
            "criticos_incompletos": critical_incomplete,
            "total_devengado": sum(x["total_devengado"] for x in calculated),
            "total_deducciones": sum(x["total_deducciones"] for x in calculated),
            "total_neto": sum(x["total"] for x in calculated),
            "motor_calculo": "PYTHON",
            "entrada": "NOVEDADES + MAESTRO_EMPLEADOS",
        },
        "rules": {
            "overtime_factor": float(overtime_factor),
            "month_hours": float(month_hours),
            "employee_health_rate": float(health_rate),
            "employee_pension_rate": float(pension_rate),
            "employee_contribution_rate": float(contribution_rate),
            "default_labor_days": float(_d(os.getenv("PAYROLL_DEFAULT_LABOR_DAYS", "15"))),
        },
    }

MONTHS_ES = {"ENERO":1,"FEBRERO":2,"MARZO":3,"ABRIL":4,"MAYO":5,"JUNIO":6,"JULIO":7,"AGOSTO":8,"SEPTIEMBRE":9,"SETIEMBRE":9,"OCTUBRE":10,"NOVIEMBRE":11,"DICIEMBRE":12}

def _infer_period_from_path(path: Path, rows: list[dict]) -> tuple[str, str, str]:
    # 1) Si Novedades trae fechas, se usan primero.
    parsed=[]
    for r in rows:
        for key in ("fecha_inicio","fecha_fin"):
            v=r.get(key)
            if isinstance(v, datetime): parsed.append(v.date())
            elif isinstance(v, date): parsed.append(v)
            elif v:
                for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y"):
                    try: parsed.append(datetime.strptime(str(v).strip(),fmt).date()); break
                    except ValueError: pass
    if parsed:
        a,b=min(parsed),max(parsed)
        return a.isoformat(), b.isoformat(), f"{a.strftime('%d/%m/%Y')} - {b.strftime('%d/%m/%Y')}"
    # 2) Inferencia desde nombres tipo SEPTIEMBRE 1-15 / AGOSTO 16-30.
    name=path.stem.upper().replace('_',' ')
    month=next(((m,n) for m,n in MONTHS_ES.items() if m in name),None)
    mrange=re.search(r"(\d{1,2})\s*[-A]\s*(\d{1,2})", name)
    if month and mrange:
        year_match=re.search(r"20\d{2}",name); year=int(year_match.group()) if year_match else datetime.now().year
        mo=month[1]; d1=int(mrange.group(1)); d2=int(mrange.group(2)); d2=min(d2,calendar.monthrange(year,mo)[1])
        a=date(year,mo,d1); b=date(year,mo,d2)
        return a.isoformat(),b.isoformat(),f"{a.strftime('%d/%m/%Y')} - {b.strftime('%d/%m/%Y')}"
    return "", "", "PERÍODO SEGÚN NOVEDADES"

def process_novelties_file(path: Path) -> dict:
    rows=read_novelties_excel(path)
    result=calculate_novelties(rows)
    start,end,label=_infer_period_from_path(path,rows)
    result["period"]={"start":start,"end":end,"label":label}
    return result


def _blank_if_zero(value):
    return None if value in (None, 0, 0.0) else value



def _copy_row_style(ws, source_row: int, target_row: int, max_col: int) -> None:
    ws.row_dimensions[target_row].height = ws.row_dimensions[source_row].height
    for c in range(1, max_col + 1):
        src = ws.cell(source_row, c)
        dst = ws.cell(target_row, c)
        if src.has_style:
            dst._style = copy(src._style)
        if src.number_format:
            dst.number_format = src.number_format
        if src.font:
            dst.font = copy(src.font)
        if src.fill:
            dst.fill = copy(src.fill)
        if src.border:
            dst.border = copy(src.border)
        if src.alignment:
            dst.alignment = copy(src.alignment)
        if src.protection:
            dst.protection = copy(src.protection)


def _prepare_dynamic_rows(ws, employee_count: int, *, data_start: int, template_last_data_row: int, total_template_row: int, max_col: int) -> int:
    """Amplía la plantilla sin truncar empleados y devuelve la fila TOTAL."""
    needed_last = data_start + max(employee_count, 1) - 1
    total_row = max(total_template_row, needed_last + 2)

    # Copiar estilo de fila de datos para cualquier empleado que exceda la plantilla.
    for row in range(template_last_data_row + 1, needed_last + 1):
        _copy_row_style(ws, template_last_data_row, row, max_col)

    if total_row != total_template_row:
        _copy_row_style(ws, total_template_row, total_row, max_col)

    # Limpieza de datos en toda el área que se va a reutilizar.
    clear_until = max(total_template_row, total_row)
    for r in range(data_start, clear_until + 1):
        for c in range(1, max_col + 1):
            ws.cell(r, c).value = None
    return total_row

def generate_calculation_file(result: dict, review_id: str, version: int) -> Path:
    """Genera el cálculo histórico completo sin truncar trabajadores."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{review_id}_V{version}_01_CALCULO_DE_NOMINA_PROCESADO.xlsx"
    copy2(CALC_TEMPLATE, path)
    wb = load_workbook(path)
    ws = wb.active

    for extra in list(wb.sheetnames)[1:]:
        del wb[extra]
    ws = wb.active
    for c, header in enumerate(CALC_HEADERS, start=1):
        ws.cell(1, c).value = header

    total_row = _prepare_dynamic_rows(
        ws, len(result["rows"]), data_start=2, template_last_data_row=35,
        total_template_row=36, max_col=26
    )

    for idx, x in enumerate(result["rows"], start=2):
        values = [
            x.get("nombre", ""), x.get("apellido", ""), x.get("cedula", ""),
            float(x.get("salario_basico") or 0), _blank_if_zero(float(x.get("aux_transporte") or 0)),
            float(x.get("dias_laborales") or 0), _blank_if_zero(float(x.get("dnj") or 0)),
            _blank_if_zero(float(x.get("dj") or 0)), _blank_if_zero(float(x.get("dias_novedad") or 0)),
            float(x.get("dias_laborados") or 0), float(x.get("sub_trans_quincenal") or 0),
            float(x.get("salario_quincenal") or 0), float(x.get("total_ingreso") or 0),
            float(x.get("dias_salud") or 0), float(x.get("aportes") or 0),
            _blank_if_zero(float(x.get("prestamos") or 0)), _blank_if_zero(float(x.get("no_salarial") or 0)),
            _blank_if_zero(float(x.get("no_salarial_quincenal") or 0)), float(x.get("total_deducciones") or 0),
            float(x.get("dispersion_banco") or 0), float(x.get("pago_total_nomina") or 0),
            _blank_if_zero(float(x.get("dias_dominical") or 0)), float(x.get("valor_dia_dominical") or 0),
            _blank_if_zero(float(x.get("dominical") or 0)), _blank_if_zero(float(x.get("comisiones") or 0)),
            float(x.get("total") or 0),
        ]
        for c, value in enumerate(values, start=1):
            ws.cell(idx, c).value = value

    ws.cell(total_row, 1).value = "TOTAL"
    ws.cell(total_row, 26).value = result["summary"]["total_neto"]
    wb.save(path)
    return path

def save_payroll_snapshot(review_id: str, version: int, source: str, result: dict) -> None:
    data = []
    if REGISTRY.exists():
        try: data = json.loads(REGISTRY.read_text(encoding="utf-8"))
        except Exception: data = []
    data.append({"review_id": review_id, "version": version, "source": source, "created_at": datetime.now(timezone.utc).isoformat(), "summary": result["summary"], "rows": result["rows"]})
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_payrolls() -> list[dict]:
    if not REGISTRY.exists(): return []
    try: return list(reversed(json.loads(REGISTRY.read_text(encoding="utf-8"))))
    except Exception: return []


def get_payroll(review_id: str) -> dict | None:
    return next((x for x in list_payrolls() if x.get("review_id") == review_id), None)


def employee_history(document: str) -> list[dict]:
    key = normalize_document(document); out=[]
    for payroll in list_payrolls():
        row = next((r for r in payroll.get("rows",[]) if normalize_document(r.get("cedula")) == key), None)
        if row: out.append({"review_id": payroll.get("review_id"), "created_at": payroll.get("created_at"), "version": payroll.get("version"), "row": row})
    return out

def generate_signature_file(result: dict, review_id: str, version: int) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{review_id}_V{version}_02_FORMATO_NOMINA_FIRMA.xlsx"
    copy2(SIGN_TEMPLATE, path)
    wb = load_workbook(path)
    ws = wb.active
    total_row = _prepare_dynamic_rows(
        ws, len(result["rows"]), data_start=2, template_last_data_row=33,
        total_template_row=36, max_col=16
    )
    for idx, x in enumerate(result["rows"], start=2):
        vals = [
            x.get("nombre"), x.get("apellido"), x.get("cedula"),
            x.get("salario_basico"), x.get("aux_transporte", 0), x.get("dias_trabajados"),
            x.get("dnj", 0) or None, x.get("dj", 0) or None,
            x.get("salario_periodo", 0), x.get("sub_trans_quincenal", 0),
            x.get("aportes", 0), x.get("descuento", 0) or None,
            x.get("bonificacion", 0) or None, x.get("total", 0),
        ]
        for c, value in enumerate(vals, start=2):
            ws.cell(idx, c).value = value
    ws.cell(total_row, 2).value = "TOTAL"
    ws.cell(total_row, 15).value = result["summary"]["total_neto"]
    wb.save(path)
    return path



def _bank_template_master() -> dict:
    """Datos bancarios históricos entregados por Multy, separados de la plantilla visual.

    Esto permite conservar la plantilla bancaria limpia y generar cada periodo
    únicamente desde empleados + novedades. Los cambios posteriores se guardan
    en el maestro del empleado mediante INGRESO/CAMBIO_BANCO.
    """
    if not BANK_MASTER.exists():
        return {}
    try:
        rows = json.loads(BANK_MASTER.read_text(encoding="utf-8"))
    except Exception:
        return {}
    master = {}
    for item in rows if isinstance(rows, list) else []:
        doc = normalize_document(item.get("document"))
        if not doc:
            continue
        master[doc] = {
            "tipo_identificacion": item.get("id_type_code") or "1",
            "codigo_banco": item.get("bank_code") or "",
            "tipo_cuenta": item.get("bank_account_type") or "",
            "cuenta": item.get("bank_account") or "",
            "referencia_pago": item.get("payment_reference") or "NOMINA",
            "correo_pago": item.get("payment_email") or "",
            "descripcion_pago": item.get("payment_description") or "",
        }
    return master

def generate_bank_file(result: dict, review_id: str, version: int) -> tuple[Path,list[str]]:
    """Genera el archivo bancario usando la plantilla real entregada por Multy."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{review_id}_V{version}_03_PLANTILLA_BANCO_PAGOS_NOMINA.xlsx"
    copy2(BANK_TEMPLATE, path)
    wb = load_workbook(path)
    ws = wb.active
    # La plantilla real tiene A:K y hasta 32 filas de empleados. Se amplía si hace falta.
    total_row = _prepare_dynamic_rows(ws, len(result["rows"]), data_start=2,
                                      template_last_data_row=33, total_template_row=35, max_col=11)
    warnings=[]
    master = _bank_template_master()
    for idx, x in enumerate(result["rows"], start=2):
        fallback = master.get(normalize_document(x.get("cedula")), {})
        bank_data = {k: (x.get(k) if x.get(k) not in (None, "") else fallback.get(k, "")) for k in
                     ("tipo_identificacion","codigo_banco","tipo_cuenta","cuenta","referencia_pago","correo_pago","descripcion_pago")}
        # El formato bancario real usa códigos numéricos. Para trabajadores históricos
        # prevalece el código que Multy ya utilizó en su archivo bancario.
        if fallback.get("tipo_identificacion"):
            bank_data["tipo_identificacion"] = fallback["tipo_identificacion"]
        else:
            id_map = {"CC": "1", "CE": "2", "TI": "3", "PP": "4", "PPT": "5"}
            bank_data["tipo_identificacion"] = id_map.get(str(bank_data.get("tipo_identificacion") or "").upper(), bank_data.get("tipo_identificacion") or "1")
        missing=[]
        if not bank_data.get("codigo_banco"): missing.append("código banco")
        if not bank_data.get("tipo_cuenta"): missing.append("tipo producto")
        if not bank_data.get("cuenta"): missing.append("número de cuenta")
        if missing:
            warnings.append(f"Datos bancarios incompletos para {x['cedula']}: {', '.join(missing)}")
        vals = [
            bank_data.get("tipo_identificacion") or "CC", x.get("cedula"),
            str(x.get("nombre") or "").upper(), str(x.get("apellido") or "").upper(),
            bank_data.get("codigo_banco", ""), bank_data.get("tipo_cuenta", ""), bank_data.get("cuenta", ""),
            x.get("total", 0), bank_data.get("referencia_pago") or "NOMINA",
            bank_data.get("correo_pago", ""), bank_data.get("descripcion_pago") or f"Pago nómina {x.get('empleado','')}"
        ]
        for c, value in enumerate(vals, start=1): ws.cell(idx, c).value = value
    ws.cell(total_row, 1).value = "TOTAL "
    ws.cell(total_row, 8).value = result["summary"]["total_neto"]
    wb.save(path)
    return path,warnings


def _safe_sheet_title(index: int, cedula: str) -> str:
    return f"{index:02d}_{str(cedula or '')[-8:]}"[:31]

_UNITS=["cero","uno","dos","tres","cuatro","cinco","seis","siete","ocho","nueve","diez","once","doce","trece","catorce","quince","dieciséis","diecisiete","dieciocho","diecinueve","veinte","veintiuno","veintidós","veintitrés","veinticuatro","veinticinco","veintiséis","veintisiete","veintiocho","veintinueve"]
_TENS=["","","veinte","treinta","cuarenta","cincuenta","sesenta","setenta","ochenta","noventa"]
_HUNDS=["","ciento","doscientos","trescientos","cuatrocientos","quinientos","seiscientos","setecientos","ochocientos","novecientos"]
def _under_1000(n:int)->str:
    if n==0:return ""
    if n==100:return "cien"
    parts=[]
    if n>=100: parts.append(_HUNDS[n//100]); n%=100
    if n<30:
        if n: parts.append(_UNITS[n])
    else:
        t=n//10; u=n%10; parts.append(_TENS[t]+((" y "+_UNITS[u]) if u else ""))
    return " ".join(parts)
def _number_to_words_es(value)->str:
    n=int(round(float(value or 0)))
    if n==0:return "CERO PESOS"
    parts=[]
    if n>=1_000_000:
        m=n//1_000_000; parts.append("un millón" if m==1 else _under_1000(m)+" millones"); n%=1_000_000
    if n>=1000:
        k=n//1000; parts.append("mil" if k==1 else _under_1000(k)+" mil"); n%=1000
    if n: parts.append(_under_1000(n))
    return (" ".join(parts)+" pesos").upper()

def _display(value, pending="PENDIENTE EN MAESTRO"):
    return value if value not in (None, "") else pending


def generate_payslips_file(result: dict, review_id: str, version: int) -> Path:
    """Genera un desprendible por trabajador usando el formato real entregado por Multy.

    El motor Python sigue siendo la fuente de verdad: no se usan las fórmulas de la
    plantilla para recalcular la nómina. La plantilla solo presenta los resultados.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{review_id}_V{version}_04_DESPRENDIBLES_DE_NOMINA.xlsx"
    copy2(PAYSLIP_TEMPLATE, path)
    wb = load_workbook(path)
    base = wb["Sin diligenciar"] if "Sin diligenciar" in wb.sheetnames else wb.active
    # Conservamos una hoja limpia como referencia y creamos una copia por empleado.
    for idx, x in enumerate(result["rows"], start=1):
        ws = wb.copy_worksheet(base)
        ws.title = _safe_sheet_title(idx, x.get("cedula"))
        ws["C7"] = x.get("empleado", "")
        ws["C8"] = x.get("cedula", "")
        ws["C9"] = _display(x.get("contract_type"))
        ws["C10"] = _display(x.get("email") or x.get("correo_pago"))
        ws["C11"] = _display(x.get("phone"))
        ws["C12"] = _display(x.get("position"))
        ws["C13"] = _display(x.get("salary_type"), "Ordinario")
        ws["C15"] = x.get("salario_basico", 0)
        ws["C16"] = x.get("aux_transporte", 0)
        bank_label = " ".join(v for v in [str(x.get("banco") or ""), str(x.get("tipo_cuenta") or "")] if v).strip()
        ws["C17"] = _display(bank_label)
        ws["E17"] = _display(x.get("cuenta"))
        ws["C18"] = "NO" if x.get("cuenta") else "SÍ"
        ws["E18"] = x.get("total", 0)
        period=result.get("period", {})
        ws["C19"] = period.get("label") or "PERÍODO SEGÚN NOVEDADES"
        ws["E19"] = x.get("dias_incapacidad_justificada", 0) + x.get("dias_incapacidad_injustificada", 0)
        ws["C20"] = period.get("start") or _display(x.get("contract_start"), "PENDIENTE PERÍODO")
        ws["E20"] = x.get("dias_laborados", 0)
        ws["C21"] = period.get("end") or _display(x.get("contract_end"), "PENDIENTE PERÍODO")
        # Valores calculados por Nómina AI; se reemplazan fórmulas de ejemplo.
        ws["C24"] = x.get("dias_laborados", 0); ws["D24"] = x.get("salario_periodo", 0)
        ws["C25"] = x.get("dias_laborados", 0); ws["D25"] = x.get("sub_trans_quincenal", 0)
        ws["C26"] = x.get("dias_incapacidad_justificada", 0); ws["D26"] = 0
        ws["C27"] = 0; ws["D27"] = 0
        ws["C30"] = x.get("horas_extra", 0); ws["D30"] = x.get("pago_horas_extra", 0)
        ws["C31"] = 0; ws["D31"] = 0
        ws["C32"] = x.get("dias_dominical", 0); ws["D32"] = x.get("dominical", 0)
        ws["C35"] = 0.04; ws["D35"] = x.get("salud_empleado", 0)
        ws["C36"] = 0.04; ws["D36"] = x.get("pension_empleado", 0)
        ws["C38"] = x.get("total_devengado", 0)
        ws["C39"] = x.get("total_deducciones", 0)
        ws["C40"] = x.get("total", 0)
        # Entidades si están disponibles en el maestro.
        ws["E7"] = _display(x.get("health_provider"))
        ws["E8"] = _display(x.get("pension_provider"))
        ws["E9"] = _display(x.get("arl_provider"))
        ws["E12"] = _display(x.get("severance_fund"))
        ws["E13"] = _display(x.get("compensation_fund"))
        ws["C41"] = _number_to_words_es(x.get("total", 0))
    # Las hojas de ejemplo no forman parte del archivo final entregable.
    for name in ["Diligenciado", "Sin diligenciar", "PDF"]:
        if name in wb.sheetnames and len(wb.sheetnames) > 1: wb.remove(wb[name])
    wb.save(path)
    return path


def generate_all_novelty_files(result: dict, review_id: str, version: int) -> dict:
    calc=generate_calculation_file(result, review_id, version)
    signature=generate_signature_file(result, review_id, version)
    bank,warnings=generate_bank_file(result, review_id, version)
    payslips=generate_payslips_file(result, review_id, version)
    return {'calculation':calc,'signature':signature,'bank':bank,'payslips':payslips,'bank_warnings':warnings}
