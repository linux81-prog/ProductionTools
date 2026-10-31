"""Apply a person's review decisions to extracted receipts.

In the finished app these decisions come from the review screen and the
annotation editor (Stage 3). In Stage 1 they are read from a small YAML
file so the whole workflow can be demonstrated end to end. Every change is
recorded with the old value, new value, reviewer and reason.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

from ..core.audit import AuditLog
from .models import Box, FieldValue, Receipt

MONEY_FIELDS = {"subtotal", "tax", "total", "other_charges"}


def _coerce(field: str, value):
    if value is None:
        return None
    if field == "date":
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    if field in MONEY_FIELDS:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    return str(value)


def load_review(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def apply_review(receipts: list[Receipt], review: dict, audit: AuditLog) -> None:
    reviewer = review.get("reviewer", "unknown reviewer")
    decisions = review.get("receipts", {})
    for r in receipts:
        d = decisions.get(r.source_name)
        if not d:
            continue
        for field, change in (d.get("corrections") or {}).items():
            new = _coerce(field, change["value"])
            old_f = r.fields.get(field)
            old = old_f.value if old_f else None
            f = old_f or FieldValue(field, None, 0.0)
            f.value, f.confidence, f.source, f.verified = new, 1.0, "reviewer", True
            f.note = f"corrected by reviewer: {change.get('reason', '')}".strip()
            r.fields[field] = f
            entry = {"receipt": r.source_name, "field": field, "old": str(old), "new": str(new),
                     "reason": change.get("reason", "")}
            r.overrides.append({**entry, "kind": "value correction"})
            audit.record("field_corrected", actor=reviewer, **entry)
        for field, pos in (d.get("positions") or {}).items():
            page = int(pos.get("page", 0))
            img = r.pages[page].image
            f = r.fields.setdefault(field, FieldValue(field, None, 0.0))
            old_box = f.box
            f.box, f.page = Box.from_norm(pos["box"], img.width, img.height), page
            entry = {"receipt": r.source_name, "field": field, "old": "none" if old_box is None else "auto-placed",
                     "new": f"manually positioned on page {page + 1}", "reason": pos.get("reason", "")}
            r.overrides.append({**entry, "kind": "annotation position"})
            audit.record("annotation_positioned", actor=reviewer, **entry)
        if d.get("number_position"):
            r.number_position = d["number_position"]
            audit.record("number_positioned", actor=reviewer, receipt=r.source_name)
        if "account_code" in d:
            r.account_code = str(d["account_code"])
            audit.record("account_code_set", actor=reviewer, receipt=r.source_name, value=r.account_code)
        if "description" in d:
            r.description = str(d["description"])
            audit.record("description_set", actor=reviewer, receipt=r.source_name, value=r.description)
        if d.get("confirm"):
            for f in r.fields.values():
                if f.value is not None:
                    f.verified = True
            r.verified_by = reviewer
            audit.record("receipt_verified", actor=reviewer, receipt=r.source_name,
                         note=d.get("note", "all extracted fields checked against the receipt image"))
