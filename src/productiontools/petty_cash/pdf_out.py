"""Receipt file naming and combined-PDF assembly."""

from __future__ import annotations

import io
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from .models import Receipt


def receipt_filename(r: Receipt) -> str:
    vendor = r.vendor or "Unknown-Vendor"
    if vendor.isupper():
        vendor = vendor.title()
    vendor = re.sub(r"[^A-Za-z0-9]+", "-", vendor).strip("-")[:40] or "Unknown-Vendor"
    d = r.date.isoformat() if r.date else "no-date"
    amt = f"{r.total:.2f}" if r.total is not None else "no-total"
    return f"{r.number}_{d}_{vendor}_{amt}.pdf"


def placeholder_topsheet_pdf(xlsx_name: str) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(306, 560, "TOP SHEET PDF PENDING")
    c.setFont("Helvetica", 11)
    lines = [f"The filled top sheet is saved as {xlsx_name}.",
             "Automatic Excel export was not available, so please export it manually:",
             "1. Open the file in Microsoft Excel.",
             "2. File > Save As > File Format: PDF > choose 'Best for printing'.",
             "3. Add the PDF back to ProductionTools; it will rebuild this combined PDF."]
    for i, t in enumerate(lines):
        c.drawCentredString(306, 520 - i * 18, t)
    c.showPage()
    c.save()
    return buf.getvalue()


def combine(topsheet_pdf: bytes, topsheet_label: str, receipts: list[tuple[str, bytes]]) -> bytes:
    """Top sheet first, then each receipt in order, with a bookmark for each."""
    w = PdfWriter()
    start = len(w.pages)
    for p in PdfReader(io.BytesIO(topsheet_pdf)).pages:
        w.add_page(p)
    w.add_outline_item(topsheet_label, start)
    for label, data in receipts:
        start = len(w.pages)
        for p in PdfReader(io.BytesIO(data)).pages:
            w.add_page(p)
        w.add_outline_item(label, start)
    w.page_mode = "/UseOutlines"
    w.add_metadata({"/Producer": "ProductionTools", "/Title": topsheet_label})
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def write_pdf(path: Path, data: bytes) -> Path:
    from ..core.filestore import write_new_bytes
    return write_new_bytes(path, data)
