"""Production-specific petty cash rules: what may go into an envelope.

Each job has a rules file, e.g.:

    payment_policy: cash_and_approved_personal_cards   # or cash_only / case_by_case
    production_cards: ["AMEX 4201"]                     # production company card identifiers

The rules decide ELIGIBILITY. Who paid and how are recorded separately (payments.py).

Outcomes for each payment component:
  eligible         - counted in the envelope
  review_required  - NOT counted; a person must resolve it before finalizing
  separate         - eligible for reimbursement, but NOT through this envelope (the
                     reimbursement from the float was not confirmed): handled separately
  ineligible       - never counted in this envelope (documented as excluded)

Personally paid expenses and the top sheet (Option B, approved by the user):
  The master top sheet nets every listed expense against the float. So a personally
  paid expense may only be listed when the reviewer confirms the crew member was
  reimbursed by retaining that amount from the float, and documents it. Then the
  expected physical cash return equals the template's own balance. Without that
  confirmation the expense stays out of the envelope and is flagged for separate
  handling. It is never assumed to be reimbursed.

Absolute rules (no job setting can change these):
  * Production company card purchases are never eligible.
  * An unidentified card is never assumed to be personal.
  * Nothing is ever reimbursed automatically.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

POLICIES = {
    "cash_only": "Cash only - no card purchases of any kind",
    "cash_and_approved_personal_cards": "Cash, plus personally paid card expenses that are individually approved",
    "case_by_case": "Non-cash transactions only with case-by-case authorization (approval + authorization reference)",
}

ELIGIBLE, REVIEW, INELIGIBLE, SEPARATE = "eligible", "review_required", "ineligible", "separate"


@dataclass
class PettyCashRules:
    payment_policy: str = "cash_only"          # strictest by default
    production_cards: list = field(default_factory=list)
    source: str = "default (no rules file supplied: strictest policy)"

    @property
    def description(self) -> str:
        return POLICIES[self.payment_policy]


def load_rules(path: Path | None) -> PettyCashRules:
    if path is None:
        return PettyCashRules()
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    policy = data.get("payment_policy", "cash_only")
    if policy not in POLICIES:
        raise ValueError(f"payment_policy must be one of {sorted(POLICIES)}")
    return PettyCashRules(policy, [str(c) for c in data.get("production_cards", [])], Path(path).name)


def evaluate(component, receipt, rules: PettyCashRules) -> tuple[str, str]:
    """Decide whether one payment component may enter the envelope, and why."""
    method, paid_by = component.method, component.paid_by

    if paid_by == "company_card":
        return INELIGIBLE, ("production company card purchases are never eligible for petty cash "
                            "(belongs in credit card reconciliation / PO Log)")

    if component.label == "cash tip":
        bill = receipt.payments[0] if receipt.payments else None
        if bill is not None and bill.paid_by == "company_card":
            if not (receipt.tip_eligible_confirmed and receipt.tip_documentation):
                return REVIEW, ("cash tip on a production-card bill: not included unless a person confirms it is eligible "
                                "and independently documented under the job's policy")
        if paid_by is None:
            return REVIEW, "who paid the cash tip must be identified"
        if paid_by == "crew_personal":
            return _float_reimbursement(receipt, "cash tip paid personally")
        return ELIGIBLE, "cash tip" + (" (confirmed eligible and documented)" if receipt.tip_eligible_confirmed else "")

    if method is None:
        return REVIEW, "payment method could not be determined - identify it before finalizing"

    if method == "Cash":
        if paid_by is None:
            return REVIEW, "who paid the cash must be identified"
        if paid_by == "crew_personal":
            return _float_reimbursement(receipt, "paid with the crew member's own cash")
        return ELIGIBLE, "cash from the float"

    # Non-cash (card) payment
    if paid_by is None:
        return REVIEW, "card owner unknown - never assumed to be a personal card; identify who paid"
    if rules.payment_policy == "cash_only":
        return INELIGIBLE, "this production allows cash only; card purchases (including personal cards) are not eligible"
    if not receipt.personal_card_approved:
        return REVIEW, "personal card expense: requires explicit approval under the job's policy"
    if rules.payment_policy == "case_by_case" and not receipt.authorization:
        return REVIEW, "case-by-case job: approval recorded but no authorization reference"
    approved = "personal card expense approved" + (f" (authorization: {receipt.authorization})" if receipt.authorization else "")
    return _float_reimbursement(receipt, approved)


def _float_reimbursement(receipt, what: str) -> tuple[str, str]:
    """A personally paid expense enters the envelope only if reimbursement from the float is confirmed AND documented."""
    if receipt.reimbursed_from_float and receipt.reimbursement_documentation:
        return ELIGIBLE, f"{what}; crew member reimbursed by retaining it from the float ({receipt.reimbursement_documentation})"
    if receipt.reimbursed_from_float:
        return SEPARATE, f"{what}; reimbursement from the float is confirmed but not documented - kept out of the envelope"
    return SEPARATE, (f"{what}; reimbursement from the float has not been confirmed - kept out of the envelope "
                      "and flagged for separate reimbursement")


def apply(receipt, rules: PettyCashRules) -> None:
    for c in receipt.payments:
        c.eligibility, c.reason = evaluate(c, receipt, rules)


def receipt_status(receipt) -> str:
    """eligible (some amount counts) / review_required / ineligible."""
    states = {c.eligibility for c in receipt.payments}
    if ELIGIBLE in states:
        return ELIGIBLE
    if REVIEW in states or not receipt.payments:
        return REVIEW
    if SEPARATE in states:
        return SEPARATE
    return INELIGIBLE


def check_completed_envelope(receipts, rules: PettyCashRules) -> list[dict]:
    """VERIFY mode policy check on a crew member's completed envelope.

    ``receipts`` are the receipts listed on the submitted top sheet, with payment details
    filled in. Nothing is modified: the function works on copies and only returns findings.
    """
    findings = []
    for r in receipts:
        work = copy.deepcopy(r)
        for c in work.payments:
            status, reason = evaluate(c, work, rules)
            if status == INELIGIBLE:
                findings.append({"severity": "ERROR", "receipt": r.number or r.source_name, "check": "Policy violation",
                                 "message": f"{c.label} ${c.amount} ({c.method}): {reason}."})
            elif status == SEPARATE:
                findings.append({"severity": "WARNING", "receipt": r.number or r.source_name, "check": "Reimbursement not confirmed",
                                 "message": f"{c.label} ${c.amount} ({c.method}): {reason}."})
            elif status == REVIEW:
                findings.append({"severity": "WARNING", "receipt": r.number or r.source_name, "check": "Needs review",
                                 "message": f"{c.label} ${c.amount} ({c.method or 'unknown method'}): {reason}."})
            else:
                findings.append({"severity": "PASS", "receipt": r.number or r.source_name, "check": "Policy",
                                 "message": f"{c.label} ${c.amount}: {reason}."})
    return findings
