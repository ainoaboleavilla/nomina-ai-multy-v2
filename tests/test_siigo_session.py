import os
import unittest
from unittest.mock import patch

from app.integrations.siigo.config import load_siigo_config
from app.integrations.siigo.client import SiigoClient, SiigoError


class SiigoConfigTests(unittest.TestCase):
    @patch.dict(os.environ, {
        "SIIGO_ENABLED": "true",
        "SIIGO_USERNAME": "api@example.com",
        "SIIGO_ACCESS_KEY": "secret",
        "SIIGO_PARTNER_ID": "NominaAI",
        "SIIGO_LIVE_PAYROLL_JOURNAL_ENABLED": "false",
    }, clear=False)
    def test_env_configuration_is_loaded(self):
        cfg = load_siigo_config()
        self.assertTrue(cfg.enabled)
        self.assertTrue(cfg.credentials_configured)
        self.assertFalse(cfg.live_payroll_journal_enabled)
        self.assertEqual(cfg.partner_id, "NominaAI")

    @patch.dict(os.environ, {
        "SIIGO_ENABLED": "true",
        "SIIGO_USERNAME": "api@example.com",
        "SIIGO_ACCESS_KEY": "secret",
        "SIIGO_PARTNER_ID": "NominaAI",
        "SIIGO_LIVE_PAYROLL_JOURNAL_ENABLED": "false",
    }, clear=False)
    def test_live_payroll_upload_is_blocked_by_default(self):
        client = SiigoClient(load_siigo_config())
        with self.assertRaises(SiigoError):
            client.create_journal({"document": {"id": 1}, "date": "2026-09-07", "items": []})


if __name__ == "__main__":
    unittest.main()

class SiigoNetworkSafetyTests(unittest.TestCase):
    @patch.dict(os.environ, {
        "SIIGO_ENABLED": "true", "SIIGO_USERNAME": "api@example.com",
        "SIIGO_ACCESS_KEY": "secret", "SIIGO_PARTNER_ID": "NominaAI",
        "SIIGO_LIVE_PAYROLL_JOURNAL_ENABLED": "true",
    }, clear=False)
    def test_write_timeout_is_not_retried_and_becomes_uncertain(self):
        from app.integrations.siigo.client import SiigoUncertainWriteError
        client = SiigoClient(load_siigo_config())
        client._token = "token"
        client._token_expires_at = 9999999999
        with patch.object(client, "_request_once", side_effect=__import__('app.integrations.siigo.client', fromlist=['SiigoConnectionError']).SiigoConnectionError("timeout")) as mocked:
            with self.assertRaises(SiigoUncertainWriteError):
                client.create_journal({"document": {"id": 1}, "date": "2026-09-16", "items": []}, "Nomina123")
            self.assertEqual(mocked.call_count, 1)

    @patch.dict(os.environ, {
        "SIIGO_ENABLED": "true", "SIIGO_USERNAME": "api@example.com",
        "SIIGO_ACCESS_KEY": "secret", "SIIGO_PARTNER_ID": "NominaAI",
    }, clear=False)
    def test_get_retries_transient_connection_error(self):
        from app.integrations.siigo.client import SiigoConnectionError
        client = SiigoClient(load_siigo_config())
        client._token = "token"
        client._token_expires_at = 9999999999
        with patch.object(client, "_request_once", side_effect=[SiigoConnectionError("timeout"), {"results": []}]) as mocked:
            result = client.customers("123")
            self.assertEqual(result, {"results": []})
            self.assertEqual(mocked.call_count, 2)
