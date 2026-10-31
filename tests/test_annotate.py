"""Annotation rendering: circles on the receipt, manual placement, clean vs annotated."""

import io
from datetime import date
from decimal import Decimal

from PIL import Image, ImageDraw
from pypdf import PdfReader

from productiontools.core.audit import AuditLog
from productiontools.petty_cash.annotate import render_receipt_pdf
from productiontools.petty_cash.models import Box, FieldValue, Page, Receipt, Token
from productiontools.petty_cash.review import apply_review


def _receipt():
    img = Image.new("RGB", (600, 900), "white")
    ImageDraw.Draw(img).text((50, 50), "TEST VENDOR", fill="black")
    toks = [Token("TEST", 0.99, Box(50, 50, 120, 70), 0), Token("VENDOR", 0.99, Box(130, 50, 230, 70), 0),
            Token("TOTAL", 0.99, Box(50, 800, 130, 820), 0), Token("9.99", 0.99, Box(450, 800, 520, 820), 0)]
    r = Receipt("fake.jpg", None, "0" * 64, [Page(0, img, toks, "photo")])
    r.fields = {"vendor": FieldValue("vendor", "Test Vendor", 0.9, 0, Box(50, 50, 230, 70)),
                "date": FieldValue("date", None, 0.0, note="not found"),
                "total": FieldValue("total", Decimal("9.99"), 0.95, 0, Box(450, 800, 520, 820))}
    r.number = "PC001-001"
    return r


def _text(pdf: bytes) -> str:
    return "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def test_missing_location_is_reported_for_manual_placement():
    txt = _text(render_receipt_pdf(_receipt(), annotated=True, draft=True))
    assert "Needs manual placement: DATE" in txt
    assert "PC001-001" in txt and "VENDOR ?" in txt  # unverified circles are tagged "?"


def test_manual_position_from_reviewer_is_used(tmp_path):
    r = _receipt()
    review = {"reviewer": "Tester", "receipts": {"fake.jpg": {
        "corrections": {"date": {"value": "2026-10-14", "reason": "read from image"}},
        "positions": {"date": {"page": 0, "box": [0.1, 0.2, 0.4, 0.24], "reason": "placed by hand"}},
        "confirm": True}}}
    apply_review([r], review, AuditLog(tmp_path / "audit.log"))
    assert r.fields["date"].value == date(2026, 10, 14) and r.fields["date"].verified
    assert r.fields["date"].box.x0 == 60 and r.fields["date"].box.y0 == 180
    txt = _text(render_receipt_pdf(r, annotated=True))
    assert "Needs manual placement" not in txt and "DATE" in txt and "Verified by Tester" in txt
    assert {o["kind"] for o in r.overrides} == {"value correction", "annotation position"}
    assert "annotation_positioned" in (tmp_path / "audit.log").read_text()


def test_clean_version_has_no_marks():
    txt = _text(render_receipt_pdf(_receipt(), annotated=False))
    assert "PC001-001" not in txt and "VENDOR" not in txt
