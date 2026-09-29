from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.historical_validation_service import validate_historical_folder

parser = argparse.ArgumentParser(description="Valida nóminas históricas contra payroll_engine.py")
parser.add_argument("folder", nargs="?", default=str(ROOT / "data" / "historical"))
parser.add_argument("--tolerance", type=float, default=0.01)
parser.add_argument("--output", default=str(ROOT / "data" / "historical_validation_report.json"))
args = parser.parse_args()

report = validate_historical_folder(Path(args.folder), tolerance=args.tolerance)
Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: report[k] for k in [
    "files_found", "files_validated", "files_with_error", "total_compared",
    "total_matched", "total_differences", "global_match_rate"
]}, ensure_ascii=False, indent=2))
print(f"Reporte: {args.output}")
