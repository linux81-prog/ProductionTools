"""Annotation output: only circles + a small receipt number; nothing else added."""

import io
from datetime import date
from decimal import Decimal

from PIL import Image, ImageDraw
from pypdf import PdfReader

from conftest import FIX
from productiontools.core.audit import AuditLog
from productiontools.petty_cash.annotate import already_circled, ellipse_for, render_receipt_pdf
from productiontools.petty_cash.extract import load_pages
from productiontools.petty_cash.models import Box, FieldValue, Page, Receipt, Token
from productiontools.petty_cash.parse import parse_receipt
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
    r.number, r.seq, r.label = "PC001-001", 1, "#1"
    r.account_code, r.description, r.verified_by = "2410", "Gaffer tape for set", "Someone"
    return r


def _text(pdf: bytes) -> str:
    return "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def test_only_number_is_added_no_labels_footer_or_signatures():
    r = _receipt()
    txt = _text(render_receipt_pdf(r, annotated=True))
    assert "#1" in txt
    for unwanted in ("VENDOR", "DATE", "TOTAL", "2410", "Gaffer", "Verified", "Someone", "DRAFT", "PC001-001"):
        assert unwanted not in txt.replace("TEST VENDOR", ""), unwanted
    assert r.annotation_notes["date"].startswith("location not found")


def test_page_size_is_unchanged_for_pdf_receipts(tmp_path):
    src = FIX / "receipts" / "03_prop_depot_invoice.pdf"
    pages = load_pages(src)
    r = Receipt(src.name, src, "x", pages, parse_receipt(pages))
    r.number, r.seq, r.label = "PC001-003", 3, "#3"
    out = PdfReader(io.BytesIO(render_receipt_pdf(r, annotated=True))).pages[0]
    orig = PdfReader(str(src)).pages[0]
    assert (float(out.mediabox.width), float(out.mediabox.height)) == (float(orig.mediabox.width), float(orig.mediabox.height))
    assert r.annotation_notes == {}  # blue printed vendor name is not mistaken for an existing pen circle


def test_existing_pen_circle_is_not_duplicated():
    src = FIX / "receipts" / "01_hardware_barn_photo.jpg"
    pages = load_pages(src)
    fields = parse_receipt(pages)
    page = pages[0]
    tb = fields["total"].box
    e = ellipse_for(tb)
    ImageDraw.Draw(page.image).ellipse((e.x0, e.y0, e.x1, e.y1), outline=(200, 20, 30), width=4)  # crew member's pen
    assert already_circled(page, tb)
    assert not already_circled(page, fields["vendor"].box)
    r = Receipt(src.name, src, "x", pages, fields)
    r.number, r.seq, r.label = "PC001-001", 1, "#1"
    render_receipt_pdf(r, annotated=True)
    assert "already circled" in r.annotation_notes.get("total", "")
    assert "vendor" not in r.annotation_notes


def test_existing_number_is_not_duplicated():
    r = _receipt()
    r.pages[0].tokens.append(Token("#1", 0.99, Box(500, 20, 540, 40), 0))
    render_receipt_pdf(r, annotated=True)
    assert "already shown" in r.annotation_notes["number"]


def test_manual_position_from_reviewer_is_used(tmp_path):
    r = _receipt()
    review = {"reviewer": "Tester", "receipts": {"fake.jpg": {
        "corrections": {"date": {"value": "2026-10-14", "reason": "read from image"}},
        "positions": {"date": {"page": 0, "box": [0.1, 0.2, 0.4, 0.24], "reason": "placed by hand"}},
        "confirm": True}}}
    apply_review([r], review, AuditLog(tmp_path / "audit.log"))
    assert r.fields["date"].value == date(2026, 10, 14) and r.fields["date"].verified
    assert r.fields["date"].box.x0 == 60 and r.fields["date"].box.y0 == 180
    render_receipt_pdf(r, annotated=True)
    assert "date" not in r.annotation_notes
    assert {o["kind"] for o in r.overrides} == {"value correction", "annotation position"}
    assert "annotation_positioned" in (tmp_path / "audit.log").read_text()


def test_clean_version_has_no_marks():
    assert "#1" not in _text(render_receipt_pdf(_receipt(), annotated=False))
