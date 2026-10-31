"""Production-specific petty cash rules (eligibility), applied in Create and Verify modes."""

import copy
from decimal import Decimal

import pytest

from conftest import FIX
from productiontools.petty_cash.payments import envelope_amount
from productiontools.petty_cash.policy import (ELIGIBLE, INELIGIBLE, REVIEW, SEPARATE, PettyCashRules,
                                               check_completed_envelope, load_rules, receipt_status)
from productiontools.petty_cash.recon import reconcile, summary_numbers
from test_payments import _env, make

D = Decimal
DOC = dict(reimbursed_from_float=True, reimbursement_documentation="Kept from float, noted on envelope (fictional)")
POLICIES = ["cash_only", "cash_and_approved_personal_cards", "case_by_case"]


def rules(policy):
    return PettyCashRules(policy, ["AMEX 4201"], "test")


@pytest.mark.parametrize("policy", POLICIES)
def test_production_card_always_ineligible(policy):
    by_list = make("C", "50.00", "Amex", "AMEX 4201", rules=rules(policy))            # matches production card list
    by_reviewer = make("D", "50.00", "Visa", "VISA 9999", paid_by="company_card",       # reviewer identified it
                       personal_card_approved=True, authorization="X", rules=rules(policy))
    for r in (by_list, by_reviewer):
        assert [c.eligibility for c in r.payments] == [INELIGIBLE]
        assert receipt_status(r) == INELIGIBLE and envelope_amount(r) == D("0")


def test_personal_card_on_cash_only_job_ineligible():
    r = make("P", "30.00", "Visa", "VISA 5555", paid_by="crew_personal", personal_card_approved=True, rules=rules("cash_only"),
             **DOC)                                                  # even "reimbursed from the float" cannot override
    assert r.payments[0].eligibility == INELIGIBLE and "cash only" in r.payments[0].reason
    assert envelope_amount(r) == D("0")


def test_personal_card_on_permitting_job_requires_review_then_approval():
    pending = make("P", "30.00", "Visa", "VISA 5555", paid_by="crew_personal", rules=rules("cash_and_approved_personal_cards"))
    assert pending.payments[0].eligibility == REVIEW and envelope_amount(pending) == D("0")     # never automatic
    approved = make("P", "30.00", "Visa", "VISA 5555", paid_by="crew_personal", personal_card_approved=True,
                    rules=rules("cash_and_approved_personal_cards"))
    assert approved.payments[0].eligibility == SEPARATE and envelope_amount(approved) == D("0")  # reimbursement not confirmed
    listed = make("P", "30.00", "Visa", "VISA 5555", paid_by="crew_personal", personal_card_approved=True,
                  rules=rules("cash_and_approved_personal_cards"), **DOC)
    assert listed.payments[0].eligibility == ELIGIBLE and envelope_amount(listed) == D("30.00")
    flags = {(f.severity, f.check) for f in reconcile(_env([listed], reported="30.00", returned="70.00"), {"2410": "A"})}
    assert ("WARNING", "Personal card") in flags          # still flagged for sign-off even when allowed
    assert ("ERROR", "Cash reconciliation") not in flags and ("ERROR", "Top sheet balance") not in flags


def test_case_by_case_needs_approval_and_authorization():
    r1 = make("P", "30.00", "Visa", "VISA 5555", paid_by="crew_personal", personal_card_approved=True, rules=rules("case_by_case"))
    assert r1.payments[0].eligibility == REVIEW and "authorization" in r1.payments[0].reason
    r2 = make("P", "30.00", "Visa", "VISA 5555", paid_by="crew_personal", personal_card_approved=True,
              authorization="Email from UPM 10/03 (fictional)", rules=rules("case_by_case"), **DOC)
    assert r2.payments[0].eligibility == ELIGIBLE


@pytest.mark.parametrize("policy", POLICIES)
def test_unknown_card_owner_requires_review(policy):
    r = make("U", "20.00", "Visa", "VISA 1234", personal_card_approved=True, rules=rules(policy))
    assert r.payments[0].paid_by is None
    assert r.payments[0].eligibility == REVIEW and "never assumed to be a personal card" in r.payments[0].reason


def test_unknown_payment_method_requires_review():
    r = make("M", "20.00", None, rules=rules("cash_and_approved_personal_cards"))
    assert r.payments[0].eligibility == REVIEW and "payment method" in r.payments[0].reason


@pytest.mark.parametrize("policy", POLICIES)
def test_production_card_bill_with_cash_tip_not_automatically_included(policy):
    kw = dict(tip="8.00", tip_method="cash", printed="40.00", tip_paid_by="petty_cash_float", rules=rules(policy))
    r = make("T", "48.00", "Amex", "AMEX 4201", **kw)
    assert [(c.label, c.eligibility) for c in r.payments] == [("bill", INELIGIBLE), ("cash tip", REVIEW)]
    assert envelope_amount(r) == D("0") and receipt_status(r) == REVIEW
    only_confirmed = make("T", "48.00", "Amex", "AMEX 4201", tip_eligible_confirmed=True, **kw)
    assert only_confirmed.payments[1].eligibility == REVIEW                        # confirmation alone is not enough
    documented = make("T", "48.00", "Amex", "AMEX 4201", tip_eligible_confirmed=True,
                      tip_documentation="Signed tip slip, envelope PC009 (fictional)", **kw)
    assert documented.payments[1].eligibility == ELIGIBLE and envelope_amount(documented) == D("8.00")


