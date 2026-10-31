"""Full pipeline on the three fictional receipts (no Excel in the cloud: top sheet PDF uses the manual-fallback placeholder)."""

import io
import json

import pytest
from pypdf import PdfReader

from conftest import FIX, PROFILE
from productiontools.core import netguard
from productiontools.core.filestore import sha256_file
from productiontools.petty_cash.pipeline import run_envelope

EXPECTED = ["PC001-001_2026-10-14_Hardware-Barn_81.30.pdf",
            "PC001-002_2026-10-15_Copper-Kettle-Cafe_94.94.pdf",
            "PC001-003_2026-10-16_Prop-Depot-Supply-Co_100.29.pdf",
            "PC001-004_2026-10-17_Harbor-Light-Diner_54.99.pdf"]


@pytest.fixture(scope="module")
def run(tmp_path_factory, chart_module):
    project = tmp_path_factory.mktemp("project")
    before = {p.name: sha256_file(p) for p in (FIX / "receipts").iterdir()}
    res = run_envelope(FIX / "envelope.yaml", FIX / "receipts", PROFILE, chart_module, project, FIX / "review.yaml")
    return res, project, before


@pytest.fixture(scope="module")
def chart_module():
    import yaml
    return {str(k): v for k, v in yaml.safe_load((FIX / "account_codes.yaml").read_text()).items()}


def test_all_outputs_exist_with_consistent_names(run):
    res, _, _ = run
    v = res.version_dir
    assert sorted(p.name for p in (v / "receipts_annotated").iterdir()) == EXPECTED
    assert sorted(p.name for p in (v / "receipts_clean").iterdir()) == EXPECTED
    for name in ["PC001_TopSheet.xlsx", "PC001_TopSheet.pdf", "PC001_Combined_Annotated.pdf", "PC001_Combined_Clean.pdf",
                 "PC001_Reconciliation_Report.pdf", "PC001_Reconciliation_Report.xlsx", "run_summary.json"]:
        assert (v / name).exists(), name
    assert len(list((v / "review_previews").iterdir())) == 4


def test_combined_pdf_order_and_bookmarks(run):
    res, _, _ = run
    r = PdfReader(str(res.version_dir / "PC001_Combined_Annotated.pdf"))
    assert len(r.pages) == 5  # top sheet + 4 receipts
    titles = [o.title for o in r.outline]
    assert titles[0] == "PC001 Top Sheet"
    assert [t.split()[0] for t in titles[1:]] == ["PC001-001", "PC001-002", "PC001-003", "PC001-004"]
    assert "TOP SHEET PDF PENDING" in r.pages[0].extract_text()  # manual fallback when Excel is unavailable


def test_reconciliation_flags_the_planted_problems(run):
    res, _, _ = run
    checks = {(f.severity, f.scope, f.check) for f in res.flags}
    assert ("ERROR", "Envelope", "Cash reconciliation") in checks           # $2.00 short
    assert ("WARNING", "PC001-002", "Receipt arithmetic") in checks         # printed total $0.50 off
    assert ("INFO", "PC001-003", "Paid personally") in checks               # crew member's own Visa
    assert ("INFO", "PC001-004", "Tip paid by card") in checks             # handwritten tip, charged to the card
    assert ("INFO", "PC001-004", "Suggested gratuity") in checks           # suggested amounts not counted
    allowed = ("Cash reconciliation", "Receipt arithmetic", "Paid personally", "Tip paid by card", "Suggested gratuity")
    assert not [f for f in res.flags if f.check not in allowed]
    summary = json.loads((res.version_dir / "run_summary.json").read_text())
    assert summary["status"].startswith("READY FOR HUMAN REVIEW")
    assert summary["numbers"]["over_short"] == "-2.00"
    assert summary["numbers"]["receipts_total"] == "331.52"


