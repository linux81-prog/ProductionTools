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
from .parse import resolve_total

MONEY_FIELDS = {"subtotal", "tax", "total", "other_charges", "printed_total", "tip", "final_total"}
TIP_INPUTS = {"printed_total", "tip", "final_total"}


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
        corrected = set((d.get("corrections") or {}))
        if corrected & TIP_INPUTS and "total" not in corrected:
            old_total = r.total
            r.fields["total"] = resolve_total(r.fields)
            if r.fields["total"].value != old_total:
                audit.record("total_recalculated", actor="system", receipt=r.source_name, old=str(old_total),
                             new=str(r.fields["total"].value), reason="tip / final total corrected by reviewer")
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
        for key in ("paid_by", "tip_paid_by"):
            if key in d:
                val = d[key]
                if val not in ("petty_cash_float", "crew_personal", "company_card"):
                    raise ValueError(f"{r.source_name}: {key} must be petty_cash_float, crew_personal or company_card")
                setattr(r, key, val)
                audit.record(f"{key}_set", actor=reviewer, receipt=r.source_name, value=val)
        for key in ("personal_card_approved", "tip_eligible_confirmed", "reimbursed_from_float", "acknowledge_exclusion"):
            if key in d:
                attr = "exclusion_acknowledged" if key == "acknowledge_exclusion" else key
                setattr(r, attr, bool(d[key]))
                audit.record(f"{key}_set", actor=reviewer, receipt=r.source_name, value=bool(d[key]))
        for key in ("authorization", "tip_documentation"):
            if d.get(key):
                setattr(r, key, str(d[key]))
                audit.record(f"{key}_set", actor=reviewer, receipt=r.source_name, value=str(d[key]))
        if "tip_method" in d:
            r.fields["tip_method"] = FieldValue("tip_method", d["tip_method"], 1.0, source="reviewer", verified=True)
            audit.record("tip_method_set", actor=reviewer, receipt=r.source_name, value=d["tip_method"])
        if d.get("confirm"):
            for f in r.fields.values():
                if f.value is not None:
                    f.verified = True
            if r.fields.get("total") and r.fields["total"].tip_status == "proposed":
                audit.record("proposed_total_confirmed", actor=reviewer, receipt=r.source_name,
                             value=str(r.total), note="final total was blank on the receipt; reviewer accepted printed total + tip")
            r.verified_by = reviewer
            audit.record("receipt_verified", actor=reviewer, receipt=r.source_name,
                         note=d.get("note", "all extracted fields checked against the receipt image"))
