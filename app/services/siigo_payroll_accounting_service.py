from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from app.integrations.siigo.client import SiigoError, SiigoUncertainWriteError, get_siigo_client
from app.integrations.siigo.config import load_siigo_config
from app.services.accounting_mapping_service import (
    AccountingMappingError,
    account_for,
    document_code,
    fund_accounts,
    payroll_payable_account,
)
from app.services.employee_service import get_employee

BASE_DIR = Path(__file__).resolve().parents[2]
OUT_DIR = BASE_DIR / "data" / "siigo" / "payroll_journals"


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _add(items: list[dict], *, account: str, movement: str, identification: str,
         value, description: str, cost_center: str = "") -> None:
    amount = _money(value)
    if amount == 0:
        return
    if not account:
        raise SiigoError(f"No hay cuenta contable para: {description}")
    item = {
        "account": {"code": account, "movement": movement},
        "customer": {"identification": str(identification), "branch_office": 0},
        "description": description[:500],
        "value": float(amount),
    }
    if cost_center:
        item["cost_center"] = int(cost_center)
    items.append(item)


def _resolve_payroll_document_id() -> tuple[int, str]:
    cfg = load_siigo_config()
    if cfg.payroll_journal_document_id:
        return int(cfg.payroll_journal_document_id), cfg.payroll_journal_document_code or "992"
    code = cfg.payroll_journal_document_code or document_code("payroll_accrual")
    doc = get_siigo_client().resolve_journal_document_type(code)
    return int(doc["id"]), code


def build_payroll_journal(result: dict, *, journal_date: str | None = None) -> dict:
    """Construye CC-992 usando el grupo real del empleado y el mapa contable de Siigo.

    No usa cuentas genéricas SIIGO_ACCOUNT_*; las cuentas salen de
    app/config/payroll_accounting_multy.json.
    """
    cfg = load_siigo_config()
    try:
        document_id, visible_code = _resolve_payroll_document_id()
    except (AccountingMappingError, ValueError) as exc:
        raise SiigoError(str(exc)) from exc

    journal_date = journal_date or date.today().isoformat()
    items: list[dict] = []
    cc = cfg.payroll_cost_center_id
    health_liability = str(fund_accounts("health").get("liability") or "")
    pension_liability = str(fund_accounts("pension").get("liability") or "")
    payable = payroll_payable_account()
    groups_used: set[str] = set()

    for row in result.get("rows", []):
        ident = str(row.get("cedula") or "").strip()
        if not ident:
            raise SiigoError("Hay un empleado sin identificación; no se puede crear el comprobante contable.")
        employee = get_employee(ident) or {}
        group = str(row.get("payroll_group") or employee.get("payroll_group") or "").strip()
        if not group:
            raise SiigoError(
                f"El empleado {ident} no tiene grupo de nómina. Completa Administración, Ventas o Producción antes de contabilizar."
            )
        groups_used.add(group)
        label = f"Nómina {row.get('nombre','')} {row.get('apellido','')}".strip()

        try:
            _add(items, account=account_for(group, "salary"), movement="Debit", identification=ident,
                 value=row.get("salario_quincenal"), description=f"{label} - sueldo", cost_center=cc)
            _add(items, account=account_for(group, "overtime_and_surcharges"), movement="Debit", identification=ident,
                 value=(row.get("pago_horas_extra") or 0) + (row.get("dominical") or 0),
                 description=f"{label} - horas extra y recargos", cost_center=cc)
            _add(items, account=account_for(group, "transport"), movement="Debit", identification=ident,
                 value=row.get("sub_trans_quincenal"), description=f"{label} - auxilio transporte", cost_center=cc)
            _add(items, account=account_for(group, "bonus"), movement="Debit", identification=ident,
                 value=row.get("bonificacion") or row.get("no_salarial_quincenal"), description=f"{label} - bonificación", cost_center=cc)
            if _money(row.get("comisiones")):
                _add(items, account=account_for(group, "commission"), movement="Debit", identification=ident,
                     value=row.get("comisiones"), description=f"{label} - comisiones", cost_center=cc)
        except AccountingMappingError as exc:
            raise SiigoError(str(exc)) from exc

        # Deducciones del trabajador separadas para no usar una cuenta genérica de aportes.
        _add(items, account=health_liability, movement="Credit", identification=ident,
             value=row.get("salud_empleado"), description=f"{label} - salud empleado", cost_center=cc)
        _add(items, account=pension_liability, movement="Credit", identification=ident,
             value=row.get("pension_empleado"), description=f"{label} - pensión empleado", cost_center=cc)

        # Otros descuentos/préstamos: conserva la cuenta observada en la parametrización de Siigo.
        if _money(row.get("prestamos")):
            try:
                loan_account = account_for(group, "loan")
            except AccountingMappingError as exc:
                raise SiigoError(str(exc)) from exc
            _add(items, account=loan_account, movement="Credit", identification=ident,
                 value=row.get("prestamos"), description=f"{label} - préstamos/descuentos", cost_center=cc)

        _add(items, account=payable, movement="Credit", identification=ident,
             value=row.get("total"), description=f"{label} - salarios por pagar", cost_center=cc)

    debit = sum((_money(x["value"]) for x in items if x["account"]["movement"] == "Debit"), Decimal("0"))
    credit = sum((_money(x["value"]) for x in items if x["account"]["movement"] == "Credit"), Decimal("0"))
    difference = (debit - credit).quantize(Decimal("0.01"))
    if difference != 0:
        raise SiigoError(
            f"El comprobante CC-{visible_code} no está balanceado. Débitos={debit} Créditos={credit} Diferencia={difference}. "
            "No se enviará a Siigo hasta corregir la liquidación o la parametrización."
        )

    # Resumen de control para revisión humana antes de cualquier envío real.
    # Se agrupa exactamente lo que irá en `items`; no recalcula la nómina.
    employee_group = {}
    for row in result.get("rows", []):
        ident = str(row.get("cedula") or "").strip()
        employee = get_employee(ident) or {}
        employee_group[ident] = str(row.get("payroll_group") or employee.get("payroll_group") or "").strip()

    grouped: dict[tuple[str, str, str, str], Decimal] = {}
    for item in items:
        ident = str((item.get("customer") or {}).get("identification") or "").strip()
        group = employee_group.get(ident, "")
        account = str((item.get("account") or {}).get("code") or "")
        movement = str((item.get("account") or {}).get("movement") or "")
        description = str(item.get("description") or "")
        concept = description.rsplit(" - ", 1)[-1] if " - " in description else description
        key = (group, account, movement, concept)
        grouped[key] = grouped.get(key, Decimal("0")) + _money(item.get("value"))

    accounting_lines = [
        {
            "group": group,
            "account": account,
            "movement": movement,
            "concept": concept,
            "debit": float(value if movement == "Debit" else Decimal("0")),
            "credit": float(value if movement == "Credit" else Decimal("0")),
        }
        for (group, account, movement, concept), value in sorted(grouped.items())
    ]

    return {
        "document": {"id": document_id},
        "date": journal_date,
        "items": items,
        "observations": f"Nómina aprobada en Nómina AI. Causación según CC-{visible_code} y parametrización real por grupo.",
        "_summary": {
            "document_code": f"CC-{visible_code}",
            "employees": len(result.get("rows", [])),
            "groups": sorted(groups_used),
            "item_count": len(items),
            "debit": float(debit),
            "credit": float(credit),
            "difference": float(difference),
            "accounting_lines": accounting_lines,
        },
    }


