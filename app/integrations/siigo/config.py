from __future__ import annotations
import os
from dataclasses import dataclass


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


@dataclass(frozen=True)
class SiigoConfig:
    enabled: bool
    base_url: str
    username: str
    access_key: str
    partner_id: str
    company_nit: str
    company_name: str
    live_payroll_journal_enabled: bool
    payroll_journal_document_id: str
    payroll_journal_document_code: str
    provisions_document_code: str
    contract_settlement_document_code: str
    severance_settlement_document_code: str
    payroll_payout_document_code: str
    payroll_cost_center_id: str
    accounting_mapping_path: str

    @property
    def credentials_configured(self) -> bool:
        return bool(self.username and self.access_key and self.partner_id)

    @property
    def payroll_accounting_configured(self) -> bool:
        # Las cuentas ya no se declaran una a una en .env. Se leen del mapa contable versionado.
        return bool(self.payroll_journal_document_code or self.payroll_journal_document_id)


def load_siigo_config() -> SiigoConfig:
    return SiigoConfig(
        enabled=_truthy(os.getenv("SIIGO_ENABLED", "false")),
        base_url=(os.getenv("SIIGO_BASE_URL") or "https://api.siigo.com").strip().rstrip("/"),
        username=(os.getenv("SIIGO_USERNAME") or "").strip(),
        access_key=(os.getenv("SIIGO_ACCESS_KEY") or "").strip(),
        partner_id=(os.getenv("SIIGO_PARTNER_ID") or "NominaAI").strip(),
        company_nit=(os.getenv("SIIGO_COMPANY_NIT") or "").strip(),
        company_name=(os.getenv("SIIGO_COMPANY_NAME") or "GRUPO MULTY SAS").strip(),
        live_payroll_journal_enabled=_truthy(os.getenv("SIIGO_LIVE_PAYROLL_JOURNAL_ENABLED", "false")),
        payroll_journal_document_id=(os.getenv("SIIGO_PAYROLL_JOURNAL_DOCUMENT_ID") or "").strip(),
        payroll_journal_document_code=(os.getenv("SIIGO_PAYROLL_JOURNAL_DOCUMENT_CODE") or "992").strip(),
        provisions_document_code=(os.getenv("SIIGO_PROVISIONS_DOCUMENT_CODE") or "993").strip(),
        contract_settlement_document_code=(os.getenv("SIIGO_CONTRACT_SETTLEMENT_DOCUMENT_CODE") or "994").strip(),
        severance_settlement_document_code=(os.getenv("SIIGO_SEVERANCE_SETTLEMENT_DOCUMENT_CODE") or "996").strip(),
        payroll_payout_document_code=(os.getenv("SIIGO_PAYROLL_PAYOUT_DOCUMENT_CODE") or "997").strip(),
        payroll_cost_center_id=(os.getenv("SIIGO_PAYROLL_COST_CENTER_ID") or "").strip(),
        accounting_mapping_path=(os.getenv("SIIGO_PAYROLL_ACCOUNTING_MAPPING") or "app/config/payroll_accounting_multy.json").strip(),
    )
