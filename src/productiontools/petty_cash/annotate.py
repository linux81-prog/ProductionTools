"""Draw bookkeeper-style annotations on COPIES of receipts.

On the receipt itself:
  * red circles around the vendor name, the date and the total,
  * the receipt number (e.g. PC001-001) in the emptiest corner of the receipt.
In a slim band added below the receipt: number, account code, description,
verification status.

Circles that are not yet verified by a person are dashed and tagged "?".
Fields whose location could not be found are listed as
"needs manual placement" so a person can position them.

PDF receipts keep their original page (text stays sharp and selectable);
annotations are a transparent vector layer merged onto a copy. Photos are
placed on a letter-size page with the marks drawn on top.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from .models import Box, Page, Receipt

RED = HexColor("#D0021B")
LETTER = (612.0, 792.0)
MARGIN = 36.0
FOOTER_H = 58.0
OUTPUT_DPI = 200
CIRCLED_FIELDS = (("vendor", "VENDOR"), ("date", "DATE"), ("total", "TOTAL"))


@dataclass
class Placement:
    """Maps page-image pixels to PDF points on the output page."""
    scale: float      # points per pixel
    x_off: float
    y_top: float      # PDF y coordinate of image pixel row 0

    def pt(self, x: float, y: float) -> tuple[float, float]:
        return self.x_off + x * self.scale, self.y_top - y * self.scale


# ------------------------------------------------------------- layout helpers --
def _ink_density(img: Image.Image, box: Box) -> float:
    g = np.asarray(img.convert("L").crop((int(box.x0), int(box.y0), int(box.x1), int(box.y1))))
    return float((g < 140).mean()) if g.size else 1.0


def text_region(page: Page) -> Box:
    w, h = page.image.size
    if not page.tokens:
        return Box(0, 0, w, h)
    b = page.tokens[0].box
    for t in page.tokens[1:]:
        b = b.union(t.box)
    pad = 0.05 * max(b.w, b.h * 0.4)
    return Box(max(0, b.x0 - pad), max(0, b.y0 - pad), min(w, b.x1 + pad), min(h, b.y1 + pad))


def _overlap_cost(page: Page, b: Box, blockers: list[Box]) -> float:
    overlap = sum(max(0, min(b.x1, o.x1) - max(b.x0, o.x0)) * max(0, min(b.y1, o.y1) - max(b.y0, o.y0))
                  for o in blockers)
    return overlap / max(b.w * b.h, 1) * 10 + _ink_density(page.image, b)


def choose_number_box(page: Page, label_w_px: float, label_h_px: float, avoid: list[Box]) -> Box:
    """Find the emptiest spot on the receipt (inside its text area) for the receipt number.

    Every position on a grid is scored by how much it would cover words, circles or
    ink; corners are preferred when several spots are equally empty.
    """
    t = text_region(page)
    lw, lh = min(label_w_px, t.w * 0.9), min(label_h_px, t.h * 0.5)
    # allow the label to sit in the paper margin just above/below the printed text
    W, H = page.image.size
    r = Box(t.x0, max(0, t.y0 - 0.5 * lh), t.x1, min(H, t.y1 + 0.5 * lh))
    blockers = [Box(t.box.x0 - 3, t.box.y0 - 3, t.box.x1 + 3, t.box.y1 + 3) for t in page.tokens] + avoid
    best, best_cost = None, float("inf")
    nx, ny = 10, 24
    for iy in range(ny + 1):
        for ix in range(nx + 1):
            x0 = r.x0 + (r.w - lw) * ix / nx
            y0 = r.y0 + (r.h - lh) * iy / ny
            b = Box(x0, y0, x0 + lw, y0 + lh)
            edge = min(ix, nx - ix) / nx + min(iy, ny - iy) / ny     # 0 at a corner
            top_pref = 0.02 * (iy / ny)                               # slight preference for the top
            cost = _overlap_cost(page, b, blockers) + 0.4 * edge + top_pref
            if cost < best_cost:
                best, best_cost = b, cost
    return best


def _tag_position(page: Page, ell: Box, tag_w_px: float, tag_h_px: float, others: list[Box]) -> tuple[float, float]:
    """Place a small field label (VENDOR/DATE/TOTAL) beside its circle where it covers nothing."""
    w, h = page.image.size
    gap = 3
    cy = (ell.y0 + ell.y1) / 2
    options = [Box(ell.x0 - gap - tag_w_px, cy - tag_h_px / 2, ell.x0 - gap, cy + tag_h_px / 2),   # left
               Box(ell.x1 + gap, cy - tag_h_px / 2, ell.x1 + gap + tag_w_px, cy + tag_h_px / 2),   # right
               Box(ell.x0, ell.y0 - gap - tag_h_px, ell.x0 + tag_w_px, ell.y0 - gap),              # above
               Box(ell.x0, ell.y1 + gap, ell.x0 + tag_w_px, ell.y1 + gap + tag_h_px)]              # below
    blockers = [t.box for t in page.tokens] + others

    def cost(b: Box) -> float:
        outside = (b.x0 < 0) or (b.y0 < 0) or (b.x1 > w) or (b.y1 > h)
        return (100 if outside else 0) + _overlap_cost(page, b, blockers)

    b = min(options, key=cost)
    return b.x0, b.y1


def _ellipse_for(box: Box, pad_px: float) -> tuple[float, float, float, float]:
    """Ellipse (center x, center y, rx, ry) hugging the words like a pen circle."""
    cx, cy = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
    rx = box.w / 2 * 1.16 + pad_px
    ry = box.h / 2 * 1.45 + pad_px * 0.25
    return cx, cy, rx, ry


def _draw_marks(c: canvas.Canvas, page: Page, receipt: Receipt, pl: Placement, draft: bool) -> list[str]:
    """Draw circles + number for one page. Returns labels of fields needing placement."""
    circles: list[Box] = []
    to_draw = []
    for key, label in CIRCLED_FIELDS:
        f = receipt.fields.get(key)
        if not f or f.box is None or f.page != page.index:
            continue
        cx, cy, rx, ry = _ellipse_for(f.box, pad_px=max(3.0, f.box.h * 0.2))
        circles.append(Box(cx - rx, cy - ry, cx + rx, cy + ry))
        to_draw.append((f, label, cx, cy, rx, ry))
    c.saveState()
    tags: list[Box] = []
    for f, label, cx, cy, rx, ry in to_draw:
        X, Y = pl.pt(cx, cy)
        RX, RY = rx * pl.scale, ry * pl.scale
        c.setStrokeColor(RED)
        c.setLineWidth(1.8)
        c.setDash(4, 3) if not f.verified else c.setDash()
        c.ellipse(X - RX, Y - RY, X + RX, Y + RY, stroke=1, fill=0)
        tag = label + (" ?" if not f.verified else "")
        tw_pt = stringWidth(tag, "Helvetica-Bold", 6.5)
        tx, ty = _tag_position(page, Box(cx - rx, cy - ry, cx + rx, cy + ry), tw_pt / pl.scale, 7.5 / pl.scale,
                               circles + tags)
        tags.append(Box(tx, ty - 7.5 / pl.scale, tx + tw_pt / pl.scale, ty))
        TX, TY = pl.pt(tx, ty)
        c.setFillColor(RED)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawString(TX, TY + 1.2, tag)
    c.setDash()
    circles += tags

    if page.index == 0 and receipt.number:
        text = receipt.number
        region_w_pt = text_region(page).w * pl.scale
        size_pt = max(9.0, min(16.0, 0.32 * region_w_pt / max(stringWidth(text, "Helvetica-Bold", 1), 1)))
        w_pt = stringWidth(text, "Helvetica-Bold", size_pt) + 12
        h_pt = size_pt + 9
        if receipt.number_position:
            nb = Box.from_norm(receipt.number_position, *page.image.size)
        else:
            nb = choose_number_box(page, w_pt / pl.scale, h_pt / pl.scale, circles)
        x0, y1 = pl.pt(nb.x0, nb.y0)
        x1, y0 = pl.pt(nb.x1, nb.y1)
        c.setFillColor(Color(1, 1, 1, alpha=0.85))
        c.setStrokeColor(RED)
        c.setLineWidth(1.6)
        c.roundRect(x0, y0, x1 - x0, y1 - y0, 4, stroke=1, fill=1)
        c.setFillColor(RED)
        fs = min(size_pt, (x1 - x0 - 8) / max(stringWidth(text, "Helvetica-Bold", 1), 1))
        c.setFont("Helvetica-Bold", fs)
        c.drawCentredString((x0 + x1) / 2, (y0 + y1) / 2 - fs * 0.35, text)
    c.restoreState()

    missing = []
    if page.index == len(receipt.pages) - 1:
        for key, label in CIRCLED_FIELDS:
            f = receipt.fields.get(key)
            if not f or f.box is None:
                missing.append(label)
    return missing


def _draw_footer(c: canvas.Canvas, receipt: Receipt, x: float, y_bottom: float, width: float,
                 missing: list[str], draft: bool, account_lookup: dict[str, str]) -> None:
    c.saveState()
    c.setStrokeColor(RED)
    c.setLineWidth(0.6)
    c.line(x, y_bottom + FOOTER_H - 6, x + width, y_bottom + FOOTER_H - 6)
    c.setFillColor(RED)
    c.setFont("Helvetica-Bold", 9.5)
    total = receipt.total
    acct = receipt.account_code or "—"
    acct_desc = account_lookup.get(receipt.account_code or "", "")
    line1 = f"{receipt.number or 'UNNUMBERED'}   |   Acct {acct}{(' ' + acct_desc) if acct_desc else ''}   |   ${total if total is not None else '—'}"
    c.drawString(x, y_bottom + FOOTER_H - 20, line1)
    c.setFont("Helvetica", 8.5)
    c.drawString(x, y_bottom + FOOTER_H - 32, (receipt.description or "(no description entered)")[:110])
    c.setFont("Helvetica-Oblique", 7.5)
    if draft:
        status = "UNVERIFIED DRAFT — dashed circles were placed automatically and need a person to confirm."
    elif receipt.verified_by:
        status = f"Verified by {receipt.verified_by}."
    else:
        status = "Not yet verified."
    if missing:
        status += "  Needs manual placement: " + ", ".join(missing) + "."
    c.drawString(x, y_bottom + FOOTER_H - 44, status[:150])
    c.restoreState()


def _watermark(c: canvas.Canvas, w: float, h: float, text: str) -> None:
    c.saveState()
    c.setFillColor(Color(0.82, 0.0, 0.1, alpha=0.10))
    c.setFont("Helvetica-Bold", 54)
    c.translate(w / 2, h / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, text)
    c.restoreState()


def _jpeg(img: Image.Image, target_px_w: int) -> ImageReader:
    if img.width > target_px_w:
        img = img.resize((target_px_w, int(img.height * target_px_w / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=85, optimize=True)
    buf.seek(0)
    return ImageReader(buf)


# --------------------------------------------------------------- renderers --
def render_receipt_pdf(receipt: Receipt, annotated: bool, draft: bool = False,
                       account_lookup: dict[str, str] | None = None) -> bytes:
    """Return a PDF (bytes) with every page of the receipt, annotated or clean."""
    account_lookup = account_lookup or {}
    writer = PdfWriter()
    original_reader = None
    for page in receipt.pages:
        if page.source_kind in ("pdf-text", "pdf-scan") and page.pdf_scale and page.pdf_page_size:
            if original_reader is None:
                original_reader = PdfReader(str(receipt.original_path))
            src_page = original_reader.pages[page.index]
            writer.add_page(src_page)
            out_page = writer.pages[-1]
            if annotated:
                w, h = page.pdf_page_size
                left, bottom = float(out_page.mediabox.left), float(out_page.mediabox.bottom)
                buf = io.BytesIO()
                c = canvas.Canvas(buf, pagesize=(w, h + FOOTER_H))
                c.translate(0, FOOTER_H)
                pl = Placement(1 / page.pdf_scale, 0, h)
                missing = _draw_marks(c, page, receipt, pl, draft)
                if page.index == len(receipt.pages) - 1 or page.index == 0:
                    _draw_footer(c, receipt, MARGIN, -FOOTER_H + 4, w - 2 * MARGIN, missing, draft, account_lookup)
                if draft:
                    _watermark(c, w, h, "DRAFT - NOT VERIFIED")
                c.showPage()
                c.save()
                overlay = PdfReader(io.BytesIO(buf.getvalue())).pages[0]
                # The overlay page is FOOTER_H taller; shift it so its origin is the band's bottom.
                from pypdf import Transformation
                out_page.merge_transformed_page(overlay, Transformation().translate(left, bottom - FOOTER_H))
                out_page.mediabox.lower_left = (left, bottom - FOOTER_H)
                out_page.cropbox.lower_left = (left, bottom - FOOTER_H)
        else:
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=LETTER, invariant=1)
            area_w = LETTER[0] - 2 * MARGIN
            area_h = LETTER[1] - 2 * MARGIN - FOOTER_H
            img = page.image
            s = min(area_w / img.width, area_h / img.height)
            draw_w, draw_h = img.width * s, img.height * s
            x0 = (LETTER[0] - draw_w) / 2
            y_top = LETTER[1] - MARGIN
            c.drawImage(_jpeg(img, int(draw_w / 72 * OUTPUT_DPI)), x0, y_top - draw_h, draw_w, draw_h)
            if annotated:
                pl = Placement(s, x0, y_top)
                missing = _draw_marks(c, page, receipt, pl, draft)
                _draw_footer(c, receipt, MARGIN, MARGIN - 6, area_w, missing, draft, account_lookup)
                if draft:
                    _watermark(c, *LETTER, "DRAFT - NOT VERIFIED")
            c.showPage()
            c.save()
            writer.add_page(PdfReader(io.BytesIO(buf.getvalue())).pages[0])
    out = io.BytesIO()
    writer.add_metadata({"/Producer": "ProductionTools", "/Title": f"Receipt {receipt.number or receipt.source_name}"})
    writer.write(out)
    return out.getvalue()