def siigo_payload(journal: dict) -> dict:
    return {k: v for k, v in journal.items() if not k.startswith("_")}


def validate_third_parties(result: dict) -> dict:
    client = get_siigo_client()
    missing = []
    found = []
    for row in result.get("rows", []):
        ident = str(row.get("cedula") or "").strip()
        response = client.customers(identification=ident, page=1, page_size=10)
        rows = response.get("results", []) if isinstance(response, dict) else []
        exact = next((x for x in rows if str(x.get("identification") or "").strip() == ident), None)
        if exact:
            found.append({"identification": ident, "name": f"{row.get('nombre','')} {row.get('apellido','')}".strip(), "siigo_id": exact.get("id")})
        else:
            missing.append({"identification": ident, "name": f"{row.get('nombre','')} {row.get('apellido','')}".strip()})
    return {"found": found, "missing": missing, "ok": not missing}


def save_preview(review_id: str, version: int, journal: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{review_id}_V{version}_SIIGO_COMPROBANTE_NOMINA.json"
    path.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def upload_payroll_journal(review_id: str, version: int, journal: dict) -> tuple[dict, str]:
    payload = siigo_payload(journal)
    digest = hashlib.sha256(f"{review_id}|{version}|{payload['date']}".encode()).hexdigest()[:24]
    key = f"Nomina{version}{digest}"[:30]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state_path = OUT_DIR / f"{review_id}_V{version}_SIIGO_ESTADO.json"
    state = {"status": "ENVIANDO", "idempotency_key": key, "date": payload.get("date")}
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        response = get_siigo_client().create_journal(payload, idempotency_key=key)
    except SiigoUncertainWriteError as exc:
        state.update({"status": "REQUIERE_VERIFICACION", "error": str(exc)})
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    except SiigoError as exc:
        state.update({"status": "ERROR", "error": str(exc)})
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    path = OUT_DIR / f"{review_id}_V{version}_SIIGO_RESPUESTA.json"
    path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    state.update({"status": "CONFIRMADA", "siigo_id": response.get("id"), "siigo_name": response.get("name")})
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return response, path.name
