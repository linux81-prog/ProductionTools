"""OCR / extraction accuracy against answer keys (fictional receipts only)."""

from conftest import FIX
from productiontools.petty_cash.accuracy import evaluate


def test_demo_receipts_extract_correctly():
    r = evaluate(FIX / "receipts", FIX / "answer_keys.json")
    assert r["accuracy"] == 1.0, r["per_field"]


def test_stress_set_accuracy_and_no_silent_errors():
    r = evaluate(FIX / "stress", FIX / "stress" / "answer_keys.json")
    assert r["accuracy"] >= 0.85, r["per_field"]
    # The critical safety property: every wrong or missing value must be flagged for a person.
    assert r["wrong_and_NOT_flagged"] == 0
    for row in r["rows"]:
        for f, v in row["fields"].items():
            if v["status"] != "correct":
                assert v["flagged_for_review"], (row["file"], f, v)
