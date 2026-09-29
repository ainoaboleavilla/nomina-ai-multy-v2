from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
import uuid

BASE_DIR = Path(__file__).resolve().parent.parent.parent
AUDIT_DIR = BASE_DIR / "data" / "audit"
AUDIT_FILE = AUDIT_DIR / "reviews.jsonl"

def new_review_id() -> str:
    return uuid.uuid4().hex[:12]

def record_review(*, review_id: str, version: int, action: str, reviewer: str,
                  comments: str, input_file: str, generated_files: dict, summary: dict) -> dict:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    event = {
        "review_id": review_id,
        "version": int(version),
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "action": action.upper(),
        "reviewer": reviewer.strip(),
        "comments": comments.strip(),
        "input_file": input_file,
        "generated_files": generated_files,
        "summary": summary,
    }
    with AUDIT_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event

def read_reviews(limit: int = 50) -> list[dict]:
    if not AUDIT_FILE.exists():
        return []
    rows = []
    with AUDIT_FILE.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except (json.JSONDecodeError, TypeError):
                continue
    return list(reversed(rows[-limit:]))
