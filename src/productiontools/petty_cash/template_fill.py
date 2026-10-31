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
        "receipts_total": total, "receipt_count": len(receipts),
    }
    values: dict[str, object] = {cell: header_src[field] for field, cell in profile.header.items()}
    for i, r in enumerate(receipts):
        row = profile.first_row + i
        line_src = {"number": r.number, "date": r.date, "vendor": r.vendor, "description": r.description,
                    "account_code": r.account_code, "amount": r.total,
                    "payment": r.val("payment"), "tax": r.val("tax")}
        for field, col in profile.columns.items():
            values[f"{col}{row}"] = line_src[field]
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
