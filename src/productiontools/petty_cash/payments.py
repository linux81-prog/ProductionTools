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

Rules:
  * A company-card component is never counted toward the envelope or reimbursement.
  * Unknown classifications are never guessed. They block finalizing until a person
    decides.
  * A tip is counted exactly once: card tips are inside the card charge; a cash tip on
    a card bill is its own component.
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

    @property
    def reimbursable(self) -> bool:
        return self.paid_by in REIMBURSABLE


def _last4(s: str | None) -> str | None:
    m = re.search(r"(\d{4})\s*$", s or "")
    return m.group(1) if m else None


def classify(receipt, company_cards: list[str] = ()) -> list[Component]:
    """Build payment components for a receipt. Reviewer decisions always win."""
    total = receipt.total
    if total is None:
        return []
    method = receipt.val("payment")
    pay_id = receipt.val("payment_id")
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
        return [Component("bill", bill_amount, method, pb, src), Component("cash tip", tip, "Cash", tpb, tsrc)]
    pb, src = who(receipt.paid_by, method)
    return [Component("bill", total, method, pb, src)]


def envelope_amount(receipt) -> Decimal:
    """Amount this receipt contributes to the petty cash envelope: everything except company-card spending.

    Unknown components are included here, but they are flagged as ERROR so the
    envelope cannot be finalized until a person classifies them.
    """
    return sum((c.amount for c in receipt.payments if c.paid_by != "company_card"), ZERO)


def describe(c: Component) -> str:
    return f"{c.label} ${c.amount} by {c.method or 'unknown method'}, paid by {LABELS[c.paid_by]} ({c.source})"
