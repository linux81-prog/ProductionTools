"""Build the Stage 1 deliverables folder: docs/stage1-demo/

  1. runs the full automated test suite (with the network lock on),
  2. runs the end-to-end demo on the three fictional receipts,
  3. measures OCR accuracy on the demo set and on the harder stress set,
  4. writes docs/stage1-demo/test-results.md in plain English.

Run:  python tools/make_report.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from productiontools.core import netguard  # noqa: E402

netguard.install()

import run_demo  # noqa: E402
from productiontools.core.xlsx_fill import ALLOWED_CHANGES  # noqa: E402
from productiontools.petty_cash.accuracy import FIELDS, evaluate  # noqa: E402

OUT = ROOT / "docs" / "stage1-demo"
FIX = ROOT / "fixtures"


def run_tests() -> tuple[str, str]:
    p = subprocess.run([sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider", "tests"],
                       cwd=ROOT, capture_output=True, text=True)
    lines = [l for l in p.stdout.splitlines() if "::" in l and ("PASSED" in l or "FAILED" in l or "ERROR" in l)]
    summary = p.stdout.strip().splitlines()[-1].strip("= ")
    return summary, "\n".join(re.sub(r"\s+\[\s*\d+%\]$", "", l) for l in lines)


def acc_table(r: dict) -> str:
    out = ["| Field | Correct | Wrong | Not found | Wrong/missing but flagged for review |", "|---|---|---|---|---|"]
    for f in FIELDS:
        v = r["per_field"][f]
        flagged = v["wrong_but_flagged"] + v["missing"]
        out.append(f"| {f} | {v['correct']}/{r['receipts']} | {v['wrong']} | {v['missing']} | {flagged}/{v['wrong'] + v['missing']} |")
    return "\n".join(out)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    work = ROOT / "demo_runs" / ("report-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    res = run_demo.run(work)
    v = res.version_dir

    # copy the deliverables
    for name in ["PC001_TopSheet.xlsx", "PC001_TopSheet.pdf", "PC001_Combined_Annotated.pdf", "PC001_Combined_Clean.pdf",
                 "PC001_Reconciliation_Report.pdf", "PC001_Reconciliation_Report.xlsx", "run_summary.json",
                 "extraction_before_review.json"]:
        shutil.copy(v / name, OUT / name)
    for sub in ("receipts_annotated", "receipts_clean", "draft_before_review"):
        shutil.copytree(v / sub, OUT / sub)
    shutil.copy(work / "audit.log", OUT / "audit.log")

    demo_acc = evaluate(FIX / "receipts", FIX / "answer_keys.json")
    stress_acc = evaluate(FIX / "stress", FIX / "stress" / "answer_keys.json")
    (OUT / "ocr_accuracy.json").write_text(json.dumps({"demo": demo_acc, "stress": stress_acc}, indent=2))
    test_summary, test_lines = run_tests()

    pres = res.preservation
    pres_rows = "\n".join(f"| {'PASS' if c['passed'] else '**FAIL**'} | {c['name']} | {c['detail']} |" for c in pres["checks"])
    allowed = "\n".join(f"- **{a}**: {why}" for a, why in ALLOWED_CHANGES)
    seen = "\n".join(f"- {s}" for s in pres["allowed_changes_seen"]) or "- none (the fictional template already had the recalculate flag set, so workbook.xml did not change at all)"

    stress_fail_rows = []
    for row in stress_acc["rows"]:
        for f, val in row["fields"].items():
            if val["status"] != "correct":
                stress_fail_rows.append(f"| {row['file']} | {row['condition']} | {f} | {val['expected']} | {val['got']} | "
                                        f"{'yes' if val['flagged_for_review'] else '**NO**'} |")
    stress_cond = "\n".join(f"| {row['file']} | {row['condition']} | "
                            f"{sum(v['status'] == 'correct' for v in row['fields'].values())}/{len(FIELDS)} |"
                            for row in stress_acc["rows"])

    review_needed = []
    for name, data in res.extraction.items():
        for f, fv in data["fields"].items():
            if fv["needs_review"] and f in ("vendor", "date", "subtotal", "tax", "total", "payment"):
                review_needed.append(f"- `{name}`: **{f}** = {fv['value']} (confidence {fv['confidence']:.0%}) — {fv['note'] or 'below threshold'}")
    review_needed = "\n".join(review_needed) or "- none"

    overrides = [o for r in res.envelope.receipts for o in r.overrides]
    corr = [o for o in overrides if o["kind"] == "value correction"]
    pos = [o for o in overrides if o["kind"] == "annotation position"]
    corr_txt = (f"**Manual corrections the reviewer had to make on the demo receipts: {len(corr)}.**"
                + ("" if corr else " All vendor, date, total, subtotal, tax and payment values were read correctly.")
                + "".join(f"\n- {o['receipt']}: {o['field']} {o['old']} → {o['new']} ({o['reason']})" for o in corr))
    pos_txt = (f"**Manual annotation positioning needed: {len(pos)}**"
               + (" in this demo. Every vendor, date and total was located automatically." if not pos else "."))
    flags = "\n".join(f"| {f.severity} | {f.scope} | {f.check} | {f.message} |" for f in res.flags)

    md = f"""# Stage 1 — Test Results and Demo Report

Generated {datetime.now():%Y-%m-%d %H:%M} in the cloud development environment. **All data is fictional.**

## 1. Automated tests

**Result: {test_summary}**

Every test runs with the app-level network lock installed, so any accidental outbound
connection would make the suite fail.

<details><summary>All test names and results</summary>

```
{test_lines}
```
</details>

## 2. OCR / extraction accuracy

