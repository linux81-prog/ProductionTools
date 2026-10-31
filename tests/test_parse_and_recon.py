from datetime import date
from decimal import Decimal

from productiontools.petty_cash.models import Box, Envelope, FieldValue, Page, Receipt, Token
from productiontools.petty_cash.parse import parse_receipt, tidy_vendor
from productiontools.petty_cash.payments import classify
from productiontools.petty_cash.recon import reconcile, summary_numbers
from PIL import Image


def _page(lines):
    """Build a fake OCR page: each line is a list of (text, x) at increasing heights."""
    toks = []
    for row, words in enumerate(lines):
        y = 40 + row * 40
        for text, x in words:
            toks.append(Token(text, 0.99, Box(x, y, x + 12 * len(text), y + 24), 0))
    return Page(0, Image.new("RGB", (800, 40 + 40 * len(lines) + 40), "white"), toks, "photo")


def test_parse_basic_receipt():
    page = _page([[("SUNSET", 200), ("LUMBER", 300)], [("10/03/2026", 40), ("4:10", 600)],
                  [("SUBTOTAL", 40), ("20.00", 600)], [("TAX", 40), ("1.90", 600)], [("TOTAL", 40), ("$21.90", 600)],
                  [("CASH", 40), ("25.00", 600)], [("CHANGE", 40), ("3.10", 600)]])
    f = parse_receipt([page])
    assert f["vendor"].value == "Sunset Lumber"
    assert f["date"].value == date(2026, 10, 3)
    assert f["total"].value == Decimal("21.90") and f["total"].confidence > 0.9
    assert f["payment"].value == "Cash"
    assert f["total"].box is not None


def test_total_line_split_from_amount_and_balance_due_zero_ignored():
    page = _page([[("PROP", 40), ("SHOP", 120)], [("Invoice", 40), ("Date:", 140), ("Oct", 220), ("2,", 270), ("2026", 300)],
                  [("Due", 40), ("Date:", 100), ("Nov", 200), ("1,", 250), ("2026", 280)],
                  [("Subtotal", 40), ("$50.00", 600)], [("Tax", 40), ("$4.75", 600)], [("Total", 40), ("$54.75", 600)],
                  [("Balance", 40), ("Due", 140), ("$0.00", 600)]])
    f = parse_receipt([page])
    assert f["total"].value == Decimal("54.75")
    assert f["date"].value == date(2026, 10, 2)  # invoice date, not due date


def test_arithmetic_mismatch_lowers_confidence():
    page = _page([[("CAFE", 200), ("NINE", 300)], [("10/09/2026", 40)], [("SUBTOTAL", 40), ("10.00", 600)],
                  [("TAX", 40), ("0.95", 600)], [("TOTAL", 40), ("11.45", 600)]])
    t = parse_receipt([page])["total"]
    assert t.value == Decimal("11.45") and t.needs_review and "cross-check failed" in t.note


def test_missing_total_is_reported_not_guessed():
    page = _page([[("SOME", 200), ("STORE", 300)], [("10/09/2026", 40)], [("WIDGET", 40), ("4.00", 600)]])
    t = parse_receipt([page])["total"]
    assert t.value is None and t.needs_review


def test_tidy_vendor():
    assert tidy_vendor("HARDWARE BARN") == "Hardware Barn"
    assert tidy_vendor("PROP DEPOT SUPPLY CO.") == "Prop Depot Supply Co."
    assert tidy_vendor("Blue Bottle") == "Blue Bottle"


def _receipt(name, vendor, d, sub, tax, total, verified=True, code="2410", pay="Cash"):
    r = Receipt(name, None, name * 4, [])
    for k, v in (("vendor", vendor), ("date", d), ("subtotal", sub), ("tax", tax), ("total", total), ("payment", pay)):
        r.fields[k] = FieldValue(k, v, 0.95, 0, Box(0, 0, 1, 1), verified=verified)
    r.account_code, r.description, r.verified_by = code, "test", ("Reviewer" if verified else None)
    r.number = name
    classify(r)
    return r


def _env(receipts, returned="0.00", reported=None):
    total = sum(r.total for r in receipts)
    env = Envelope("PC9", "Prod", "P-1", "Co", "Crew", "Art", "Coord", date(2026, 10, 1), date(2026, 10, 31),
                   Decimal("100.00"), Decimal(returned), Decimal(reported) if reported else total)
    env.receipts = receipts
    return env


D = Decimal


def test_balanced_envelope_has_no_errors(chart):
    env = _env([_receipt("A", "X", date(2026, 10, 2), D("40.00"), D("3.80"), D("43.80"))], returned="56.20")
    flags = reconcile(env, chart)
    assert not [f for f in flags if f.severity == "ERROR"]
    n = summary_numbers(env)
    assert n["expected_return"] == D("56.20") and n["over_short"] == D("0.00")


def test_shortage_and_overage(chart):
    r = _receipt("A", "X", date(2026, 10, 2), D("40.00"), D("3.80"), D("43.80"))
    short = reconcile(_env([r], returned="55.20"), chart)
    assert any(f.check == "Cash reconciliation" and "SHORT by $1.00" in f.message for f in short)
    over = reconcile(_env([r], returned="57.20"), chart)
    assert any("OVER by $1.00" in f.message for f in over)


def test_flags_duplicates_dates_limits_codes_and_unverified(chart):
    a = _receipt("A", "X", date(2026, 10, 2), D("10.00"), D("0.00"), D("10.00"))
    b = _receipt("B", "X", date(2026, 10, 2), D("10.00"), D("0.00"), D("10.00"))
    c = _receipt("C", "Y", date(2026, 9, 1), D("300.00"), D("0.00"), D("300.00"), code="0000")
    d = _receipt("D", "Z", date(2026, 10, 5), D("1.00"), D("0.00"), D("1.00"), verified=False, pay="Visa")
    checks = {(f.scope, f.check) for f in reconcile(_env([a, b, c, d]), chart)}
    assert ("B", "Possible duplicate") in checks
    assert ("C", "Date outside period") in checks and ("C", "Over limit") in checks and ("C", "Account code") in checks
    assert ("D", "Not verified") in checks and ("D", "Needs decision") in checks


def test_reported_total_mismatch(chart):
    r = _receipt("A", "X", date(2026, 10, 2), D("40.00"), D("3.80"), D("43.80"))
    flags = reconcile(_env([r], returned="56.20", reported="45.00"), chart)
    assert any(f.check == "Reported total" for f in flags)
