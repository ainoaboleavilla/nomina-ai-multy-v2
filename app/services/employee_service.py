from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
STORE = BASE_DIR / "data" / "employees.json"
BOOTSTRAP_STORE = Path(os.getenv("EMPLOYEE_BOOTSTRAP_FILE", "/etc/secrets/employees.json"))

def _ensure_bootstrap_store() -> None:
    """Inicializa el maestro desde un Secret File en despliegues efímeros (Render).

    El archivo sensible NO se versiona en Git. En local se usa data/employees.json.
    En Render, si el almacenamiento local arranca vacío, se restaura desde
    /etc/secrets/employees.json (o EMPLOYEE_BOOTSTRAP_FILE).
    """
    try:
        current_ok = STORE.exists() and STORE.stat().st_size > 2
        if current_ok:
            data = json.loads(STORE.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return
        if BOOTSTRAP_STORE.exists():
            seed = json.loads(BOOTSTRAP_STORE.read_text(encoding="utf-8"))
            if isinstance(seed, list) and seed:
                STORE.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(BOOTSTRAP_STORE, STORE)
    except Exception:
        # La pantalla mostrará 0 si no existe una fuente válida; no se inventan empleados.
        return


def _read() -> list[dict]:
    _ensure_bootstrap_store()
    if not STORE.exists():
        return []
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(rows: list[dict]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_document(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return "".join(ch for ch in text if ch.isdigit()) or text


def split_name(full_name: str) -> tuple[str, str]:
    parts = [p for p in str(full_name or "").strip().split() if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


PAYSLIP_PROFILE_FIELDS = [
    ("email", "Correo"), ("phone", "Celular"), ("position", "Cargo"),
    ("contract_type", "Tipo de contrato"), ("health_provider", "EPS"),
    ("pension_provider", "AFP"), ("arl_provider", "ARL"),
    ("severance_fund", "Fondo de cesantías"), ("compensation_fund", "Caja"),
    ("bank", "Banco"), ("bank_account_type", "Tipo de cuenta"), ("bank_account", "No. cuenta"),
]

def payslip_missing_fields(employee: dict) -> list[str]:
    return [label for key,label in PAYSLIP_PROFILE_FIELDS if not str(employee.get(key) or "").strip()]

def list_employees() -> list[dict]:
    rows=_read()
    for item in rows:
        item["payslip_missing"] = payslip_missing_fields(item)
        item["payslip_complete"] = not item["payslip_missing"]
    return sorted(rows, key=lambda x: (x.get("name") or "").lower())


def list_active_employees() -> list[dict]:
    """Empleados que deben participar en cada corrida de nómina.

    `in_payroll` permite diferenciar trabajadores de otros terceros/personas que
    existan en Siigo. Los registros históricos previos sin el campo se consideran
    parte de nómina salvo que estén marcados INACTIVO.
    """
    rows = []
    for item in _read():
        if str(item.get("status") or "").upper() == "INACTIVO":
            continue
        if item.get("in_payroll") is False:
            continue
        rows.append(item)
    return sorted(rows, key=lambda x: (x.get("name") or "").lower())


def get_employee(document: str) -> dict | None:
    key = normalize_document(document)
    return next((x for x in _read() if normalize_document(x.get("document")) == key), None)


def ensure_employee_from_novelty(row: dict) -> tuple[dict, bool]:
    document = normalize_document(row.get("documento") or row.get("cedula"))
    if not document:
        raise ValueError("La novedad tiene un empleado sin documento.")
    rows = _read()
    existing = next((x for x in rows if normalize_document(x.get("document")) == document), None)
    if existing:
        changed = False
        if row.get("empleado") and not existing.get("name"):
            existing["name"] = str(row["empleado"]).strip(); changed = True
        if row.get("banco") and not existing.get("bank"):
            existing["bank"] = str(row["banco"]).strip(); changed = True
        if row.get("cuenta") and not existing.get("bank_account"):
            existing["bank_account"] = str(row["cuenta"]).strip(); changed = True
        if row.get("salario_base") not in (None, ""):
            existing["salary_base"] = row.get("salario_base"); changed = True
        if row.get("grupo_nomina") and not existing.get("payroll_group"):
            existing["payroll_group"] = str(row.get("grupo_nomina") or "").strip(); changed = True
        existing.setdefault("in_payroll", False)
        existing.setdefault("roster_verified", False)
        existing.setdefault("source", "NOVEDAD")
        if changed:
            existing["updated_at"] = datetime.now(timezone.utc).isoformat()
            _write(rows)
        return existing, False

    first, last = split_name(row.get("empleado") or "")
    now = datetime.now(timezone.utc).isoformat()
    employee = {
        "document": document,
        "name": str(row.get("empleado") or "").strip(),
        "first_name": first,
        "last_name": last,
        "email": "",
        "phone": "",
        "address": "",
        "city": "",
        "position": "",
        "payroll_group": str(row.get("grupo_nomina") or "").strip(),
        "health_provider": "",
        "pension_provider": "",
        "arl_provider": "",
        "compensation_fund": "",
        "bank": str(row.get("banco") or "").strip(),
        "bank_account": str(row.get("cuenta") or "").strip(),
        "salary_base": row.get("salario_base") or 0,
        "transport_allowance": row.get("auxilio_transporte") or 0,
        "status": "NUEVO_PENDIENTE_DATOS",
        "in_payroll": False,
        "roster_verified": False,
        "source": "NOVEDAD",
        "siigo_id": "",
        "siigo_sync_status": "PENDIENTE",
        "created_at": now,
        "updated_at": now,
    }
    rows.append(employee)
    _write(rows)
    return employee, True


def upsert_employee(payload: dict) -> dict:
    document = normalize_document(payload.get("document"))
    if not document:
        raise ValueError("El documento es obligatorio.")
    rows = _read()
    existing = next((x for x in rows if normalize_document(x.get("document")) == document), None)
    if existing is None:
        existing = {"document": document, "created_at": datetime.now(timezone.utc).isoformat()}
        rows.append(existing)
    for key in [
        "name", "first_name", "last_name", "email", "phone", "address", "city",
        "position", "payroll_group", "health_provider", "pension_provider", "arl_provider",
        "compensation_fund", "severance_fund", "bank", "bank_account", "bank_account_type", "bank_code",
        "id_type", "payment_email", "payment_reference", "payment_description",
        "contract_number", "contract_start", "contract_end", "contract_type", "salary_type",
        "salary_base", "transport_allowance",
    ]:
        if key in payload:
            existing[key] = str(payload.get(key) or "").strip()
    if "in_payroll" in payload:
        existing["in_payroll"] = bool(payload.get("in_payroll"))
    else:
        existing.setdefault("in_payroll", True)
    existing.setdefault("roster_verified", True)
    existing.setdefault("source", "MANUAL")
    required = [existing.get("name"), existing.get("salary_base")]
    existing["status"] = "ACTIVO" if all(str(x or "").strip() not in ("", "0", "0.0") for x in required) else "NUEVO_PENDIENTE_DATOS"
    existing.setdefault("siigo_id", "")
    existing.setdefault("siigo_sync_status", "PENDIENTE")
    existing["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write(rows)
    return existing


def import_siigo_employee(candidate: dict) -> dict:
    """Importa/vincula un tercero de Siigo al maestro de empleados.

    La API pública de Siigo expone terceros, no el catálogo privado de empleados
    de Nómina Electrónica. Por seguridad este método solo se llama después de que
    el usuario confirma que el tercero corresponde a un trabajador.
    """
    document = normalize_document(candidate.get("identification"))
    if not document:
        raise ValueError("El tercero de Siigo no tiene identificación.")
    name_value = candidate.get("name")
    if isinstance(name_value, list):
        name = " ".join(str(x or "").strip() for x in name_value if str(x or "").strip())
    else:
        name = str(name_value or candidate.get("commercial_name") or "").strip()
    first, last = split_name(name)

    rows = _read()
    existing = next((x for x in rows if normalize_document(x.get("document")) == document), None)
    now = datetime.now(timezone.utc).isoformat()
    if existing is None:
        existing = {
            "document": document,
            "created_at": now,
            "salary_base": 0,
            "transport_allowance": 0,
            "bank": "",
            "bank_account": "",
            "payroll_group": "",
            "health_provider": "",
            "pension_provider": "",
            "arl_provider": "",
            "compensation_fund": "",
        }
        rows.append(existing)
    existing["name"] = name or existing.get("name") or document
    existing.setdefault("first_name", first)
    existing.setdefault("last_name", last)
    existing["siigo_id"] = str(candidate.get("id") or existing.get("siigo_id") or "")
    existing["siigo_sync_status"] = "SINCRONIZADO"
    existing["in_payroll"] = True
    existing["roster_verified"] = True
    existing["source"] = "SIIGO_API_TERCERO_CONFIRMADO"
    existing["status"] = "ACTIVO" if float(existing.get("salary_base") or 0) > 0 else "PENDIENTE_DATOS_BASE"
    existing["updated_at"] = now
    _write(rows)
    return existing


def set_payroll_membership(documents: list[str]) -> int:
    selected = {normalize_document(x) for x in documents if normalize_document(x)}
    rows = _read()
    changed = 0
    for item in rows:
        new_value = normalize_document(item.get("document")) in selected
        if bool(item.get("in_payroll", True)) != new_value:
            item["in_payroll"] = new_value
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            changed += 1
    _write(rows)
    return changed


def mark_siigo(document: str, *, siigo_id: str = "", status: str = "SINCRONIZADO") -> dict | None:
    rows = _read(); key = normalize_document(document)
    target = next((x for x in rows if normalize_document(x.get("document")) == key), None)
    if target:
        target["siigo_id"] = str(siigo_id or target.get("siigo_id") or "")
        target["siigo_sync_status"] = status
        target["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write(rows)
    return target


def active_roster_count() -> int:
    return len(list_active_employees())


def has_verified_roster() -> bool:
    rows = list_active_employees()
    return bool(rows) and any(x.get("roster_verified", True) is not False for x in rows)


def apply_roster_novelty(row: dict) -> str | None:
    """Aplica altas/retiros al maestro persistente desde NOVEDADES.

    INGRESO/ALTA: incorpora al trabajador a la planta (requiere nombre y salario base
    si todavía no existe). RETIRO/BAJA: lo conserva en histórico y lo saca de la
    planta activa. Devuelve la acción aplicada o None para novedades ordinarias.
    """
    action = str(row.get("tipo_novedad") or row.get("accion") or "").strip().upper()
    action = action.replace(" ", "_")
    if action not in {"INGRESO", "ALTA", "NUEVO", "RETIRO", "BAJA", "CAMBIO_BANCO"}:
        return None
    document = normalize_document(row.get("documento") or row.get("cedula"))
    if not document:
        raise ValueError("La novedad de ingreso/retiro requiere documento.")
    rows = _read()
    existing = next((x for x in rows if normalize_document(x.get("document")) == document), None)
    now = datetime.now(timezone.utc).isoformat()
    if action == "CAMBIO_BANCO":
        if existing is None:
            raise ValueError(f"No se puede cambiar banco de {document}: no existe en el maestro.")
        if row.get("banco") not in (None, ""): existing["bank"] = str(row.get("banco")).strip()
        if row.get("tipo_cuenta") not in (None, ""): existing["bank_account_type"] = str(row.get("tipo_cuenta")).strip().upper()
        if row.get("tipo_cuenta") not in (None, ""): existing["bank_account_type"] = str(row.get("tipo_cuenta")).strip().upper()
        if row.get("cuenta") not in (None, ""): existing["bank_account"] = str(row.get("cuenta")).strip()
        if row.get("tipo_identificacion") not in (None, ""): existing["id_type"] = str(row.get("tipo_identificacion")).strip().upper()
        if row.get("codigo_banco") not in (None, ""): existing["bank_code"] = str(row.get("codigo_banco")).strip()
        if row.get("correo_pago") not in (None, ""): existing["payment_email"] = str(row.get("correo_pago")).strip()
        if row.get("referencia_pago") not in (None, ""): existing["payment_reference"] = str(row.get("referencia_pago")).strip()
        if row.get("descripcion_pago") not in (None, ""): existing["payment_description"] = str(row.get("descripcion_pago")).strip()
        existing["updated_at"] = now; existing["source"] = "NOVEDAD_CAMBIO_BANCO"
        _write(rows)
        return "CAMBIO_BANCO"

    if action in {"RETIRO", "BAJA"}:
        if existing is None:
            raise ValueError(f"No se puede retirar {document}: no existe en el maestro.")
        existing["in_payroll"] = False
        existing["status"] = "RETIRADO_POR_NOVEDAD"
        existing["roster_verified"] = True
        existing["source"] = "NOVEDAD_RETIRO"
        existing["updated_at"] = now
        _write(rows)
        return "RETIRO"

    # INGRESO / ALTA / NUEVO
    if existing is None:
        name = str(row.get("empleado") or "").strip()
        salary = row.get("salario_base")
        if not name or salary in (None, "", 0, "0"):
            raise ValueError(f"El ingreso de {document} requiere empleado y salario_base.")
        first, last = split_name(name)
        existing = {
            "document": document, "name": name, "first_name": first, "last_name": last,
            "salary_base": salary, "transport_allowance": row.get("auxilio_transporte") or 0,
            "bank": str(row.get("banco") or "").strip(), "bank_account_type": str(row.get("tipo_cuenta") or "").strip().upper(), "bank_account": str(row.get("cuenta") or "").strip(),
            "id_type": str(row.get("tipo_identificacion") or "CC").strip().upper(), "bank_code": str(row.get("codigo_banco") or "").strip(),
            "payment_email": str(row.get("correo_pago") or "").strip(), "payment_reference": str(row.get("referencia_pago") or "NOMINA").strip(),
            "payment_description": str(row.get("descripcion_pago") or "").strip(),
            "payroll_group": str(row.get("grupo_nomina") or "").strip(), "created_at": now,
        }
        rows.append(existing)
    else:
        if row.get("empleado"): existing["name"] = str(row.get("empleado")).strip()
        if row.get("salario_base") not in (None, ""): existing["salary_base"] = row.get("salario_base")
        if row.get("banco") not in (None, ""): existing["bank"] = str(row.get("banco")).strip()
        if row.get("tipo_cuenta") not in (None, ""): existing["bank_account_type"] = str(row.get("tipo_cuenta")).strip().upper()
        if row.get("cuenta") not in (None, ""): existing["bank_account"] = str(row.get("cuenta")).strip()
        if row.get("tipo_identificacion") not in (None, ""): existing["id_type"] = str(row.get("tipo_identificacion")).strip().upper()
        if row.get("codigo_banco") not in (None, ""): existing["bank_code"] = str(row.get("codigo_banco")).strip()
        if row.get("correo_pago") not in (None, ""): existing["payment_email"] = str(row.get("correo_pago")).strip()
        if row.get("referencia_pago") not in (None, ""): existing["payment_reference"] = str(row.get("referencia_pago")).strip()
        if row.get("descripcion_pago") not in (None, ""): existing["payment_description"] = str(row.get("descripcion_pago")).strip()
    existing["in_payroll"] = True
    existing["status"] = "ACTIVO"
    existing["roster_verified"] = True
    existing["source"] = "NOVEDAD_INGRESO"
    existing["updated_at"] = now
    _write(rows)
    return "INGRESO"
