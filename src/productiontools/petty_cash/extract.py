"""Turn an imported receipt file into pages of positioned words.

* Phone photos (JPG/PNG/HEIC): fix rotation, find the paper, straighten and
  crop it, then read the text with the offline RapidOCR engine.
* PDFs with a real text layer (e.g. emailed invoices): read the text and its
  exact positions directly. This is more accurate than OCR.
* Scanned PDFs (pictures of paper): render each page to an image and OCR it.

All work happens on in-memory copies; the original file is only read.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .models import Box, Page, Token

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".webp"}
RENDER_DPI = 200
MIN_TEXT_CHARS = 20


# ------------------------------------------------------------------- OCR --
@lru_cache(maxsize=1)
def _engine():
    from rapidocr import RapidOCR  # models ship inside the package; no download
    return RapidOCR(params={"Global.log_level": "error"})


def ocr_tokens(img: Image.Image, page_index: int) -> list[Token]:
    arr = np.asarray(img.convert("RGB"))
    result = _engine()(arr, return_word_box=True)
    tokens: list[Token] = []
    words = getattr(result, "word_results", None) or ()
    for line in words:
        for text, score, pts in line:
            text = (text or "").strip()
            if not text:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            tokens.append(Token(text, float(score), Box(min(xs), min(ys), max(xs), max(ys)), page_index))
    return tokens


# ------------------------------------------------------- photo clean-up --
def _order_quad(pts: np.ndarray) -> np.ndarray:
    pts = pts.reshape(4, 2).astype("float32")
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype="float32")


def find_paper_quad(img: Image.Image) -> np.ndarray | None:
    """Locate a bright sheet of paper on a darker background. Returns 4 corners or None."""
    import cv2

    rgb = np.asarray(img.convert("RGB"))
    h, w = rgb.shape[:2]
    scale = 1000 / max(h, w)
    small = cv2.resize(rgb, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), (7, 7), 0)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    if area < 0.15 * small.shape[0] * small.shape[1] or area > 0.97 * small.shape[0] * small.shape[1]:
        return None
    hull = cv2.convexHull(c)
    peri = cv2.arcLength(hull, True)
    quad = None
    for eps in (0.02, 0.03, 0.04, 0.06, 0.08):
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4:
            quad = approx
            break
    if quad is None:
        quad = cv2.boxPoints(cv2.minAreaRect(hull))
    return _order_quad(np.asarray(quad)) / scale


def straighten_photo(img: Image.Image) -> tuple[Image.Image, list[str]]:
    import cv2

    notes: list[str] = []
    quad = find_paper_quad(img)
    if quad is None:
        notes.append("paper edges not found; used the photo as-is")
        return img, notes
    tl, tr, br, bl = quad
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32")
    m = cv2.getPerspectiveTransform(quad.astype("float32"), dst)
    warped = cv2.warpPerspective(np.asarray(img.convert("RGB")), m, (width, height),
                                 flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    notes.append("perspective corrected and cropped to the receipt paper")
    return Image.fromarray(warped), notes


# ----------------------------------------------------------- loaders --
def _open_photo(path: Path) -> Image.Image:
    if path.suffix.lower() in {".heic", ".heif"}:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    with Image.open(path) as im:
        im.load()
        return im.copy()


def load_photo(path: Path) -> list[Page]:
    img = _open_photo(path)
    notes = []
    fixed = ImageOps.exif_transpose(img)
    if fixed.size != img.size or fixed.tobytes()[:64] != img.tobytes()[:64]:
        notes.append("rotated upright using the photo's orientation tag")
    img = fixed.convert("RGB")
    img, more = straighten_photo(img)
    notes += more
    return [Page(0, img, ocr_tokens(img, 0), "photo", preprocessing=notes)]


def _pdf_text_tokens(page, textpage, scale: float, height_pt: float, index: int) -> list[Token]:
    tokens: list[Token] = []
    n = textpage.count_chars()
    word, box = "", None

    def flush():
        nonlocal word, box
        if word.strip() and box is not None:
            tokens.append(Token(word.strip(), 1.0, box, index))
        word, box = "", None

    for i in range(n):
        ch = textpage.get_text_range(i, 1)
        if not ch or ch.isspace() or ch in "\r\n\x02":
            flush()
            continue
        # "loose" boxes use the font's full height, so punctuation lines up with letters
        l, b, r, t = textpage.get_charbox(i, loose=True)
        cb = Box(l * scale, (height_pt - t) * scale, r * scale, (height_pt - b) * scale)
        if box is not None:
            em = max(cb.h, box.h)
            if cb.x0 - box.x1 > 0.25 * em or abs(cb.cy - box.cy) > 0.35 * em:
                flush()
        word += ch
        box = cb if box is None else box.union(cb)
    flush()
    return tokens


def load_pdf(path: Path) -> list[Page]:
    import pypdfium2 as pdfium

    pages: list[Page] = []
    pdf = pdfium.PdfDocument(str(path))
    try:
        scale = RENDER_DPI / 72
        for i in range(len(pdf)):
            page = pdf[i]
            w_pt, h_pt = page.get_size()
            rotation = page.get_rotation()
            img = page.render(scale=scale).to_pil().convert("RGB")
            textpage = page.get_textpage()
            text = textpage.get_text_range()
            if rotation == 0 and len(text.strip()) >= MIN_TEXT_CHARS:
                tokens = _pdf_text_tokens(page, textpage, scale, h_pt, i)
                pages.append(Page(i, img, tokens, "pdf-text", scale, (w_pt, h_pt),
                                  ["read the PDF's built-in text layer (no OCR needed)"]))
            else:
                notes = ["no usable text layer; rendered at %d dpi and read with OCR" % RENDER_DPI]
                if rotation:
                    notes.append(f"page has {rotation}° rotation; annotations will use a re-rendered image")
                pages.append(Page(i, img, ocr_tokens(img, i), "pdf-scan",
                                  scale if rotation == 0 else None, (w_pt, h_pt) if rotation == 0 else None, notes))
            textpage.close()
            page.close()
    finally:
        pdf.close()
    return pages


def load_pages(path: Path) -> list[Page]:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return load_pdf(path)
    if ext in PHOTO_EXTS:
        return load_photo(path)
    raise ValueError(f"Unsupported receipt file type: {path.name}")
