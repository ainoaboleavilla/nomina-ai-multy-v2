import os
import unittest
from unittest.mock import patch

from app.services.siigo_payroll_accounting_service import build_payroll_journal, siigo_payload


class PayrollJournalTests(unittest.TestCase):
    def _env(self):
        return {
            "SIIGO_PAYROLL_JOURNAL_DOCUMENT_ID": "123",
            "SIIGO_PAYROLL_JOURNAL_DOCUMENT_CODE": "992",
            "SIIGO_PAYROLL_ACCOUNTING_MAPPING": "app/config/payroll_accounting_multy.json",
        }

    def test_balanced_payroll_journal_admin(self):
        # 1000 salario + 100 horas extra + 50 bonificación = 1150 débitos
        # 40 salud + 40 pensión + 20 préstamos + 1050 neto = 1150 créditos
        result = {"rows": [{
            "cedula": "123", "nombre": "Ana", "apellido": "Gomez",
            "payroll_group": "Administración",
            "salario_quincenal": 1000, "pago_horas_extra": 100,
            "sub_trans_quincenal": 0, "bonificacion": 50,
            "dominical": 0, "comisiones": 0,
            "salud_empleado": 40, "pension_empleado": 40,
            "prestamos": 20, "total": 1050,
        }]}
        with patch.dict(os.environ, self._env(), clear=False):
            journal = build_payroll_journal(result, journal_date="2026-09-12")
        self.assertEqual(journal["_summary"]["difference"], 0.0)
        self.assertEqual(journal["_summary"]["document_code"], "CC-992")
        self.assertEqual(siigo_payload(journal)["document"]["id"], 123)
        accounts = [x["account"]["code"] for x in journal["items"]]
        self.assertIn("51050601", accounts)
        self.assertIn("51051501", accounts)
        self.assertIn("51054801", accounts)
        self.assertIn("23700501", accounts)
        self.assertIn("23803001", accounts)
        self.assertIn("25050501", accounts)
        self.assertNotIn("_summary", siigo_payload(journal))

    def test_ventas_uses_52_accounts(self):
        result = {"rows": [{
            "cedula": "555", "nombre": "Venta", "apellido": "Uno",
            "payroll_group": "Ventas",
            "salario_quincenal": 1000, "pago_horas_extra": 0,
            "sub_trans_quincenal": 0, "bonificacion": 0,
            "dominical": 0, "comisiones": 100,
            "salud_empleado": 40, "pension_empleado": 40,
            "prestamos": 0, "total": 1020,
        }]}
        with patch.dict(os.environ, self._env(), clear=False):
            journal = build_payroll_journal(result, journal_date="2026-09-12")
        accounts = [x["account"]["code"] for x in journal["items"]]
        self.assertIn("52050601", accounts)
        self.assertIn("52950501", accounts)
        self.assertEqual(journal["_summary"]["difference"], 0.0)


if __name__ == "__main__":
    unittest.main()
