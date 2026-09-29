from __future__ import annotations

from .config import load_siigo_config
from .client import get_siigo_client
from app.services.accounting_mapping_service import mapping_status


def integration_status() -> dict:
    cfg = load_siigo_config()
    masked = ""
    if cfg.username:
        if "@" in cfg.username:
            left, right = cfg.username.split("@", 1)
            masked = (left[:2] + "***@" + right) if left else "***@" + right
        else:
            masked = cfg.username[:2] + "***"
    try:
        mapping = mapping_status()
        mapping_ok = True
    except Exception as exc:
        mapping = {"error": str(exc), "groups": []}
        mapping_ok = False
    return {
        "enabled": cfg.enabled,
        "configured": cfg.credentials_configured,
        "username_masked": masked,
        "partner_id_configured": bool(cfg.partner_id),
        "base_url": cfg.base_url,
        "live_payroll_journal_enabled": cfg.live_payroll_journal_enabled,
        "payroll_accounting_configured": cfg.payroll_accounting_configured and mapping_ok,
        "payroll_journal_document_id": cfg.payroll_journal_document_id,
        "payroll_journal_document_code": cfg.payroll_journal_document_code,
        "payroll_cost_center_id": cfg.payroll_cost_center_id,
        "accounting_mapping": mapping,
    }


def test_connection() -> dict:
    client = get_siigo_client()
    token = client.get_token(force_refresh=True)
    types = client.journal_document_types()
    count = len(types) if isinstance(types, list) else len(types.get("results", [])) if isinstance(types, dict) else 0
    payroll_doc = client.resolve_journal_document_type(load_siigo_config().payroll_journal_document_code)
    return {
        "ok": True,
        "token_received": bool(token),
        "journal_document_types_found": count,
        "payroll_document": {
            "id": payroll_doc.get("id"),
            "code": load_siigo_config().payroll_journal_document_code,
            "name": payroll_doc.get("name") or payroll_doc.get("description"),
        },
    }
