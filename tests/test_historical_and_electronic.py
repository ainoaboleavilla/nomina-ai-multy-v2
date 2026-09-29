import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import app.services.employee_service as employee_service

from app.services.historical_validation_service import validate_historical_workbook
from app.services.novelty_service import process_novelties_file
from app.services.electronic_payroll_service import build_electronic_payroll_package, save_electronic_payroll_summary_csv, save_electronic_payroll_summary_xlsx

ROOT = Path(__file__).resolve().parents[1]


class HistoricalAndElectronicTests(unittest.TestCase):
    def test_calculation_template_is_sanitized_output_template(self):
        from openpyxl import load_workbook
        path = ROOT / "templates_excel" / "2026_CALCULO_DE_NOMINA.xlsx"
        wb = load_workbook(path, data_only=False)
        ws = wb.active
        self.assertEqual(ws.cell(1, 1).value, "Nombre")
        self.assertEqual(ws.cell(1, 26).value, "Total")
        self.assertIsNone(ws.cell(2, 1).value)
        self.assertIsNone(ws.cell(2, 3).value)

    def test_electronic_package_is_prepared_not_transmitted(self):
        old_store = employee_service.STORE
        with TemporaryDirectory() as td:
            employee_service.STORE = Path(td) / "employees.json"
            for i in range(1, 5):
                employee_service.upsert_employee({
                    "document": str(1000+i), "name": f"Empleado {i}", "salary_base": "2000000",
                    "payroll_group": "Administración", "bank": "Banco", "bank_account": str(9000+i),
                })
            path = ROOT / "data" / "novedades_demo.xlsx"
            # Este test usa las novedades demo solo para validar el paquete, pero la planta
            # se toma del maestro, no del archivo de novedades.
            result = process_novelties_file(path)
            package = build_electronic_payroll_package(
                result, "TEST", 1, "2026-08-01", "2026-08-15",
                {"nit": "900000000", "name": "Empresa Demo"},
            )
            self.assertEqual(package["status"], "READY_FOR_PROVIDER_ADAPTER")
            self.assertEqual(package["transmission"]["provider"], "SIIGO")
            self.assertTrue(package["validation"]["is_valid"])
            self.assertTrue(package["transmission"]["human_approval_required"])
            self.assertEqual(len(package["employees"]), result["summary"]["empleados"])
        employee_service.STORE = old_store

    def test_electronic_control_xlsx_preserves_accents_and_columns(self):
        from openpyxl import load_workbook
        package = {
            "review_id": "XLSXTEST", "version": 1,
            "period": {"start": "2026-09-01", "end": "2026-09-30"},
            "employer": {"name": "GRUPO MULTY SAS", "nit": "900123456"},
            "validation": {"is_valid": True, "employee_count": 1, "totals": {"earnings": 1000.5, "deductions": 80.25, "net": 920.25}},
            "employees": [{
                "identification": "00123", "first_name": "Ana María", "last_name": "Pérez Gómez",
                "earnings": {"salary": 1000.5}, "deductions": {"total": 80.25},
                "net_payment": 920.25, "worked_days": 30, "health_days": 30
            }]
        }
        with TemporaryDirectory() as td:
            path = save_electronic_payroll_summary_xlsx(Path(td), package)
            wb = load_workbook(path, data_only=True)
            ws = wb["Control nómina electrónica"]
            self.assertEqual(ws["A1"].value, "Identificación")
            self.assertEqual(ws["A2"].value, "00123")
            self.assertEqual(ws["B2"].value, "Ana María")
            self.assertEqual(ws["C2"].value, "Pérez Gómez")
            self.assertEqual(ws["D2"].value, 1000.5)
            self.assertEqual(wb["Resumen"]["B2"].value, 1)


    def test_electronic_summary_csv_opens_in_excel_columns(self):
        import tempfile
        from pathlib import Path
        package = {
            "review_id": "CSVTEST", "version": 1,
            "employees": [{
                "identification": "123", "first_name": "Ana María", "last_name": "Pérez",
                "earnings": {"salary": 1000.5}, "deductions": {"total": 80.25},
                "net_payment": 920.25, "worked_days": 30, "health_days": 30
            }]
        }
        with tempfile.TemporaryDirectory() as td:
            path = save_electronic_payroll_summary_csv(Path(td), package)
            text = path.read_text(encoding="utf-8-sig")
            lines = text.splitlines()
            self.assertEqual(lines[0], "sep=;")
            self.assertIn("Identificación;Nombre;Apellido;Devengados", lines[1])
            self.assertIn("123;Ana María;Pérez;1000,50;80,25;920,25", lines[2])


if __name__ == "__main__":
    unittest.main()
