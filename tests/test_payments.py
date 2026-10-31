"""Who paid, payment method and reimbursement eligibility."""

from datetime import date
from decimal import Decimal

from productiontools.petty_cash.models import Box, Envelope, FieldValue, Receipt
from productiontools.petty_cash.payments import classify, envelope_amount
from productiontools.petty_cash.recon import reconcile, summary_numbers

D = Decimal


def _r(name, total, pay, pay_id=None, tip=None, tip_method=None, printed=None, paid_by=None, tip_paid_by=None):
    r = Receipt(name, None, name * 8, [])
    vals = {"vendor": "V", "date": date(2026, 10, 3), "total": D(total), "payment": pay, "payment_id": pay_id,
            "tip": D(tip) if tip else None, "tip_method": tip_method, "printed_total": D(printed) if printed else D(total)}
    for k, v in vals.items():
        r.fields[k] = FieldValue(k, v, 0.95, 0, Box(0, 0, 1, 1), verified=True)
    r.fields["total"].tip_status = "verified" if tip else "none"
    r.number, r.account_code, r.description, r.verified_by = name, "2410", "x", "Tester"
    r.paid_by, r.tip_paid_by = paid_by, tip_paid_by
    r.payments = classify(r, ["AMEX 4201"])
    return r


def test_cash_is_float_but_card_is_unknown_until_classified():
    assert [c.paid_by for c in _r("A", "10.00", "Cash").payments] == ["petty_cash_float"]
    unknown = _r("B", "20.00", "Visa", "VISA 1234")
    assert [c.paid_by for c in unknown.payments] == [None]            # never guessed
    assert envelope_amount(unknown) == D("20.00")                       # counted, but blocked by an ERROR


def test_company_card_is_never_reimbursed():
    r = _r("C", "50.00", "Amex", "AMEX 4201")                          # matches the job's production card list
    assert [c.paid_by for c in r.payments] == ["company_card"]
    assert envelope_amount(r) == D("0.00")
    r2 = _r("C2", "50.00", "Visa", "VISA 9999", paid_by="company_card")  # reviewer says company card
    assert envelope_amount(r2) == D("0.00")


def test_card_bill_with_cash_tip_is_split_and_counted_once():
    # Bill $40 on the production card, $8 cash tip from the float: only the tip belongs in petty cash.
    r = _r("T", "48.00", "Amex", "AMEX 4201", tip="8.00", tip_method="cash", printed="40.00", tip_paid_by="petty_cash_float")
    assert [(c.label, c.amount, c.paid_by) for c in r.payments] == [
        ("bill", D("40.00"), "company_card"), ("cash tip", D("8.00"), "petty_cash_float")]
    assert envelope_amount(r) == D("8.00")


def test_card_tip_is_inside_the_card_charge():
    r = _r("U", "54.99", "Mastercard", "MASTERCARD 0000", tip="9.00", tip_method="card", printed="45.99", paid_by="crew_personal")
    assert [(c.amount, c.paid_by) for c in r.payments] == [(D("54.99"), "crew_personal")]
    assert envelope_amount(r) == D("54.99")


def test_cash_tip_with_unknown_payer_needs_review():
    r = _r("W", "48.00", "Visa", "VISA 1111", tip="8.00", tip_method="cash", printed="40.00", paid_by="crew_personal")
    assert [c.paid_by for c in r.payments] == ["crew_personal", None]


def test_envelope_flags_and_totals():
    env = Envelope("PC9", "P", "LK", "Co", "Crew", "Art", "C", date(2026, 10, 1), date(2026, 10, 31),
                   D("100.00"), D("0.00"), D("0.00"))
    env.receipts = [_r("A", "10.00", "Cash"), _r("B", "20.00", "Visa", "VISA 1234"),
                    _r("P", "30.00", "Visa", "VISA 5555", paid_by="crew_personal")]
    env.excluded = [_r("C", "50.00", "Amex", "AMEX 4201")]
    env.reported_total = D("60.00")
    env.cash_returned = D("40.00")
    checks = {(f.severity, f.scope, f.check) for f in reconcile(env, {"2410": "Art"})}
    assert ("ERROR", "B", "Who paid?") in checks
    assert ("INFO", "P", "Paid personally") in checks
    assert ("WARNING", "C", "Excluded receipt") in checks
    n = summary_numbers(env)
    assert (n["receipts_total"], n["reimbursable_personal"], n["unclassified"], n["excluded_company_card"]) == (
        D("60.00"), D("30.00"), D("20.00"), D("50.00"))
