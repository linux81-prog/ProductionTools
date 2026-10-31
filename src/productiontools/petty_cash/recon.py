"""Reconciliation checks for a petty cash envelope.

The app RAISES issues for a person to resolve; it never silently fixes them.
Severity:
  ERROR    - must be resolved before the envelope can be finalized
  WARNING  - needs a person's sign-off
  INFO     - for awareness
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .models import REVIEW_THRESHOLD, Envelope

ZERO = Decimal("0.00")


@dataclass
class Flag:
    severity: str
    scope: str      # receipt number or "Envelope"
    check: str
    message: str
    action: str


def reconcile(env: Envelope, chart: dict[str, str]) -> list[Flag]:
    flags: list[Flag] = []
    add = lambda *a: flags.append(Flag(*a))

    seen_hash: dict[str, str] = {}
    seen_key: dict[tuple, str] = {}
    for r in env.receipts:
        n = r.number or r.source_name
        for key, label in (("vendor", "Vendor"), ("date", "Date"), ("total", "Total")):
            f = r.fields.get(key)
            if not f or f.value is None:
                add("ERROR", n, "Missing information", f"{label} could not be read.", f"Enter the {label.lower()} from the receipt.")
            elif not f.verified and f.confidence < REVIEW_THRESHOLD:
                add("WARNING", n, "Uncertain reading", f"{label} '{f.value}' has low confidence ({f.confidence:.0%}).",
                    "Check against the receipt image and confirm.")
            if f and f.value is not None and f.box is None:
                add("WARNING", n, "Annotation placement", f"{label} location not found on the receipt.",
                    "Position the circle manually in the annotation editor.")
        if not r.verified_by:
            add("ERROR", n, "Not verified", "No person has verified this receipt.", "Review and confirm the receipt.")

        tot = r.total
        sub, tax, oth = r.val("subtotal"), r.val("tax"), r.val("other_charges") or ZERO
        printed = r.val("printed_total") if r.val("printed_total") is not None else tot
        _tip_flags(r, n, add)
        if sub is not None and tax is not None and printed is not None and sub + tax + oth != printed:
            extra = f" + other charges ${oth}" if oth else ""
            add("WARNING", n, "Receipt arithmetic", f"Subtotal ${sub} + tax ${tax}{extra} = ${sub + tax + oth}, "
                f"but the receipt's printed total is ${printed} (difference ${printed - (sub + tax + oth)}).",
                "Confirm the amount actually paid; the vendor may have mis-totalled. Attach a note if reimbursing the printed total.")
        if r.date and not (env.period_start <= r.date <= env.period_end):
            add("WARNING", n, "Date outside period", f"Receipt date {r.date:%m/%d/%Y} is outside "
                f"{env.period_start:%m/%d/%Y}–{env.period_end:%m/%d/%Y}.", "Confirm the date or move it to the right envelope.")
        if tot is not None and tot > env.per_receipt_limit:
            add("WARNING", n, "Over limit", f"${tot} exceeds the per-receipt limit of ${env.per_receipt_limit}.",
                "Get approval from the production accountant.")
        if not r.account_code:
            add("ERROR", n, "Account code", "No account code assigned.", "Choose an account code.")
        elif chart and r.account_code not in chart:
            add("ERROR", n, "Account code", f"Code {r.account_code} is not in the chart of accounts.", "Correct the code.")
        if r.description and r.description_source == "job line list":
            add("INFO", n, "Description", f"Filled from the job's line list for line {r.account_code}: \"{r.description}\".",
                "Edit on the review screen if a more specific description is wanted.")
        if not r.description:
            add("WARNING", n, "Description", "No description entered.", "Describe what was purchased and why.")
        pay = r.val("payment")
        if pay and pay != "Cash":
            add("INFO", n, "Payment method", f"Receipt shows payment by {pay}, not cash.",
                "Confirm this was paid personally (reimbursable) and not on a company card, to avoid double payment.")
        if r.sha256 in seen_hash:
            add("ERROR", n, "Duplicate file", f"Same file as {seen_hash[r.sha256]}.", "Remove the duplicate.")
        seen_hash.setdefault(r.sha256, n)
        key = (str(r.vendor).lower(), r.date, tot)
        if None not in key[1:] and key in seen_key:
            add("WARNING", n, "Possible duplicate", f"Same vendor, date and total as {seen_key[key]}.", "Confirm these are separate purchases.")
        seen_key.setdefault(key, n)
        for field_name, why in r.annotation_notes.items():
            if "already" in why:
                add("INFO", n, "Existing marking", f"{field_name}: {why}.", "No action needed; check the original marking is correct.")
        for o in r.overrides:
            add("INFO", n, "Manual override", f"{o['kind']}: {o['field']} {o['old']} → {o['new']}"
                + (f" ({o['reason']})" if o.get("reason") else ""), "Recorded in the audit log.")

    total = sum((r.total or ZERO for r in env.receipts), ZERO)
    if total != env.reported_total:
        add("WARNING", "Envelope", "Reported total", f"Receipts add up to ${total}, but the envelope reports ${env.reported_total} "
            f"(difference ${total - env.reported_total}).", "Confirm with the crew member.")
    expected = env.float_amount - total
    diff = env.cash_returned - expected
    if diff != 0:
        kind = "SHORT" if diff < 0 else "OVER"
        add("ERROR", "Envelope", "Cash reconciliation",
            f"Float ${env.float_amount} − receipts ${total} = ${expected} expected back; ${env.cash_returned} returned. "
            f"{kind} by ${abs(diff)}.", "Resolve with the crew member (missing receipt, lost-receipt affidavit, or cash correction).")
    if not env.receipts:
        add("ERROR", "Envelope", "No receipts", "Envelope has no receipts.", "Add receipts.")
    order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    flags.sort(key=lambda f: (order[f.severity], f.scope != "Envelope", f.scope))
    return flags


def _tip_flags(r, n, add) -> None:
    t = r.fields.get("total")
    status = getattr(t, "tip_status", "") if t else ""
    tip, fin, printed = r.val("tip"), r.val("final_total"), r.val("printed_total")
    for key, label in (("tip", "Tip"), ("final_total", "Final total")):
        f = r.fields.get(key)
        if f and f.value is not None and not f.verified:
            add("WARNING", n, "Handwritten amount", f"{label} ${f.value} is in the handwritten area (confidence {f.confidence:.0%}).",
                "Check against the receipt image and confirm or correct it.")
    if status == "mismatch":
        add("WARNING", n, "Tip arithmetic", f"Printed total ${printed} + tip ${tip} = ${printed + tip}, but the written final total "
            f"is ${fin} (difference ${fin - (printed + tip)}).", "Decide which amount was actually paid and correct the receipt entry.")
    elif status == "proposed":
        if t.verified:
            add("INFO", n, "Proposed final amount", f"Final total was blank; printed ${printed} + tip ${tip} = ${t.value} was confirmed on review.",
                "Recorded in the audit log.")
        else:
            add("WARNING", n, "Proposed final amount", f"Final total is blank. Proposed: printed ${printed} + tip ${tip} = ${t.value}.",
                "Confirm the proposed amount before it is used.")
    elif status == "implied":
        add("WARNING", n, "Implied tip", f"Final total ${fin} is written but no tip amount could be read (implied tip ${fin - printed}).",
            "Confirm the tip and final amount.")
    if tip is not None or status in ("proposed", "implied", "mismatch", "verified"):
        method = r.val("tip_method")
        if method == "card":
            add("INFO", n, "Tip paid by card", f"Tip ${tip if tip is not None else (fin - printed)} is included in the card charge of ${r.total}.",
                "Reimburse the card charge once; do not add the tip again.")
        elif method == "cash":
            add("INFO", n, "Tip paid in cash", f"Tip paid in cash; expense amount ${r.total} includes it.",
                "Confirm the cash tip was paid from petty cash / personally.")
        else:
            add("WARNING", n, "Tip payment method", "Could not tell whether the tip was paid by card or in cash.",
                "Ask the crew member so the reimbursement is correct.")
    if r.val("suggested_tip"):
        add("INFO", n, "Suggested gratuity", "Receipt shows suggested tip amounts; these were NOT counted.", "No action needed.")


def summary_numbers(env: Envelope) -> dict:
    total = sum((r.total or ZERO for r in env.receipts), ZERO)
    expected = env.float_amount - total
    return {"float": env.float_amount, "receipts_total": total, "expected_return": expected,
            "cash_returned": env.cash_returned, "over_short": env.cash_returned - expected,
            "reported_total": env.reported_total, "receipt_count": len(env.receipts)}


# ------------------------------------------------------------------ outputs --
def report_pdf(env: Envelope, flags: list[Flag], extra_sections: list[tuple[str, list[str]]] | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            title=f"Reconciliation report {env.envelope_number}", author="ProductionTools")
    ss = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=ss["BodyText"], fontSize=8.5, leading=10.5)
    story = [Paragraph(f"Petty Cash Reconciliation Report — {env.envelope_number}", ss["Title"]),
             Paragraph(f"{env.production} ({env.production_number}) · {env.company} · {env.crew_member}, {env.department} · "
                       f"Period {env.period_start:%m/%d/%Y}–{env.period_end:%m/%d/%Y}", small), Spacer(1, 10)]
    n = summary_numbers(env)
    money = lambda v: f"${v:,.2f}" if v >= 0 else f"(${-v:,.2f})"
    summ = [["Float issued", money(n["float"])], ["Receipts total", money(n["receipts_total"])],
            ["Expected cash return", money(n["expected_return"])], ["Cash returned", money(n["cash_returned"])],
            ["Over / (Short)", money(n["over_short"])], ["Crew-reported total", money(n["reported_total"])],
            ["Receipts", str(n["receipt_count"])]]
    t = Table(summ, colWidths=[2.2 * inch, 1.4 * inch])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9.5), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                           ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#F8D7DA") if n["over_short"] else colors.white)]))
    story += [t, Spacer(1, 12)]

    counts = {s: sum(f.severity == s for f in flags) for s in ("ERROR", "WARNING", "INFO")}
    pl = lambda n, word: f"{n} {word}{'' if n == 1 else 's'}"
    story.append(Paragraph(f"<b>{pl(counts['ERROR'], 'error')}</b> (must be resolved before finalizing) · "
                           f"<b>{pl(counts['WARNING'], 'warning')}</b> (need sign-off) · {pl(counts['INFO'], 'note')}", ss["BodyText"]))
    story.append(Spacer(1, 6))
    rows = [["", "Scope", "Check", "Finding", "Action"]]
    for f in flags:
        rows.append([f.severity, f.scope, Paragraph(f.check, small), Paragraph(f.message, small), Paragraph(f.action, small)])
    ft = Table(rows, colWidths=[0.75 * inch, 0.85 * inch, 1.1 * inch, 2.75 * inch, 1.85 * inch], repeatRows=1)
    style = [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9), ("FONT", (0, 1), (1, -1), "Helvetica", 8),
             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
             ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey)]
    colours = {"ERROR": "#F8D7DA", "WARNING": "#FFF3CD", "INFO": "#E8F0FE"}
    for i, f in enumerate(flags, start=1):
        style.append(("BACKGROUND", (0, i), (0, i), colors.HexColor(colours[f.severity])))
    ft.setStyle(TableStyle(style))
    story.append(ft)
    for title, lines in extra_sections or []:
        story += [Spacer(1, 12), Paragraph(title, ss["Heading3"])]
        story += [Paragraph(line, small) for line in lines]
    story += [Spacer(1, 14), Paragraph("Generated offline by ProductionTools. This report flags issues for a person to resolve; "
                                       "nothing has been changed automatically.", small)]
    doc.build(story)
    return buf.getvalue()


def report_xlsx(env: Envelope, flags: list[Flag], dest: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Flags"
    ws.append(["Severity", "Scope", "Check", "Finding", "Action"])
    for c in ws[1]:
        c.font = Font(bold=True)
    fills = {"ERROR": "F8D7DA", "WARNING": "FFF3CD", "INFO": "E8F0FE"}
    for f in flags:
        ws.append([f.severity, f.scope, f.check, f.message, f.action])
        ws.cell(ws.max_row, 1).fill = PatternFill("solid", fgColor=fills[f.severity])
    for col, w in zip("ABCDE", [10, 12, 22, 80, 60]):
        ws.column_dimensions[col].width = w
    s = wb.create_sheet("Summary")
    for k, v in summary_numbers(env).items():
        s.append([k.replace("_", " ").title(), float(v) if isinstance(v, Decimal) else v])
    s.column_dimensions["A"].width = 24
    li = wb.create_sheet("Line Items")
    li.append(["Number", "Date", "Vendor", "Description", "Account", "Subtotal", "Tax", "Total", "Payment", "Verified by", "Source file"])
    for r in env.receipts:
        li.append([r.number, r.date, r.vendor, r.description, r.account_code,
                   *(float(r.val(k)) if r.val(k) is not None else None for k in ("subtotal", "tax", "total")),
                   r.val("payment"), r.verified_by, r.source_name])
    with open(dest, "xb") as fh:
        wb.save(fh)
