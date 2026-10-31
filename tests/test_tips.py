"""Handwritten tips and gratuities (fictional receipts with simulated handwriting)."""

from decimal import Decimal

import pytest

from conftest import FIX
from productiontools.core.audit import AuditLog
from productiontools.petty_cash.annotate import plan_marks
from productiontools.petty_cash.extract import load_pages
from productiontools.petty_cash.models import Receipt
from productiontools.petty_cash.parse import parse_receipt
from productiontools.petty_cash.recon import _tip_flags
from productiontools.petty_cash.review import apply_review

D = Decimal


def _load(path):
    pages = load_pages(path)
    r = Receipt(path.name, path, "x", pages, parse_receipt(pages))
    r.number, r.seq, r.label = "PC001-001", 1, "#1"
    return r


def _flags(r):
    out = []
    _tip_flags(r, "R", lambda *a: out.append(a))
    return {(f[0], f[2]) for f in out}


@pytest.fixture(scope="module")
def cases():
    return {n: _load(FIX / "tips" / n) for n in ("tip_no_final.jpg", "tip_mismatch.jpg", "suggested_only.jpg")} | {
        "both": _load(FIX / "receipts" / "04_harbor_light_diner_photo.jpg")}


def test_tip_and_final_written_and_consistent(cases):
    r = cases["both"]
    assert (r.val("printed_total"), r.val("tip"), r.val("final_total"), r.total) == (D("45.99"), D("9.00"), D("54.99"), D("54.99"))
    assert r.fields["total"].tip_status == "verified"
    for k in ("tip", "final_total", "total"):
        assert r.fields[k].needs_review          # handwriting is never silently accepted
    assert r.val("tip_method") == "card"
    assert ("INFO", "Tip paid by card") in _flags(r) and ("WARNING", "Handwritten amount") in _flags(r)


def test_tip_without_final_proposes_amount_needing_confirmation(cases):
    r = cases["tip_no_final.jpg"]
    t = r.fields["total"]
    assert (t.value, t.tip_status, t.box) == (D("53.99"), "proposed", None)
    assert t.needs_review and "needs confirmation" in t.note
    assert ("WARNING", "Proposed final amount") in _flags(r)
    # Annotation: circle the printed total and the tip that appear; never write the calculation on the receipt
    circled = {k for k, _, _ in plan_marks(r.pages[0], r, 0.5).circles}
    assert {"printed_total", "tip"} <= circled and "total" not in circled


def test_mismatch_is_flagged(cases):
    r = cases["tip_mismatch.jpg"]
    t = r.fields["total"]
    assert (t.value, t.tip_status) == (D("55.99"), "mismatch")
    assert t.confidence <= 0.5 and "difference 1.00" in t.note
    assert ("WARNING", "Tip arithmetic") in _flags(r)


def test_suggested_gratuity_is_never_counted(cases):
    r = cases["suggested_only.jpg"]
    assert r.total == D("45.99") and r.val("tip") is None
    assert r.fields["total"].tip_status == "none"
    assert ("INFO", "Suggested gratuity") in _flags(r)
    assert ("WARNING", "Tip payment method") not in _flags(r)


def test_reviewer_corrects_unreadable_tip_and_total_is_recalculated(tmp_path):
    r = _load(FIX / "tips" / "tip_mismatch.jpg")
    review = {"reviewer": "Tester", "receipts": {"tip_mismatch.jpg": {
        "corrections": {"final_total": {"value": "54.99", "reason": "handwriting re-read: 54.99, not 55.99"}},
        "confirm": True}}}
    log = tmp_path / "audit.log"
    apply_review([r], review, AuditLog(log))
    assert r.total == D("54.99") and r.fields["total"].tip_status == "verified"
    assert "total_recalculated" in log.read_text()
    assert ("WARNING", "Tip arithmetic") not in _flags(r)


def test_confirming_a_proposed_total_is_logged(tmp_path):
    r = _load(FIX / "tips" / "tip_no_final.jpg")
    log = tmp_path / "audit.log"
    apply_review([r], {"reviewer": "Tester", "receipts": {"tip_no_final.jpg": {"confirm": True}}}, AuditLog(log))
    assert r.fields["total"].verified and "proposed_total_confirmed" in log.read_text()
    assert ("INFO", "Proposed final amount") in _flags(r)


def test_tip_above_printed_total_is_not_added_twice():
    from PIL import Image

    from productiontools.petty_cash.models import Box, Page, Token

    lines = [[("BAR", 200), ("NINE", 300)], [("10/09/2026", 40)], [("SUBTOTAL", 40), ("40.00", 600)],
             [("TAX", 40), ("3.80", 600)], [("TIP", 40), ("8.00", 600)], [("TOTAL", 40), ("51.80", 600)],
             [("VISA", 40), ("51.80", 600)]]
    toks = [Token(t, 0.99, Box(x, 40 + i * 40, x + 12 * len(t), 64 + i * 40), 0) for i, ws in enumerate(lines) for t, x in ws]
    f = parse_receipt([Page(0, Image.new("RGB", (800, 400), "white"), toks, "photo")])
    assert f["total"].value == D("51.80") and f["tip"].value is None       # tip already inside the printed total
    assert f["other_charges"].value == D("8.00") and "cross-check passed" in f["printed_total"].note
