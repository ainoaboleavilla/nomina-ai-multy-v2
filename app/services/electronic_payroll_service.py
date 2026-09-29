from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import csv
import json

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


class ElectronicPayrollValidationError(ValueError):
    pass


def _money(value) -> float:
    try:
        return float(Decimal(str(value or 0)).quantize(Decimal("0.01")))
    except (InvalidOperation, TypeError, ValueError):
        return 0.0


def build_electronic_payroll_package(result: dict, review_id: str, version: int,
                                     period_start: str, period_end: str,
                                     employer: dict | None = None) -> dict:
    """Construye el contrato interno de nómina electrónica.

    El contrato es deliberadamente independiente del proveedor. No es XML DIAN ni
    un payload privado de Siigo. La transmisión externa queda a cargo de un adapter
    que solo puede habilitarse cuando exista una especificación oficial del proveedor.
    """
    employer = employer or {}
    employees = []
    for row in result.get("rows", []):
        earnings = {
            "salary": _money(row.get("salario_quincenal") or row.get("salario_periodo")),
            "overtime": _money(row.get("pago_horas_extra")),
            "transport_allowance": _money(row.get("sub_trans_quincenal")),
            "non_salary": _money(row.get("no_salarial_quincenal") or row.get("bonificacion")),
            "sunday_pay": _money(row.get("dominical")),
            "commissions": _money(row.get("comisiones")),
        }
        deductions = {
            "contributions": _money(row.get("aportes")),
            "loans": _money(row.get("prestamos")),
            "total": _money(row.get("total_deducciones")),
        }
        employees.append({
            "identification": str(row.get("cedula") or "").strip(),
            "first_name": str(row.get("nombre") or "").strip(),
            "last_name": str(row.get("apellido") or "").strip(),
            "earnings": earnings,
            "deductions": deductions,
            "net_payment": _money(row.get("total")),
            "worked_days": float(row.get("dias_laborados") or row.get("dias_trabajados") or 0),
            "health_days": float(row.get("dias_salud") or min(float(row.get("dias_trabajados") or 0), 30)),
        })

    package = {
        "schema": "nomina-ai/electronic-payroll/v3",
        "status": "DRAFT",
        "review_id": review_id,
        "version": int(version),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generated_on": date.today().isoformat(),
        "period": {"start": period_start, "end": period_end},
        "employer": {
            "nit": str(employer.get("nit") or "").strip(),
            "name": str(employer.get("name") or "").strip(),
        },
        "summary": result.get("summary", {}),
        "employees": employees,
        "transmission": {
            "provider": "SIIGO",
            "state": "NOT_SENT",
            "external_id": None,
            "sent_at": None,
            "human_approval_required": True,
            "provider_contract_status": "PENDING_OFFICIAL_ELECTRONIC_PAYROLL_SPEC",
        },
    }
    validation = validate_electronic_payroll_package(package)
    package["validation"] = validation
    package["status"] = "READY_FOR_PROVIDER_ADAPTER" if validation["is_valid"] else "VALIDATION_FAILED"
    return package