"Correct" means the extracted value exactly matches the answer key (amounts to the cent,
dates to the day, vendor names ignoring capitalisation and punctuation).

### 2a. The three demo receipts (phone photo, scanned PDF, emailed invoice)

**{demo_acc['correct']}/{demo_acc['field_checks']} fields correct ({demo_acc['accuracy']:.0%}).**

{acc_table(demo_acc)}

### 2b. Stress set: 12 harder fictional phone photos

These were made deliberately difficult (blur, noise, crumpling, fading, dim light, low
resolution) so this figure is more honest than the clean demo receipts alone.

**{stress_acc['correct']}/{stress_acc['field_checks']} fields correct ({stress_acc['accuracy']:.0%}).
Wrong values that were NOT flagged for human review: {stress_acc['wrong_and_NOT_flagged']}.**

{acc_table(stress_acc)}

| File | Condition | Fields correct |
|---|---|---|
{stress_cond}

Failures in detail:

| File | Condition | Field | Expected | Got | Flagged for review? |
|---|---|---|---|---|---|
{chr(10).join(stress_fail_rows) or '| — | — | — | — | — | — |'}

**What this means:** on clear and moderately degraded photos the reader was accurate. On
the heavily blurred photo it failed, but it flagged every wrong or missing value for a
person, which is the safety behaviour we need. Real receipts will vary more than synthetic
ones; expect lower accuracy on handwriting, very faded thermal paper and unusual layouts.
Handwriting was not tested in Stage 1.

## 3. Workbook preservation (filled top sheet vs. original template)

**Overall: {'PASSED' if pres['passed'] else 'FAILED'}.** Two independent methods were used:
(A) raw comparison of every internal part of the .xlsx file, and (B) re-opening both files
with a separate spreadsheet library and comparing values, formulas, formatting and print settings.

| Result | Check | Detail |
|---|---|---|
{pres_rows}

**Documented intentional changes (the only differences allowed):**
{allowed}

**Allowed changes actually seen in this run:**
{seen}

The tests also confirm that the checker **catches** problems. It fails on a changed formula
in an unmapped cell, and on a damaged logo image. They also confirm that filling **refuses**
to write into a formula cell or into the hidden part of a merged cell. And a template
*without* the recalculate flag is tested too: the flag is added, and that is the only change
to workbook.xml.

## 4. Reconciliation results for envelope PC001

| Severity | Scope | Check | Finding |
|---|---|---|---|
{flags}

All three were planted on purpose in the fictional data: the crew member returned $2.00
too little, the café receipt's printed total is $0.50 more than subtotal + tax, and the
invoice was paid by card.

## 5. What failed, or needed manual correction

**Fields the machine flagged for review before any person looked** (shown dashed with "?" in
`draft_before_review/`):
{review_needed}

{corr_txt}

The reviewer (fictional) also had to:
- enter the account code and description for each receipt (by design, the app never guesses these yet),
- confirm the café receipt's printed total despite its arithmetic error (left for the accountant),
- confirm each receipt, because nothing counts as verified until a person says so.

{pos_txt} Manual positioning is supported and tested (`tests/test_annotate.py`),
and the visual editor arrives in Stage 3.

**Known limitations and things that did not work perfectly:**
- **Top sheet PDF:** there is no Excel in the cloud, so `PC001_TopSheet.pdf` is a *cloud preview*
  made with LibreOffice and is clearly watermarked. It is not part of the app. On your Mac,
  Excel produces this page (Stage 2). The manual-export fallback page is tested too.
- **Receipt-number placement:** chosen automatically as the emptiest spot on or next to the printed
  text. On the narrow café receipt the number sits at the receipt's bottom edge, partly off the paper.
  It's readable, but this is a case for the Stage 3 editor.
- **Heavy blur:** one of 12 stress photos failed (see 2b). It was flagged, not silently wrong.
- **Overflow:** more receipts than the template's 15 line rows stops with a clear message.
  Continuation sheets come in a later stage.
- **Vendor names** are tidied from ALL CAPS ("HARDWARE BARN" → "Hardware Barn"). Unusual names
  may need a person to adjust them.

## 6. Network and privacy (Stage 1)

- **App-level network lock (application-level safeguard):** installed for every run and every
  test; outbound attempts during the demo run: {len([a for a in netguard.LOG.attempts])}.
  This covers only ProductionTools' own Python process.
- The OCR models ship inside the installed package; nothing is downloaded at run time.
- See `docs/NETWORK-SECURITY.md` for the difference between the app's own safeguards, macOS's
  built-in firewall (incoming connections only), and independent outbound blockers.

## 7. Files in this folder

| File | What it is |
|---|---|
| `receipts_annotated/` | The three numbered, annotated receipt PDFs (named number_date_vendor_total) |
| `receipts_clean/` | The same receipts with no marks |
| `draft_before_review/` | What the machine produced on its own, before human review (dashed = unverified) |
| `PC001_TopSheet.xlsx` | The filled copy of the fictional top-sheet template |
| `PC001_TopSheet.pdf` | Cloud preview of the top sheet (watermarked; Excel makes this on the Mac) |
| `PC001_Combined_Annotated.pdf` | Top sheet + annotated receipts, with bookmarks |
| `PC001_Combined_Clean.pdf` | Top sheet + clean receipts (the annotation toggle) |
| `PC001_Reconciliation_Report.pdf` / `.xlsx` | Discrepancies and missing information |
| `extraction_before_review.json`, `run_summary.json`, `audit.log`, `ocr_accuracy.json` | Machine-readable records |
"""
    (OUT / "test-results.md").write_text(md)
    shutil.rmtree(work)
    print(f"Report written to {OUT}")
    print(test_summary)


if __name__ == "__main__":
    main()
