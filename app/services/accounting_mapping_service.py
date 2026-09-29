from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MAPPING = BASE_DIR / "app" / "config" / "payroll_accounting_multy.json"


class AccountingMappingError(ValueError):
    pass


def _mapping_path() -> Path:
    raw = (os.getenv("SIIGO_PAYROLL_ACCOUNTING_MAPPING") or "").strip()
    return Path(raw) if raw else DEFAULT_MAPPING


@lru_cache(maxsize=4)
def _load_from_path(path_text: str) -> dict:
    path = Path(path_text)
    if not path.exists():
        raise AccountingMappingError(f"No existe el archivo de parametrización contable: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AccountingMappingError(f"No fue posible leer la parametrización contable: {exc}") from exc
    if not isinstance(data, dict):
        raise AccountingMappingError("La parametrización contable debe ser un objeto JSON.")
    return data


def load_accounting_mapping() -> dict:
    return _load_from_path(str(_mapping_path().resolve()))


def available_groups() -> list[str]:
    return list((load_accounting_mapping().get("groups") or {}).keys())


def normalize_group(value: str | None) -> str:
    raw = str(value or "").strip()
    for group in available_groups():
        if group.casefold() == raw.casefold():
            return group
    return raw


def group_accounts(group: str) -> dict:
    normalized = normalize_group(group)
    accounts = (load_accounting_mapping().get("groups") or {}).get(normalized)
    if not accounts:
        raise AccountingMappingError(
            f"El grupo de nómina '{group or 'SIN GRUPO'}' no está parametrizado. "
            f"Grupos permitidos: {', '.join(available_groups())}."
        )
    return accounts


def account_for(group: str, concept: str, *, required: bool = True) -> str:
    account = str(group_accounts(group).get(concept) or "").strip()
    if required and not account:
        raise AccountingMappingError(
            f"Falta parametrizar la cuenta '{concept}' para el grupo '{normalize_group(group)}'. "
            "No se enviará un comprobante incompleto a Siigo."
        )
    return account


def fund_accounts(fund: str) -> dict:
    data = (load_accounting_mapping().get("funds") or {}).get(fund)
    if not data:
        raise AccountingMappingError(f"El fondo '{fund}' no está parametrizado.")
    return data


def arl_liability(provider: str | None) -> str:
    data = fund_accounts("arl")
    provider_key = str(provider or "").strip().upper()
    by_provider = {str(k).strip().upper(): v for k, v in (data.get("liability_by_provider") or {}).items()}
    return str(by_provider.get(provider_key) or data.get("default_liability") or "").strip()


def provision_accounts(name: str) -> dict:
    data = (load_accounting_mapping().get("provisions") or {}).get(name)
    if not data:
        raise AccountingMappingError(f"La provisión '{name}' no está parametrizada.")
    return data


def document_code(kind: str) -> str:
    code = str((load_accounting_mapping().get("document_codes") or {}).get(kind) or "").strip()
    if not code:
        raise AccountingMappingError(f"No hay código de comprobante configurado para '{kind}'.")
    return code


def payroll_payable_account() -> str:
    value = str(load_accounting_mapping().get("payroll_payable_account") or "").strip()
    if not value:
        raise AccountingMappingError("Falta la cuenta de nómina por pagar en la parametrización.")
    return value


def mapping_status() -> dict:
    data = load_accounting_mapping()
    return {
        "company": data.get("company"),
        "verified_on": data.get("verified_on"),
        "groups": available_groups(),
        "document_codes": data.get("document_codes") or {},
        "payroll_payable_account": data.get("payroll_payable_account"),
        "path": str(_mapping_path()),
    }
