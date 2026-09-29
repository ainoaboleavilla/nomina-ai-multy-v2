import json
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parents[2]
PATH = BASE_DIR / 'data' / 'novelties_draft.json'

def list_draft():
    if not PATH.exists(): return []
    try: return json.loads(PATH.read_text(encoding='utf-8'))
    except Exception: return []

def save(rows):
    PATH.parent.mkdir(parents=True, exist_ok=True); PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')

def add(item):
    rows=list_draft(); rows.append(item); save(rows); return rows

def clear():
    save([])
