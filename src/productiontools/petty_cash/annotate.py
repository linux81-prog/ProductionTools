"""Mark COPIES of receipts the way a bookkeeper would, and nothing more.

Default output (as agreed with the user):
  * a red circle around the vendor name, the transaction date and the final total,
  * a small, unobtrusive receipt number in an empty spot on the receipt,
  * NO labels, NO footer, NO account codes, descriptions or signatures, and no
    added margin. The page stays as close to the original as possible.

If a field already appears to be circled (for example by the crew member, in
coloured pen), it is not circled again. If the receipt already shows its number,
the number is not added again.

Review previews (``draft=True``) show circles the machine placed but no person
has confirmed yet as dashed lines. They are a review aid, not a deliverable.

PDF receipts keep their original page; the marks are a transparent vector layer
merged onto a copy. Photos are placed on a letter-size page with marks on top.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import numpy as np
from PIL import Image
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from .models import Box, Page, Receipt

RED = HexColor("#D0021B")
LETTER = (612.0, 792.0)
MARGIN = 36.0
OUTPUT_DPI = 200
NUMBER_FONT = "Helvetica-Bold"
NUMBER_SIZE_PT = 10.0
CIRCLED_FIELDS = ("vendor", "date", "total")


@dataclass
class Placement:
    """Maps page-image pixels to PDF points on the output page."""
    scale: float      # points per pixel
    x_off: float
    y_top: float      # PDF y coordinate of image pixel row 0

    def pt(self, x: float, y: float) -> tuple[float, float]:
        return self.x_off + x * self.scale, self.y_top - y * self.scale


@dataclass
class MarkPlan:
    circles: list[tuple[str, Box, bool]]   # (field, box, verified)
    number_box: Box | None
    skipped: dict[str, str]                # field -> reason (already marked / not found)


# --------------------------------------------------------------- helpers --
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
    """Find the emptiest spot on the receipt (in or just around its printed text) for the number."""
    t = text_region(page)
    lw, lh = min(label_w_px, t.w * 0.9), min(label_h_px, t.h * 0.5)
    W, H = page.image.size
    r = Box(t.x0, max(0, t.y0 - 0.5 * lh), t.x1, min(H, t.y1 + 0.5 * lh))
    blockers = [Box(tk.box.x0 - 3, tk.box.y0 - 3, tk.box.x1 + 3, tk.box.y1 + 3) for tk in page.tokens] + avoid
    best, best_cost = None, float("inf")
    nx, ny = 10, 24
    for iy in range(ny + 1):
        for ix in range(nx + 1):
            x0 = r.x0 + (r.w - lw) * ix / nx
            y0 = r.y0 + (r.h - lh) * iy / ny
            b = Box(x0, y0, x0 + lw, y0 + lh)
            edge = min(ix, nx - ix) / nx + min(iy, ny - iy) / ny     # 0 at a corner
            cost = _overlap_cost(page, b, blockers) + 0.4 * edge + 0.02 * (iy / ny)
            if cost < best_cost:
                best, best_cost = b, cost
    return best


def ellipse_for(box: Box) -> Box:
    """Bounding box of an ellipse hugging the words like a pen circle."""
    pad = max(3.0, box.h * 0.2)
    cx, cy = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
    rx = box.w / 2 * 1.16 + pad
    ry = box.h / 2 * 1.45 + pad * 0.25
    return Box(cx - rx, cy - ry, cx + rx, cy + ry)


def already_circled(page: Page, box: Box) -> bool:
    """True if coloured pen strokes appear to surround this field already.

    Looks for saturated ink (red, blue, green pen) in four bands just outside
    the words: above, below, left and right. A hand-drawn circle crosses all
    four; coloured printing beside a word normally does not.
    """
    rgb = np.asarray(page.image.convert("RGB")).astype("float32") / 255.0
    H, W = rgb.shape[:2]
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    pen = (sat > 0.45) & (mx > 0.25)
    gx, gy = max(4, box.h * 0.9), max(4, box.h * 0.9)
    x0, y0, x1, y1 = box.x0, box.y0, box.x1, box.y1
    bands = [(x0, y0 - gy, x1, y0), (x0, y1, x1, y1 + gy), (x0 - gx, y0, x0, y1), (x1, y0, x1 + gx, y1)]
    hits = 0
    for bx0, by0, bx1, by1 in bands:
        a = pen[max(0, int(by0)):min(H, int(by1)), max(0, int(bx0)):min(W, int(bx1))]
        if a.size and a.mean() > 0.01:
            hits += 1
    return hits >= 4


def number_already_present(page: Page, label: str) -> bool:
    key = re.sub(r"\W", "", label).lower()
    return bool(key) and any(re.sub(r"\W", "", t.text).lower() == key for t in page.tokens)


def plan_marks(page: Page, receipt: Receipt, pl_scale: float) -> MarkPlan:
    circles, skipped = [], {}
    for key in CIRCLED_FIELDS:
        f = receipt.fields.get(key)
        if not f or f.box is None or f.page != page.index:
            if page.index == len(receipt.pages) - 1 and (not f or f.box is None):
                skipped[key] = "location not found - needs manual placement"
            continue
        if already_circled(page, f.box):
            skipped[key] = "already circled on the receipt - not marked again"
            continue
        circles.append((key, f.box, f.verified))
    number_box = None
    label = receipt.label or receipt.number
    if page.index == 0 and label:
        if number_already_present(page, label):
            skipped["number"] = "number already shown on the receipt - not added again"
        elif receipt.number_position:
            number_box = Box.from_norm(receipt.number_position, *page.image.size)
        else:
            w_px = (stringWidth(label, NUMBER_FONT, NUMBER_SIZE_PT) + 4) / pl_scale
            h_px = (NUMBER_SIZE_PT + 3) / pl_scale
            number_box = choose_number_box(page, w_px, h_px, [ellipse_for(b) for _, b, _ in circles])
    return MarkPlan(circles, number_box, skipped)


def _draw(c: canvas.Canvas, page: Page, receipt: Receipt, pl: Placement, draft: bool) -> dict[str, str]:
    plan = plan_marks(page, receipt, pl.scale)
    c.saveState()
    c.setStrokeColor(RED)
    c.setLineWidth(1.6)
    for _, box, verified in plan.circles:
        e = ellipse_for(box)
        (X0, Y1), (X1, Y0) = pl.pt(e.x0, e.y0), pl.pt(e.x1, e.y1)
        if draft and not verified:
            c.setDash(4, 3)
        else:
            c.setDash()
        c.ellipse(X0, Y0, X1, Y1, stroke=1, fill=0)
    c.setDash()
    if plan.number_box is not None:
        label = receipt.label or receipt.number
        b = plan.number_box
        X0, Y1 = pl.pt(b.x0, b.y0)
        X1, Y0 = pl.pt(b.x1, b.y1)
        size = min(NUMBER_SIZE_PT, (X1 - X0 - 2) / max(stringWidth(label, NUMBER_FONT, 1), 1e-6))
        c.setFillColor(RED)
        c.setFont(NUMBER_FONT, size)
        c.drawString(X0 + 2, (Y0 + Y1) / 2 - size * 0.35, label)
    c.restoreState()
    return plan.skipped


def _jpeg(img: Image.Image, target_px_w: int) -> ImageReader:
    if img.width > target_px_w:
        img = img.resize((target_px_w, int(img.height * target_px_w / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=85, optimize=True)
    buf.seek(0)
    return ImageReader(buf)


# ---------------------------------------------------------------- render --
def render_receipt_pdf(receipt: Receipt, annotated: bool, draft: bool = False, **_ignored) -> bytes:
    """Return a PDF (bytes) with every page of the receipt, annotated or clean.

    Annotation notes (e.g. "already circled") are stored on ``receipt.annotation_notes``.
    """
    writer = PdfWriter()
    original_reader = None
    notes: dict[str, str] = {}
    for page in receipt.pages:
        if page.source_kind in ("pdf-text", "pdf-scan") and page.pdf_scale and page.pdf_page_size:
            if original_reader is None:
                original_reader = PdfReader(str(receipt.original_path))
            writer.add_page(original_reader.pages[page.index])
            out_page = writer.pages[-1]
            if annotated:
                w, h = page.pdf_page_size
                buf = io.BytesIO()
                c = canvas.Canvas(buf, pagesize=(w, h))
                notes.update(_draw(c, page, receipt, Placement(1 / page.pdf_scale, 0, h), draft))
                c.showPage()
                c.save()
                overlay = PdfReader(io.BytesIO(buf.getvalue())).pages[0]
                left, bottom = float(out_page.mediabox.left), float(out_page.mediabox.bottom)
                out_page.merge_transformed_page(overlay, Transformation().translate(left, bottom))
        else:
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=LETTER, invariant=1)
            area_w, area_h = LETTER[0] - 2 * MARGIN, LETTER[1] - 2 * MARGIN
            img = page.image
            s = min(area_w / img.width, area_h / img.height)
            draw_w, draw_h = img.width * s, img.height * s
            x0 = (LETTER[0] - draw_w) / 2
            y_top = LETTER[1] - MARGIN
            c.drawImage(_jpeg(img, int(draw_w / 72 * OUTPUT_DPI)), x0, y_top - draw_h, draw_w, draw_h)
            if annotated:
                notes.update(_draw(c, page, receipt, Placement(s, x0, y_top), draft))
            c.showPage()
            c.save()
            writer.add_page(PdfReader(io.BytesIO(buf.getvalue())).pages[0])
    if annotated:
        receipt.annotation_notes = notes
    out = io.BytesIO()
    writer.add_metadata({"/Producer": "ProductionTools"})
    writer.write(out)
    return out.getvalue()
