"""Fachada de compatibilidad para la integración Siigo configurada por .env."""
from app.integrations.siigo.client import SiigoError, get_siigo_client
from app.integrations.siigo.service import integration_status, test_connection


def integration_readiness(*_args, **_kwargs):
    status = integration_status()
    return {
        **status,
        "environment_credentials_configured": status["configured"],
        "public_api_auth_supported": True,
        "public_mcp_supported": True,
        "mcp_focus": "NOMINA_Y_NOMINA_ELECTRONICA",
        "mcp_payroll_upload_supported": False,
        "electronic_payroll_public_api_endpoint_documented": False,
        "payroll_accounting_api_ready": status["payroll_accounting_configured"],
        "reason": (
            "El MCP se usa únicamente como complemento dentro del contexto de nómina y nómina electrónica; no se expone facturación en el producto. "
            "La carga de nómina de este MVP usa la API REST de comprobantes contables (/v1/journals), "
            "con aprobación humana y auditoría."
        ),
    }


def test_connection_from_env():
    return test_connection()


def list_customers(*, identification=None, page=1, page_size=10):
    return get_siigo_client().customers(identification=identification, page=page, page_size=page_size)
