"""Who paid, how, and what is eligible for petty cash reimbursement.

Each receipt is split into one or more payment *components*. Usually there is one,
but a card bill plus a cash tip is two. Each component records:
  * the amount,
  * the payment method (Cash, Visa ...),
  * who paid:
      petty_cash_float  - cash from the crew member's petty cash float
      crew_personal     - the crew member's own money or own card (reimbursable)
      company_card      - a production company card (NEVER reimbursed to crew)
      None              - unknown: a person must classify it.

Eligibility is decided by the production's rules (policy.py), not here.
Money is tracked in separate buckets so eligibility never gets confused with cash:
  * eligible amount       - counted in the envelope / top sheet
  * float disbursement    - eligible AND actually paid from the petty cash float
                            (cash from the float, or a personal expense explicitly
                            recorded as reimbursed from the float)
  * personal owed         - eligible, paid personally, NOT yet reimbursed from the float
  * company card          - never counted
Unknown classifications are never guessed. A tip is counted exactly once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

PAID_BY = ("petty_cash_float", "crew_personal", "company_card")
REIMBURSABLE = ("petty_cash_float", "crew_personal")
ZERO = Decimal("0.00")
LABELS = {"petty_cash_float": "petty cash float", "crew_personal": "crew member personally",
          "company_card": "production company card", None: "UNKNOWN"}


@dataclass
class Component:
    label: str              # "bill", "cash tip"
    amount: Decimal
    method: str | None
    paid_by: str | None
    source: str             # how paid_by was decided: reviewer / production card list / inferred / unknown
    eligibility: str = "review_required"   # set by policy.apply()
    reason: str = ""

    @property
    def reimbursable(self) -> bool:
        return self.paid_by in REIMBURSABLE


def _last4(s: str | None) -> str | None:
    m = re.search(r"(\d{4})\s*$", s or "")
    return m.group(1) if m else None


def classify(receipt, company_cards: list[str] = (), rules=None) -> list[Component]:
    """Build payment components for a receipt. Reviewer decisions always win."""
    total = receipt.total
    if total is None:
        return []
    method = receipt.val("payment")
    pay_id = receipt.val("payment_id")
    if rules is not None:
        company_cards = list(company_cards) + list(rules.production_cards)
    company_last4 = {_last4(c) for c in company_cards if _last4(c)}

    def who(reviewer_value, method_):
        if reviewer_value:
            return reviewer_value, "reviewer"
        if method_ and method_ != "Cash" and _last4(pay_id) in company_last4:
            return "company_card", "matched the job's production card list"
        if method_ == "Cash":
            return "petty_cash_float", "inferred from CASH payment - confirm"
        return None, "unknown - who paid must be confirmed"

    tip, tip_method = receipt.val("tip"), receipt.val("tip_method")
    status = getattr(receipt.fields.get("total"), "tip_status", "")
    if tip is not None and tip_method == "cash" and method and method != "Cash" and status in ("verified", "proposed", "mismatch"):
        bill_amount = total - tip
        pb, src = who(receipt.paid_by, method)
        # Whose cash paid the tip (float or the crew member's own) is never assumed.
        tpb, tsrc = (receipt.tip_paid_by, "reviewer") if receipt.tip_paid_by else (None, "unknown - who paid the cash tip must be confirmed")
        comps = [Component("bill", bill_amount, method, pb, src), Component("cash tip", tip, "Cash", tpb, tsrc)]
        return _with_policy(receipt, comps, rules)
    pb, src = who(receipt.paid_by, method)
    comps = [Component("bill", total, method, pb, src)]
    return _with_policy(receipt, comps, rules)


def _with_policy(receipt, comps, rules):
    from .policy import PettyCashRules, evaluate
    rules = rules or PettyCashRules()
    receipt.payments = comps
    for c in comps:
        c.eligibility, c.reason = evaluate(c, receipt, rules)
    return comps


def envelope_amount(receipt) -> Decimal:
    """Eligible amount: what this receipt contributes to the envelope / top sheet."""
    return sum((c.amount for c in receipt.payments if c.eligibility == "eligible"), ZERO)


def float_disbursement(receipt) -> Decimal:
    """Eligible money that actually left the petty cash float."""
    total = ZERO
    for c in receipt.payments:
        if c.eligibility != "eligible":
            continue
        if c.paid_by == "petty_cash_float" or (c.paid_by == "crew_personal" and receipt.reimbursed_from_float):
            total += c.amount
    return total


def personal_owed(receipt) -> Decimal:
    """Eligible personally paid money not (yet) reimbursed from the float."""
    if receipt.reimbursed_from_float:
        return ZERO
    return sum((c.amount for c in receipt.payments if c.eligibility == "eligible" and c.paid_by == "crew_personal"), ZERO)


def describe(c: Component) -> str:
    return f"{c.label} ${c.amount} by {c.method or 'unknown method'}, paid by {LABELS[c.paid_by]} ({c.source})"


def bucket_totals(receipts, excluded=()) -> dict:
    out = {"eligible_total": ZERO, "float_disbursements": ZERO, "personal_owed": ZERO, "held_for_review": ZERO,
           "ineligible_company_card": ZERO, "ineligible_policy": ZERO}
    for r in list(receipts) + list(excluded):
        out["eligible_total"] += envelope_amount(r)
        out["float_disbursements"] += float_disbursement(r)
        out["personal_owed"] += personal_owed(r)
        for c in r.payments:
            if c.eligibility == "review_required":
                out["held_for_review"] += c.amount
            elif c.eligibility == "ineligible":
                key = "ineligible_company_card" if c.paid_by == "company_card" else "ineligible_policy"
                out[key] += c.amount
    return out
