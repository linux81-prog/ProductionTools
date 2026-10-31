"""Measure extraction accuracy against answer keys (fictional test data only)."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from .extract import load_pages
from .models import REVIEW_THRESHOLD
from .parse import parse_receipt

FIELDS = ("vendor", "date", "subtotal", "tax", "total", "payment")


def _norm(field: str, v) -> str | None:
    if v is None:
        return None
    if field in ("subtotal", "tax", "total"):
        return str(Decimal(str(v)).quantize(Decimal("0.01")))
    if field == "vendor":
        return re.sub(r"[^a-z0-9]", "", str(v).lower())
    return str(v).strip().lower()


def evaluate(receipts_dir: Path, keys_path: Path) -> dict:
    keys = json.loads(Path(keys_path).read_text())
    rows, per_field = [], {f: {"correct": 0, "wrong": 0, "missing": 0, "wrong_but_flagged": 0} for f in FIELDS}
    for name, key in keys.items():
        pages = load_pages(Path(receipts_dir) / name)
        fields = parse_receipt(pages)
        row = {"file": name, "condition": key.get("condition", ""), "fields": {}}
        for f in FIELDS:
            got = fields[f].value if f in fields else None
            ok = _norm(f, got) == _norm(f, key[f])
            flagged = fields[f].needs_review if f in fields else True
            status = "correct" if ok else ("missing" if got is None else "wrong")
            per_field[f][status] += 1
            if status == "wrong" and flagged:
                per_field[f]["wrong_but_flagged"] += 1
            row["fields"][f] = {"expected": key[f], "got": None if got is None else str(got), "status": status,
                                "confidence": fields[f].confidence if f in fields else 0.0, "flagged_for_review": flagged}
        rows.append(row)
    n = len(keys)
    total_checks = n * len(FIELDS)
    correct = sum(v["correct"] for v in per_field.values())
    wrong = sum(v["wrong"] for v in per_field.values())
    silent = sum(v["wrong"] - v["wrong_but_flagged"] for v in per_field.values())
    return {"receipts": n, "field_checks": total_checks, "correct": correct,
            "accuracy": round(correct / total_checks, 4) if total_checks else 0.0,
            "wrong": wrong, "missing": sum(v["missing"] for v in per_field.values()),
            "wrong_and_NOT_flagged": silent, "review_threshold": REVIEW_THRESHOLD,
            "per_field": per_field, "rows": rows}