def validate_electronic_payroll_package(package: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    employer = package.get("employer", {})
    if not employer.get("nit"):
        errors.append("Falta el NIT del empleador.")
    if not employer.get("name"):
        errors.append("Falta la razón social del empleador.")

    start = package.get("period", {}).get("start")
    end = package.get("period", {}).get("end")
    if not start or not end:
        errors.append("El periodo debe tener fecha inicial y final.")
    elif start > end:
        errors.append("La fecha inicial del periodo no puede ser posterior a la fecha final.")

    employees = package.get("employees", [])
    if not employees:
        errors.append("La nómina electrónica no contiene empleados.")

    seen = set()
    total_net = Decimal("0")
    total_earnings = Decimal("0")
    total_deductions = Decimal("0")
    for index, employee in enumerate(employees, start=1):
        ident = employee.get("identification", "")
        label = f"Empleado #{index}"
        if not ident:
            errors.append(f"{label}: falta identificación.")
        elif ident in seen:
            errors.append(f"Identificación duplicada: {ident}.")
        seen.add(ident)
        if not employee.get("first_name"):
            warnings.append(f"{ident or label}: nombre vacío.")

        earnings = employee.get("earnings", {})
        deductions = employee.get("deductions", {})
        emp_earnings = sum(Decimal(str(v or 0)) for v in earnings.values())
        emp_deductions = Decimal(str(deductions.get("total") or 0))
        emp_net = Decimal(str(employee.get("net_payment") or 0))
        total_earnings += emp_earnings
        total_deductions += emp_deductions
        total_net += emp_net
        if emp_net < 0:
            warnings.append(f"{ident or label}: pago neto negativo ({emp_net}).")

    return {
        "is_valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "employee_count": len(employees),
        "totals": {
            "earnings": float(total_earnings.quantize(Decimal("0.01"))),
            "deductions": float(total_deductions.quantize(Decimal("0.01"))),
            "net": float(total_net.quantize(Decimal("0.01"))),
        },
    }


def save_electronic_payroll_package(output_dir: Path, package: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{package['review_id']}_V{package['version']}_04_NOMINA_ELECTRONICA.json"
    path = output_dir / filename
    path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    return path



def save_electronic_payroll_summary_xlsx(output_dir: Path, package: dict) -> Path:
    """Genera el archivo de control humano en Excel, con Unicode y formato legible."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{package['review_id']}_V{package['version']}_04_NOMINA_ELECTRONICA_CONTROL.xlsx"
    path = output_dir / filename

    wb = Workbook()
    ws = wb.active
    ws.title = "Control nómina electrónica"

    headers = [
        "Identificación", "Nombre", "Apellido", "Devengados", "Deducciones",
        "Neto", "Días laborados", "Días salud"
    ]
    ws.append(headers)

    for employee in package.get("employees", []):
        earnings = sum(Decimal(str(v or 0)) for v in employee.get("earnings", {}).values())
        deductions = Decimal(str(employee.get("deductions", {}).get("total") or 0))
        ws.append([
            str(employee.get("identification", "")),
            str(employee.get("first_name", "")),
            str(employee.get("last_name", "")),
            float(earnings.quantize(Decimal("0.01"))),
            float(deductions.quantize(Decimal("0.01"))),
            float(Decimal(str(employee.get("net_payment", 0) or 0)).quantize(Decimal("0.01"))),
            float(employee.get("worked_days", 0) or 0),
            float(employee.get("health_days", 0) or 0),
        ])

    # Presentación profesional y compatible con Excel.
    header_fill = PatternFill("solid", fgColor="111111")
    header_font = Font(color="FFD700", bold=True)
    thin = Side(style="thin", color="D9D9D9")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = Border(bottom=thin)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    for row in ws.iter_rows(min_row=2):
        row[0].number_format = "@"  # cédula como texto: no pierde ceros ni precisión
        for cell in row:
            cell.border = Border(bottom=thin)
            cell.alignment = Alignment(vertical="center")
        for idx in (3, 4, 5):
            row[idx].number_format = '#,##0.00'
        for idx in (6, 7):
            row[idx].number_format = '0.00'

    widths = [18, 24, 28, 18, 18, 18, 17, 14]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.row_dimensions[1].height = 24

    # Resumen verificable en una segunda hoja.
    summary = wb.create_sheet("Resumen")
    validation = package.get("validation", {})
    totals = validation.get("totals", {})
    summary_rows = [
        ("Estado", "LISTA PARA ADAPTADOR" if validation.get("is_valid") else "REQUIERE CORRECCIÓN"),
        ("Empleados", validation.get("employee_count", len(package.get("employees", [])))),
        ("Devengados", float(totals.get("earnings", 0) or 0)),
        ("Deducciones", float(totals.get("deductions", 0) or 0)),
        ("Neto", float(totals.get("net", 0) or 0)),
        ("Periodo inicio", package.get("period", {}).get("start", "")),
        ("Periodo fin", package.get("period", {}).get("end", "")),
        ("Empresa", package.get("employer", {}).get("name", "")),
        ("NIT", package.get("employer", {}).get("nit", "")),
    ]
    for item in summary_rows:
        summary.append(item)
    for cell in summary[1]:
        cell.font = Font(bold=True)
    for r in range(3, 6):
        summary.cell(r, 2).number_format = '#,##0.00'
    summary.column_dimensions["A"].width = 22
    summary.column_dimensions["B"].width = 32

    wb.save(path)
    return path


def save_electronic_payroll_summary_csv(output_dir: Path, package: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{package['review_id']}_V{package['version']}_04_NOMINA_ELECTRONICA_RESUMEN.csv"
    path = output_dir / filename
    # Excel en configuraciones regionales de Colombia suele usar punto y coma
    # como separador de campos porque la coma se reserva para decimales.
    # sep=; hace que Excel abra el archivo directamente en columnas.
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        fh.write("sep=;\n")
        writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["Identificación", "Nombre", "Apellido", "Devengados", "Deducciones", "Neto", "Días laborados", "Días salud"])

        def excel_decimal(value, places="0.00"):
            amount = Decimal(str(value or 0)).quantize(Decimal(places))
            return format(amount, "f").replace(".", ",")

        for employee in package.get("employees", []):
            earnings = sum(Decimal(str(v or 0)) for v in employee.get("earnings", {}).values())
            deductions = Decimal(str(employee.get("deductions", {}).get("total") or 0))
            writer.writerow([
                employee.get("identification", ""),
                employee.get("first_name", ""),
                employee.get("last_name", ""),
                excel_decimal(earnings),
                excel_decimal(deductions),
                excel_decimal(employee.get("net_payment", 0)),
                excel_decimal(employee.get("worked_days", 0)),
                excel_decimal(employee.get("health_days", 0)),
            ])
    return path
