import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from openpyxl import Workbook

from app.services.delivery_service import build_delivery_folder


class DeliveryServiceTest(unittest.TestCase):
    def test_builds_expected_delivery_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output = base / "data" / "output"
            output.mkdir(parents=True)

            source = base / "input.xlsx"
            wb = Workbook()
            wb.active.title = "AGOSTO 15-30"
            wb.save(source)

            generated = {}
            for key, name in {
                "calculation": "calc.xlsx",
                "signature": "firma.xlsx",
                "bank": "banco.xlsx",
            }.items():
                p = output / name
                wb = Workbook()
                wb.save(p)
                generated[key] = name

            result = build_delivery_folder(
                base_dir=base,
                input_path=source,
                generated_files=generated,
                output_dir=output,
                review_id="REV1",
                version=1,
            )

            folder = result["folder"]
            self.assertTrue((folder / "Comprobantes").is_dir())
            self.assertTrue((folder / "Liquidaciones").is_dir())
            self.assertTrue((folder / "2026_CALCULO_DE_NOMINA_AGOSTO_15-30.xlsx").exists())
            self.assertTrue((folder / "FORMATO_NOMINA_FIRMA_AGOSTO_15-30.xlsx").exists())
            self.assertTrue((folder / "Plantilla_BANCO-Pagos-Nomina_AGOSTO_15-30.xlsx").exists())
            self.assertTrue(result["zip"].exists())

            with ZipFile(result["zip"]) as zf:
                names = set(zf.namelist())
                root = "ENTREGA_NOMINA_AGOSTO_15-30_V1/"
                self.assertIn(root + "Comprobantes/", names)
                self.assertIn(root + "Liquidaciones/", names)


if __name__ == "__main__":
    unittest.main()
