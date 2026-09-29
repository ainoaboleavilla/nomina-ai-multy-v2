import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from openpyxl import Workbook, load_workbook

import app.services.employee_service as employee_service
from app.services.novelty_service import read_novelties_excel, calculate_novelties, generate_all_novelty_files


class NoveltiesFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.old_store = employee_service.STORE
        employee_service.STORE = Path(self.tmp.name) / "employees.json"

    def tearDown(self):
        employee_service.STORE = self.old_store
        self.tmp.cleanup()

    def test_reads_novelties_and_calculates_full_roster(self):
        employee_service.upsert_employee({
            "document": "999", "name": "Empleado Sin Novedad", "salary_base": "2000000",
            "payroll_group": "Administración", "bank": "Banco", "bank_account": "111",
        })
        with TemporaryDirectory() as td:
            p = Path(td) / "novedades.xlsx"
            wb = Workbook(); ws = wb.active
            ws.append(['documento','empleado','salario_base','dias_trabajados','horas_extra','bonificacion','descuento','banco','cuenta'])
            ws.append(['123','Prueba Empleado',3000000,15,4,100000,50000,'Banco','999'])
            wb.save(p)
            rows = read_novelties_excel(p)
            result = calculate_novelties(rows)
            self.assertEqual(result['summary']['entrada'], 'NOVEDADES + MAESTRO_EMPLEADOS')
            self.assertEqual(result['summary']['empleados'], 1)
            self.assertEqual(result['summary']['con_novedades'], 0)
            self.assertEqual(result['summary']['sin_novedades'], 1)
            docs = {r['cedula'] for r in result['rows']}
            self.assertEqual(docs, {'999'})

    def test_generates_three_outputs_with_more_than_32_employees(self):
        for i in range(1, 41):
            employee_service.upsert_employee({
                "document": str(1000+i), "name": f"Empleado {i}", "salary_base": "2500000",
                "payroll_group": "Administración", "bank": "Banco", "bank_account": str(9000+i),
            })
        result = calculate_novelties([{
            'documento':'1001','empleado':'Empleado 1','salario_base':2500000,'dias_trabajados':15,
            'horas_extra':2,'bonificacion':0,'descuento':0,'banco':'Banco','cuenta':'9001'
        }])
        self.assertEqual(result['summary']['empleados'], 40)
        files = generate_all_novelty_files(result, 'TESTNOV', 1)
        self.assertTrue(files['calculation'].exists())
        self.assertTrue(files['signature'].exists())
        self.assertTrue(files['bank'].exists())
        wb = load_workbook(files['calculation'], data_only=True)
        ws = wb.active
        self.assertEqual(ws['A1'].value, 'Nombre')
        self.assertEqual(ws['Z1'].value, 'Total')
        self.assertEqual(sum(1 for r in range(2, 42) if ws.cell(r, 3).value), 40)
        self.assertIsNotNone(ws.cell(43, 26).value)

    def test_33_employees_with_only_4_novelties_still_outputs_33(self):
        for i in range(1, 34):
            employee_service.upsert_employee({
                "document": str(5000+i), "name": f"Trabajador {i}", "salary_base": "2000000",
                "payroll_group": "Administración", "bank": "Banco", "bank_account": str(8000+i),
            })
        novelties = []
        for i in range(1, 5):
            novelties.append({
                "documento": str(5000+i), "empleado": f"Trabajador {i}", "dias_trabajados": 15,
                "horas_extra": i, "bonificacion": 0, "descuento": 0
            })
        result = calculate_novelties(novelties)
        self.assertEqual(result["summary"]["empleados"], 33)
        self.assertEqual(result["summary"]["con_novedades"], 4)
        self.assertEqual(result["summary"]["sin_novedades"], 29)
        files = generate_all_novelty_files(result, "TEST33", 1)
        wb = load_workbook(files["calculation"], data_only=True)
        ws = wb.active
        self.assertEqual(sum(1 for r in range(2, 35) if ws.cell(r, 3).value), 33)

    def test_novelties_cannot_become_master_when_roster_empty(self):
        with self.assertRaises(ValueError):
            calculate_novelties([{
                "documento":"123", "empleado":"Solo Novedad", "salario_base":2000000,
                "dias_trabajados":15, "horas_extra":0, "bonificacion":0, "descuento":0
            }])


if __name__ == '__main__':
    unittest.main()