def test_topsheet_values_and_preservation(run):
    import openpyxl
    res, _, _ = run
    assert res.preservation["passed"]
    ws = openpyxl.load_workbook(res.version_dir / "PC001_TopSheet.xlsx")["Top Sheet"]
    assert [ws[f"A{r}"].value for r in (10, 11, 12, 13)] == ["PC001-001", "PC001-002", "PC001-003", "PC001-004"]
    assert [ws[f"G{r}"].value for r in (10, 11, 12, 13)] == [81.3, 94.94, 100.29, 54.99]  # confirmed final incl. tip
    assert ws["G28"].value == 66.48 and ws["G25"].value == "=SUM(G10:G24)"


def test_originals_preserved_and_locked(run):
    res, project, before = run
    assert {p.name: sha256_file(p) for p in (FIX / "receipts").iterdir()} == before
    summary = json.loads((res.version_dir / "run_summary.json").read_text())
    assert all(o["unchanged"] and o["read_only"] for o in summary["originals"])


def test_annotated_receipts_carry_only_number_and_circles(run):
    res, _, _ = run
    for name in EXPECTED:
        a = (res.version_dir / "receipts_annotated" / name).read_bytes()
        c = (res.version_dir / "receipts_clean" / name).read_bytes()
        assert a != c
        txt = PdfReader(io.BytesIO(a)).pages[0].extract_text()
        assert name.split("_")[0] in txt                        # the receipt number (full style for this template)
        for unwanted in ("Verified", "Acct", "VENDOR", "DRAFT"):
            assert unwanted not in txt


def test_no_unexpected_network_attempts(run):
    # The only blocked attempts allowed are the deliberate ones made by test_netguard.py.
    intentional = ("203.0.113", "198.51.100", "example.com")
    assert not [a for a in netguard.LOG.attempts if not any(t in a.target for t in intentional)]


def test_second_run_creates_new_version_without_overwriting(run, chart_module):
    res, project, _ = run
    first = {p: p.read_bytes() for p in res.version_dir.rglob("*") if p.is_file()}
    res2 = run_envelope(FIX / "envelope.yaml", FIX / "receipts", PROFILE, chart_module, project, FIX / "review.yaml")
    assert res2.version_dir.name == "v2"
    assert all(p.read_bytes() == b for p, b in first.items())
    assert len([l for l in (project / "originals" / "manifest.jsonl").read_text().splitlines() if l]) == 4  # no duplicates on re-run


def test_master_template_envelope(tmp_path, chart_module):
    """The user-supplied master template: index numbering, numeric line numbers, template formulas untouched."""
    import openpyxl
    profile = FIX / "templates" / "master_pc" / "PC_Sheet_Template.profile.yaml"
    template = FIX / "templates" / "master_pc" / "PC_Sheet_Template.xlsx"
    before = sha256_file(template)
    res = run_envelope(FIX / "envelope.yaml", FIX / "receipts", profile, FIX / "jobs" / "LK-0042_line_list.csv",
                       tmp_path, FIX / "review.yaml")
    assert res.preservation["passed"]
    assert any("S3" in a for a in res.preservation["allowed_changes_seen"])
    assert sha256_file(template) == before
    ws = openpyxl.load_workbook(res.version_dir / "PC001_TopSheet.xlsx")["PC Formulas (1)"]
    assert [ws[f"B{r}"].value for r in (8, 9, 10, 11)] == [1, 2, 3, 4]
    assert [ws[f"F{r}"].value for r in (8, 9, 10, 11)] == [2410, 3510, 2510, 3520]   # numbers, so the breakdown formulas work
    assert [ws[f"E{r}"].value for r in (8, 9, 10, 11)] == [81.3, 94.94, 100.29, 54.99]
    assert ws["E48"].value == 400 and ws["A3"].value == "Jordan Avery" and ws["E3"].value == 5550102020
    assert ws["E44"].value == '=IF(SUM(E8:E42),SUM(E8:E42),"")'
    assert ws["S3"].value == "LK-0042-PC001"                                # unique envelope ID replaces "1 of N"
    assert ws["D8"].value == "Gaffer tape, zip ties, gloves, sash cord"     # purchase description, as entered
    assert ws["D10"].value == "Brass ship lantern, rope coil (hero props)"
    txt = PdfReader(str(res.version_dir / "receipts_annotated" / EXPECTED[0])).pages[0].extract_text()
    assert "#1" in txt
