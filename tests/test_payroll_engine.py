import importlib.util
import sys
import re
import unittest
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "app" / "services" / "payroll_engine.py"
spec = importlib.util.spec_from_file_location("payroll_engine_standalone", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine
spec.loader.exec_module(engine)

PayrollInputs = engine.PayrollInputs
calculate = engine.calculate
build_inputs = engine.build_inputs


class PayrollEngineTests(unittest.TestCase):
    def test_basic_formula_parity(self):
        inputs = PayrollInputs(
            nombre="Prueba", apellido="Empleado", cedula="1",
            salario_basico=Decimal("1750905"),
            aux_transporte=Decimal("249095"),
            dias_laborales=Decimal("15"),
            dnj=Decimal("0"), dj=Decimal("0"), dias_salud=Decimal("15"),
            prestamos=Decimal("0"), no_salarial=Decimal("160000"),
            dias_dominical=Decimal("0"), comisiones=Decimal("0"),
        )
        result = calculate(inputs)
        self.assertEqual(result.dias_novedad, Decimal("0"))
        self.assertEqual(result.dias_laborados, Decimal("15"))
        self.assertEqual(result.total, result.pago_total_nomina)
        self.assertEqual(result.dispersion_banco, result.pago_total_nomina)

    def test_sanitized_template_has_historical_headers(self):
        path = ROOT / "templates_excel" / "2026_CALCULO_DE_NOMINA.xlsx"
        wb = load_workbook(path, data_only=False)
        ws = wb.active
        expected = [
            "Nombre", "Apellido", "cedula / ppt", "Salario básico",
            "Auxilio de transporte ", "Dias Laborales",
            "Días Novedad No Justificada", "Novedad Justificada", "Dias Novedad",
            "Dias Laborados", "Sub de trans quincenal ", "Salario quincenal ",
            "Total ingreso", "Dias salud", "aportes", "Prestamos ", "No salarial",
            "No salarial Quincenal", "Total deducciones", "Dispersion Banco",
            "Pago Total nomina", "# de dias Dominical", "Valor dia dominical",
            "Dominical", "Comisiones Vendedores", "Total"
        ]
        self.assertEqual([ws.cell(1, c).value for c in range(1, 27)], expected)
        self.assertEqual(len(wb.sheetnames), 1)
        for r in range(2, ws.max_row + 1):
            for c in range(1, 27):
                value = ws.cell(r, c).value
                self.assertTrue(value is None or (isinstance(value, str) and value.startswith("=")))



if __name__ == "__main__":
    unittest.main()