def test_acknowledged_exclusion_does_not_block_but_unresolved_review_does():
    excluded = make("C", "50.00", "Amex", "AMEX 4201")
    cash = make("A", "10.00", "Cash")
    env = _env([cash], [excluded], returned="90.00", reported="10.00")
    blocking = [f for f in reconcile(env, {"2410": "A"}) if f.severity == "ERROR"]
    assert [f.check for f in blocking] == ["Production card - ineligible"]          # not yet acknowledged
    excluded.exclusion_acknowledged = True
    flags = reconcile(env, {"2410": "A"})
    assert not [f for f in flags if f.severity == "ERROR"]                          # envelope can now be finalized
    assert ("INFO", "Production card - ineligible") in {(f.severity, f.check) for f in flags}
    assert summary_numbers(env)["ineligible_company_card"] == D("50.00")            # documented separately
    pending = make("U", "20.00", "Visa", "VISA 1234")
    pending.exclusion_acknowledged = True                                           # acknowledging cannot resolve a question
    env2 = _env([cash], [excluded, pending], returned="90.00", reported="10.00")
    assert ("ERROR", "Needs decision") in {(f.severity, f.check) for f in reconcile(env2, {"2410": "A"})}


def test_verify_mode_flags_prohibited_cards_without_modifying_anything():
    cash_only = rules("cash_only")
    listed = [make("1", "10.00", "Cash", rules=cash_only),
              make("2", "30.00", "Visa", "VISA 5555", paid_by="crew_personal", personal_card_approved=True, rules=cash_only, **DOC),
              make("3", "50.00", "Amex", "AMEX 4201", rules=cash_only),
              make("4", "20.00", "Visa", "VISA 1234", rules=cash_only)]
    before = copy.deepcopy([(r.number, r.total, r.paid_by, [(c.amount, c.eligibility) for c in r.payments]) for r in listed])
    findings = check_completed_envelope(listed, cash_only)
    sev = {(f["receipt"], f["severity"], f["check"]) for f in findings}
    assert ("1", "PASS", "Policy") in sev
    assert ("2", "ERROR", "Policy violation") in sev            # personal card on a cash-only job
    assert ("3", "ERROR", "Policy violation") in sev            # production card
    assert ("4", "WARNING", "Needs review") in sev              # unknown card owner
    after = [(r.number, r.total, r.paid_by, [(c.amount, c.eligibility) for c in r.payments]) for r in listed]
    assert after == before                                      # never silently modifies the submitted envelope
    permit = check_completed_envelope(listed, rules("cash_and_approved_personal_cards"))
    assert ("2", "PASS", "Policy") in {(f["receipt"], f["severity"], f["check"]) for f in permit}
    not_kept = [make("5", "30.00", "Visa", "VISA 5555", paid_by="crew_personal", personal_card_approved=True, rules=cash_only)]
    found = check_completed_envelope(not_kept, rules("cash_and_approved_personal_cards"))
    assert ("5", "WARNING", "Reimbursement not confirmed") in {(f["receipt"], f["severity"], f["check"]) for f in found}
    assert ("3", "ERROR", "Policy violation") in {(f["receipt"], f["severity"], f["check"]) for f in permit}


def test_rules_file_and_strict_default():
    r = load_rules(FIX / "jobs" / "LK-0042_petty_cash_rules.yaml")
    assert r.payment_policy == "cash_and_approved_personal_cards" and r.production_cards == ["AMEX 4201"]
    assert load_rules(None).payment_policy == "cash_only"


def test_create_mode_keeps_ineligible_out_of_topsheet(tmp_path):
    """End to end on a cash-only job: personal-card receipts stay out of the top sheet and totals but are documented."""
    import openpyxl
    from productiontools.petty_cash.pipeline import run_envelope
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("payment_policy: cash_only\nproduction_cards: ['AMEX 4201']\n")
    res = run_envelope(FIX / "envelope.yaml", FIX / "receipts", FIX / "templates" / "master_pc" / "PC_Sheet_Template.profile.yaml",
                       FIX / "jobs" / "LK-0042_line_list.csv", tmp_path / "proj", FIX / "review.yaml", rules_path=rules_file)
    assert [r.source_name for r in res.envelope.excluded] == ["03_prop_depot_invoice.pdf", "04_harbor_light_diner_photo.jpg"]
    assert len(res.envelope.receipts) == 2
    ws = openpyxl.load_workbook(res.version_dir / "LK-0042-PC001_TopSheet.xlsx")["PC Formulas (1)"]
    assert [ws[f"E{r}"].value for r in (8, 9, 10)] == [81.3, 94.94, None]
    n = summary_numbers(res.envelope)
    assert (n["eligible_total"], n["ineligible_policy"]) == (D("176.24"), D("155.28"))
    assert {(f.scope, f.check) for f in res.flags} >= {("03_prop_depot_invoice.pdf", "Job policy - ineligible"),
                                                       ("04_harbor_light_diner_photo.jpg", "Job policy - ineligible")}
    assert sorted(p.name for p in (res.version_dir / "receipts_annotated").iterdir()) == [
        "LK-0042-PC001-001_2026-10-14_Hardware-Barn_81.30.pdf", "LK-0042-PC001-002_2026-10-15_Copper-Kettle-Cafe_94.94.pdf"]
