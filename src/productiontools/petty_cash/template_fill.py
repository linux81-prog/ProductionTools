"""Fill a copy of a company's top-sheet template from an envelope."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from ..core import xlsx_integrity
from ..core.xlsx_fill import TemplateMappingError, fill_template_copy
from .mapping import TemplateProfile
from .models import Envelope


class TemplateOverflowError(TemplateMappingError):
    pass


def receipt_number_value(r, profile: TemplateProfile):
    return r.seq if profile.receipt_number_style == "index" else r.number


def receipt_label(r, profile: TemplateProfile) -> str:
    """Text written on the receipt; matches what the top sheet's number column shows."""
    v = receipt_number_value(r, profile)
    return f"#{v}" if isinstance(v, int) else str(v)


def _typed(value, typ: str):
    """Convert a value to the type the template expects (e.g. numeric line numbers for formulas)."""
    if value is None or typ in ("auto", "date"):
        return value
    if typ == "text":
        return str(value)
    if typ == "digits":  # e.g. phone numbers stored as a number so the template's own format applies
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        return int(digits) if digits else None
    if typ in ("number", "money"):
        s = str(value).replace(",", "").replace("$", "").strip()
        try:
            d = Decimal(s)
        except Exception:
            raise TemplateMappingError(f"Value {value!r} must be a number for this template cell")
        return int(d) if typ == "number" and d == d.to_integral_value() else d
    return value


def topsheet_values(env: Envelope, profile: TemplateProfile) -> dict[str, object]:
    receipts = env.receipts
    if len(receipts) > profile.max_rows:
        raise TemplateOverflowError(
            f"{len(receipts)} receipts but the template has {profile.max_rows} line rows. "
            "Continuation sheets arrive in a later stage; split the envelope for now.")
    total = sum((r.total or Decimal("0") for r in receipts), Decimal("0"))
    header_src = {
        "production": env.production, "production_number": env.production_number, "company": env.company,
        "crew_member": env.crew_member, "department": env.department, "position": env.position,
        "envelope_number": env.envelope_number, "period_start": env.period_start, "period_end": env.period_end,
        "float_amount": env.float_amount, "cash_returned": env.cash_returned, "reported_total": env.reported_total,
        "receipts_total": total, "receipt_count": len(receipts), "crew_phone": env.crew_phone,
    }
    values: dict[str, object] = {cell: _typed(header_src[field], profile.types.get(cell, "auto"))
                                 for field, cell in profile.header.items()}
    for i, r in enumerate(receipts):
        row = profile.first_row + i
        line_src = {"number": receipt_number_value(r, profile), "date": r.date, "vendor": r.vendor, "description": r.description,
                    "account_code": r.account_code, "amount": r.total,
                    "payment": r.val("payment"), "tax": r.val("tax")}
        for field, col in profile.columns.items():
            values[f"{col}{row}"] = _typed(line_src[field], profile.types.get(col, "auto"))
    return values


def fill_topsheet(env: Envelope, profile: TemplateProfile, dest: Path) -> dict:
    """Write the filled copy, then verify preservation. Raises if verification fails."""
    values = topsheet_values(env, profile)
    info = fill_template_copy(profile.template_file, dest, profile.sheet, values)
    report = xlsx_integrity.compare(profile.template_file, dest, profile.sheet, info["sheet_part"], values.keys())
    info["preservation"] = report.as_dict()
    if not report.passed:
        failed = [c.name for c in report.checks if not c.passed]
        dest.rename(dest.with_name(dest.stem + ".REJECTED-do-not-use.xlsx"))  # never leave a bad copy looking valid
        raise TemplateMappingError(f"Preservation check failed for {dest.name}: {failed}")
    return info
