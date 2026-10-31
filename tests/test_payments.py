"""Payment components: method, who paid, tips counted once, and the separate money buckets."""

from datetime import date
from decimal import Decimal

from productiontools.petty_cash.models import Box, Envelope, FieldValue, Receipt
from productiontools.petty_cash.payments import classify, envelope_amount, float_disbursement, personal_owed
from productiontools.petty_cash.policy import PettyCashRules
from productiontools.petty_cash.recon import reconcile, summary_numbers

D = Decimal
PERMIT = PettyCashRules("cash_and_approved_personal_cards", ["AMEX 4201"], "test")
CASH_ONLY = PettyCashRules("cash_only", ["AMEX 4201"], "test")


def make(name, total, pay, pay_id=None, tip=None, tip_method=None, printed=None, rules=PERMIT, **attrs):
    r = Receipt(name, None, name * 8, [])
    vals = {"vendor": "V" + name, "date": date(2026, 10, 3), "total": D(total), "payment": pay, "payment_id": pay_id,
            "tip": D(tip) if tip else None, "tip_method": tip_method, "printed_total": D(printed) if printed else D(total)}
    for k, v in vals.items():
        r.fields[k] = FieldValue(k, v, 0.95, 0, Box(0, 0, 1, 1), verified=True)
    r.fields["total"].tip_status = "verified" if tip else "none"
    r.number, r.account_code, r.description, r.verified_by = name, "2410", "x", "Tester"
    for k, v in attrs.items():
        setattr(r, k, v)
    classify(r, rules=rules)
    return r


def test_card_tip_is_inside_the_card_charge():
    r = make("U", "54.99", "Mastercard", "MASTERCARD 0000", tip="9.00", tip_method="card", printed="45.99",
             paid_by="crew_personal", personal_card_approved=True, reimbursed_from_float=True, reimbursement_documentation="Kept from float, noted on envelope (fictional)")
    assert [(c.label, c.amount) for c in r.payments] == [("bill", D("54.99"))]
    assert envelope_amount(r) == D("54.99")


def test_cash_tip_on_personal_card_bill_is_its_own_component():
    r = make("W", "48.00", "Visa", "VISA 1111", tip="8.00", tip_method="cash", printed="40.00",
             paid_by="crew_personal", personal_card_approved=True, tip_paid_by="petty_cash_float")
    # bill not yet confirmed as reimbursed from the float -> separate; the float-paid cash tip counts once
    assert [(c.label, c.amount, c.paid_by, c.eligibility) for c in r.payments] == [
        ("bill", D("40.00"), "crew_personal", "separate"), ("cash tip", D("8.00"), "petty_cash_float", "eligible")]
    assert (envelope_amount(r), float_disbursement(r), personal_owed(r)) == (D("8.00"), D("8.00"), D("40.00"))


def test_personal_card_only_enters_envelope_with_documented_float_reimbursement():
    owed = make("P", "30.00", "Visa", "VISA 5555", paid_by="crew_personal", personal_card_approved=True)
    assert owed.payments[0].eligibility == "separate"                       # never assumed reimbursed
    assert (envelope_amount(owed), float_disbursement(owed), personal_owed(owed)) == (D("0"), D("0"), D("30.00"))
    undocumented = make("P", "30.00", "Visa", "VISA 5555", paid_by="crew_personal", personal_card_approved=True,
                        reimbursed_from_float=True)
    assert undocumented.payments[0].eligibility == "separate" and "not documented" in undocumented.payments[0].reason
    kept = make("Q", "30.00", "Visa", "VISA 5555", paid_by="crew_personal", personal_card_approved=True, reimbursed_from_float=True, reimbursement_documentation="Kept from float, noted on envelope (fictional)")
    assert (envelope_amount(kept), float_disbursement(kept), personal_owed(kept)) == (D("30.00"), D("30.00"), D("0"))


def test_personal_cash_also_needs_documented_float_reimbursement():
    r = make("C", "12.00", "Cash", paid_by="crew_personal")
    assert r.payments[0].eligibility == "separate"
    r2 = make("C", "12.00", "Cash", paid_by="crew_personal", reimbursed_from_float=True, reimbursement_documentation="Kept from float, noted on envelope (fictional)")
    assert r2.payments[0].eligibility == "eligible"


def _env(receipts, excluded=(), returned="0.00", reported="0.00", rules=PERMIT):
    env = Envelope("PC9", "P", "LK", "Co", "Crew", "Art", "C", date(2026, 10, 1), date(2026, 10, 31),
                   D("100.00"), D(returned), D(reported))
    env.receipts, env.excluded, env.rules = list(receipts), list(excluded), rules
    return env


def test_cash_return_reconciles_with_template_balance():
    cash = make("A", "10.00", "Cash")
    card = make("P", "30.00", "Visa", "VISA 5555", paid_by="crew_personal", personal_card_approved=True, reimbursed_from_float=True, reimbursement_documentation="Kept from float, noted on envelope (fictional)")
    env = _env([cash, card], returned="60.00", reported="40.00")
    n = summary_numbers(env)
    assert (n["eligible_total"], n["float_disbursements"], n["expected_return"], n["template_balance"], n["over_short"]) == (
        D("40.00"), D("40.00"), D("60.00"), D("60.00"), D("0.00"))
    checks = {(f.severity, f.check) for f in reconcile(env, {"2410": "Art"})}
    assert ("ERROR", "Cash reconciliation") not in checks and ("ERROR", "Top sheet balance") not in checks
    assert ("WARNING", "Personal card") in checks


def test_unconfirmed_personal_card_stays_out_and_cash_still_reconciles():
    cash = make("A", "10.00", "Cash")
    pending = make("P", "30.00", "Visa", "VISA 5555", paid_by="crew_personal", personal_card_approved=True)
    env = _env([cash], [pending], returned="90.00", reported="10.00")
    n = summary_numbers(env)
    assert (n["eligible_total"], n["expected_return"], n["template_balance"], n["personal_owed"]) == (
        D("10.00"), D("90.00"), D("90.00"), D("30.00"))
    checks = {(f.severity, f.scope, f.check) for f in reconcile(env, {"2410": "Art"})}
    assert ("WARNING", "P", "Separate reimbursement") in checks
    assert not [c for c in checks if c[0] == "ERROR"]


def test_cash_only_job_cash_reconciliation():
    a, b = make("A", "10.00", "Cash", rules=CASH_ONLY), make("B", "15.50", "Cash", rules=CASH_ONLY)
    n = summary_numbers(_env([a, b], returned="74.50", reported="25.50", rules=CASH_ONLY))
    assert (n["eligible_total"], n["expected_return"], n["over_short"], n["personal_owed"]) == (
        D("25.50"), D("74.50"), D("0.00"), D("0"))
