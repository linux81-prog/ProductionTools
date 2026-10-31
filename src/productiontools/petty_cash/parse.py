"""Find vendor, date, subtotal, tax, total and payment type among positioned words.

Every result carries a confidence score (0-1) and the exact words it came
from, so the annotation step can circle the right place and the review step
can highlight anything uncertain. These are rules of thumb, not certainties;
anything below the review threshold must be checked by a person.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import median

from .models import Box, FieldValue, Page, Token

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

MONEY_RE = re.compile(r"(?<![\d.,])[\$£€]?\s?(\d{1,3}(?:,\d{3})+|\d+)[.,](\d{2})(?![\d%])(?!\s?%)")
PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}")


# ----------------------------------------------------------------- rows --
@dataclass
class Row:
    tokens: list[Token]
    text: str
    spans: list[tuple[int, int]]  # char span of each token within text

    @property
    def box(self) -> Box:
        b = self.tokens[0].box
        for t in self.tokens[1:]:
            b = b.union(t.box)
        return b

    @property
    def page(self) -> int:
        return self.tokens[0].page

    def tokens_in(self, s: int, e: int) -> list[Token]:
        return [t for t, (a, b) in zip(self.tokens, self.spans) if a < e and b > s]

    def score_in(self, s: int, e: int) -> float:
        toks = self.tokens_in(s, e)
        return min((t.score for t in toks), default=0.0)

    def box_in(self, s: int, e: int) -> Box | None:
        toks = self.tokens_in(s, e)
        if not toks:
            return None
        b = toks[0].box
        for t in toks[1:]:
            b = b.union(t.box)
        return b


def _row_of(tokens: list[Token]) -> Row:
    tokens = sorted(tokens, key=lambda t: t.box.x0)
    text, spans = "", []
    for t in tokens:
        if text:
            text += " "
        spans.append((len(text), len(text) + len(t.text)))
        text += t.text
    return Row(tokens, text, spans)


def group_rows(tokens: list[Token]) -> list[Row]:
    """Group words into visual lines (rows) by vertical overlap."""
    if not tokens:
        return []
    med_h = median(t.box.h for t in tokens) or 1
    rows: list[list[Token]] = []
    for t in sorted(tokens, key=lambda t: (t.page, t.box.cy)):
        placed = False
        for row in reversed(rows[-4:]):
            if row[0].page != t.page:
                continue
            cy = sum(x.box.cy for x in row) / len(row)
            top = min(x.box.y0 for x in row)
            bot = max(x.box.y1 for x in row)
            overlap = min(bot, t.box.y1) - max(top, t.box.y0)
            if abs(t.box.cy - cy) < 0.45 * med_h and overlap > 0.4 * min(t.box.h, bot - top):
                row.append(t)
                placed = True
                break
        if not placed:
            rows.append([t])
    out = [_row_of(row) for row in rows]
    out.sort(key=lambda r: (r.page, r.box.y0))
    return out


# ---------------------------------------------------------------- money --
def money_matches(row: Row):
    for m in MONEY_RE.finditer(row.text):
        whole = m.group(1).replace(",", "")
        yield Decimal(f"{whole}.{m.group(2)}"), m.start(), m.end()


def _amount_on(row: Row, after: int = 0):
    found = [mm for mm in money_matches(row) if mm[1] >= after]
    return found[-1] if found else None


@dataclass
class Cand:
    value: object
    conf: float
    row: Row
    s: int
    e: int
    note: str = ""


def _keyword_amounts(rows: list[Row], patterns: list[tuple[str, float]], exclude: str | None) -> list[Cand]:
    out = []
    for i, row in enumerate(rows):
        up = row.text.upper()
        if exclude and re.search(exclude, up):
            continue
        for pat, weight in patterns:
            m = re.search(pat, up)
            if not m:
                continue
            amt = _amount_on(row, m.end())
            note = ""
            target_row = row
            if amt is None and i + 1 < len(rows):
                nxt = rows[i + 1]
                if not re.search(r"[A-Z]{3,}", nxt.text.upper()):  # next line is just a number
                    amt = _amount_on(nxt)
                    target_row = nxt
                    weight *= 0.85
                    note = "amount found on the line below its label"
            if amt is not None:
                value, s, e = amt
                conf = weight * max(target_row.score_in(s, e), 0.01)
                out.append(Cand(value, conf, target_row, s, e, note))
            break
    return out


TOTAL_PATTERNS = [
    (r"\bGRAND\s*TOTAL\b", 0.97),
    (r"\b(AMOUNT|BALANCE|TOTAL)\s*DUE\b", 0.95),
    (r"\bTOTAL\s*(PAID|CHARGED|USD)\b", 0.95),
    (r"(?<!SUB)(?<!SUB )(?<!SUB-)\bTOTAL\b", 0.92),
    (r"\bAMOUNT\b", 0.6),
]
TOTAL_EXCLUDE = r"SUB\s*-?\s*TOTAL|SAVINGS|YOU\s+SAVED|ITEMS?\b|TOTAL\s+TAX|TAX\s+TOTAL|DISCOUNT|QTY|TIP\s+GUIDE|SUGGESTED"
SUBTOTAL_PATTERNS = [(r"\bSUB\s*-?\s*TOTAL\b", 0.95)]
TAX_PATTERNS = [(r"\b(SALES\s+)?TAX\b", 0.92)]
EXTRA_PATTERNS = [(r"\b(SHIPPING|DELIVERY|HANDLING|FREIGHT|TIP|GRATUITY|SERVICE\s+(CHARGE|FEE))\b", 0.9)]
TAX_EXCLUDE = r"TAX\s*(ID|EXEMPT|INVOICE)|PRE-?TAX|TAXABLE|SUB\s*-?\s*TOTAL|\bTOTAL\b(?!\s+TAX)"


def _field_from(c: Cand | None, name: str, source: str) -> FieldValue:
    if c is None:
        return FieldValue(name, None, 0.0, note="not found")
    return FieldValue(name, c.value, round(min(c.conf, 0.99), 3), c.row.page, c.row.box_in(c.s, c.e), source, note=c.note)


def find_amounts(rows: list[Row], source: str) -> dict[str, FieldValue]:
    subs = _keyword_amounts(rows, SUBTOTAL_PATTERNS, None)
    taxes = _keyword_amounts(rows, TAX_PATTERNS, TAX_EXCLUDE)
    totals = _keyword_amounts(rows, TOTAL_PATTERNS, TOTAL_EXCLUDE)

    extras = _keyword_amounts(rows, EXTRA_PATTERNS, r"SUB\s*-?\s*TOTAL|\bTOTAL\b|FREE")
    sub = max(subs, key=lambda c: c.conf) if subs else None
    tax = max(taxes, key=lambda c: c.conf) if taxes else None
    extra_sum = sum((c.value for c in extras), Decimal("0"))
    expected = (sub.value + tax.value + extra_sum) if (sub and tax) else None
    extra_txt = f" + other charges {extra_sum}" if extras else ""

    total = None
    if totals:
        best_w = max(c.conf for c in totals)
        contenders = [c for c in totals if c.conf >= best_w - 0.08]
        if sub and tax:
            exact = [c for c in contenders if c.value == expected]
            if exact:
                total = exact[0]
        if total is None:
            total = max(contenders, key=lambda c: (c.value, c.conf))

    fields = {"subtotal": _field_from(sub, "subtotal", source),
              "tax": _field_from(tax, "tax", source),
              "total": _field_from(total, "total", source)}

    t = fields["total"]
    if t.value is not None and sub and tax:
        if expected == t.value:
            t.confidence = round(min(0.99, t.confidence + 0.05), 3)
            t.note = (t.note + "; " if t.note else "") + f"subtotal + tax{extra_txt and ' + other charges'} = total (cross-check passed)"
        else:
            t.confidence = round(t.confidence * 0.78, 3)
            t.note = (t.note + "; " if t.note else "") + (
                f"subtotal {sub.value} + tax {tax.value}{extra_txt} = {expected}, not {t.value} (cross-check failed)")
    fields["other_charges"] = FieldValue("other_charges", extra_sum if extras else None,
                                         round(min((c.conf for c in extras), default=0.0), 3), source=source,
                                         note=", ".join(f"{c.row.text}" for c in extras))
    if t.value is None and sub and not tax:
        t.note = "no TOTAL line found"
    return fields


# ----------------------------------------------------------------- date --
DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})\b"), "mdy"),
    (re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.I), "Mdy"),
    (re.compile(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?,?\s+(\d{4})\b", re.I), "dMy"),
]


def _mk_date(kind: str, g) -> tuple[date | None, bool]:
    try:
        if kind == "ymd":
            return date(int(g[0]), int(g[1]), int(g[2])), False
        if kind == "mdy":
            y = int(g[2]) + (2000 if len(g[2]) == 2 else 0)
            m, d = int(g[0]), int(g[1])
            return date(y, m, d), (m <= 12 and d <= 12 and m != d)
        if kind == "Mdy":
            return date(int(g[2]), MONTHS[g[0][:3].lower()], int(g[1])), False
        if kind == "dMy":
            return date(int(g[2]), MONTHS[g[1][:3].lower()], int(g[0])), False
    except (ValueError, KeyError):
        return None, False
    return None, False


def find_date(rows: list[Row], source: str) -> FieldValue:
    cands: list[Cand] = []
    for row in rows:
        up = row.text.upper()
        weight = 0.85
        if re.search(r"\b(INVOICE|ORDER|TRANS(ACTION)?|PURCHASE|RECEIPT)\s*DATE\b|\bDATE\s*[:#]?", up):
            weight = 0.95
        if re.search(r"\bDUE\b|\bEXP(IRES|IRY)?\b|\bSHIP(PED)?\b|\bDELIVER", up):
            weight = 0.45
        for pat, kind in DATE_PATTERNS:
            for m in pat.finditer(row.text):
                d, ambiguous = _mk_date(kind, m.groups())
                if d is None or not (2000 <= d.year <= 2100):
                    continue
                w = weight * (0.93 if ambiguous else 1.0)
                note = "day/month order assumed US (MM/DD)" if ambiguous else ""
                cands.append(Cand(d, w * max(row.score_in(m.start(), m.end()), 0.01), row, m.start(), m.end(), note))
    if not cands:
        return FieldValue("date", None, 0.0, note="not found")
    best = max(cands, key=lambda c: c.conf)
    rivals = {c.value for c in cands if c.conf >= best.conf - 0.05 and c.value != best.value}
    f = _field_from(best, "date", source)
    if rivals:
        f.confidence = round(f.confidence * 0.8, 3)
        f.note = (f.note + "; " if f.note else "") + f"other dates also present: {sorted(map(str, rivals))}"
    return f


# --------------------------------------------------------------- vendor --
VENDOR_SKIP = re.compile(
    r"RECEIPT|INVOICE|WELCOME|THANK|STORE\s*#|\bTEL\b|PHONE|WWW\.|\.COM|@|ORDER|BILL\s*TO|SHIP\s*TO|PAGE\s+\d|"
    r"CASHIER|REGISTER|TERMINAL|\bTRANS\b|DATE|TIME|CUSTOMER\s+COPY|MERCHANT|SALE\b|STATEMENT", re.I)
ADDRESS_RE = re.compile(r"^\d+\s+\w+|\b(ST|AVE|BLVD|RD|DR|LN|SUITE|STE|HWY|WAY)\b\.?|\b[A-Z]{2}\s+\d{5}\b", re.I)


def find_vendor(rows: list[Row], pages: list[Page], source: str, known_vendors: list[str] = ()) -> FieldValue:
    first = [r for r in rows if r.page == 0]
    if not first:
        return FieldValue("vendor", None, 0.0, note="not found")
    page_h = pages[0].image.height
    top_rows = [r for r in first if r.box.y0 < 0.4 * page_h][:12]
    med_h = median(t.box.h for r in first for t in r.tokens) or 1

    # Split rows at wide gaps so side-by-side blocks (e.g. name left, "INVOICE" right) are separate.
    segments: list[Row] = []
    for row in top_rows:
        current = [row.tokens[0]]
        for t in row.tokens[1:]:
            if t.box.x0 - current[-1].box.x1 > 2.5 * med_h:
                segments.append(_row_of(current))
                current = []
            current.append(t)
        segments.append(_row_of(current))
    max_h = max((median(t.box.h for t in s.tokens) for s in segments), default=1)

    known = {re.sub(r"\W+", "", k.lower()): k for k in known_vendors}
    cands: list[tuple[float, Row, str]] = []
    for idx, row in enumerate(segments):
        text = row.text.strip(" -*:#")
        letters = sum(ch.isalpha() for ch in text)
        if len(text) < 3 or letters < 3 or letters / max(len(text.replace(" ", "")), 1) < 0.6:
            continue
        if VENDOR_SKIP.search(text) or PHONE_RE.search(text) or ADDRESS_RE.search(text) or list(money_matches(row)):
            continue
        height = median(t.box.h for t in row.tokens)
        score = 0.55
        score += min(0.15, 0.15 * (height / med_h - 1))    # bigger lettering -> likelier the name
        score += 0.08 if height >= 0.97 * max_h else 0      # the largest lettering near the top
        score += 0.1 if idx <= 1 else (0.05 if idx <= 3 else 0)
        score += 0.04 if text.isupper() else 0
        key = re.sub(r"\W+", "", text.lower())
        if key in known:
            score += 0.25
            text = known[key]
        score *= min(t.score for t in row.tokens)
        cands.append((score, row, text))
    if not cands:
        return FieldValue("vendor", None, 0.0, note="no likely business name near the top")
    score, row, text = max(cands, key=lambda c: c[0])
    printed = text
    text = tidy_vendor(text)
    others = sorted(cands, key=lambda c: -c[0])[1:2]
    note = ""
    if others and others[0][0] > score - 0.08:
        score *= 0.9
        note = f"close alternative: {others[0][2]!r}"
    if text != printed:
        note = (note + "; " if note else "") + f"printed as {printed!r}"
    return FieldValue("vendor", text, round(min(score, 0.95), 3), row.page, row.box, source, note=note)


_KEEP_UPPER = {"LLC", "USA", "LA", "NY", "BBQ", "TV", "DIY", "UPS", "CVS", "II", "III"}
_SPECIAL = {"CO": "Co", "CO.": "Co.", "INC": "Inc", "INC.": "Inc.", "LTD": "Ltd", "LTD.": "Ltd.", "AND": "and", "OF": "of", "THE": "The"}


def tidy_vendor(text: str) -> str:
    """Turn ALL-CAPS receipt headers into readable names ("HARDWARE BARN" -> "Hardware Barn")."""
    text = re.sub(r"\s+", " ", text).strip(" .,-*:#") + ("." if text.rstrip().endswith(("CO.", "INC.", "LTD.")) else "")
    if not text.isupper():
        return text
    words = []
    for i, w in enumerate(text.split(" ")):
        core = w.strip(".,&'")
        if core in _KEEP_UPPER or (len(core) <= 4 and not re.search(r"[AEIOUY]", core) and core.isalpha()):
            words.append(w)
        elif w in _SPECIAL and (i > 0 or w == "THE"):
            words.append(_SPECIAL[w])
        else:
            words.append(w.capitalize())
    return " ".join(words)


# -------------------------------------------------------------- payment --
def find_payment(rows: list[Row], source: str) -> FieldValue:
    methods = [(r"\bCASH\b", "Cash"), (r"\bVISA\b", "Visa"), (r"\bMASTER\s*CARD\b|\bMC\b", "Mastercard"),
               (r"\bAMEX\b|AMERICAN\s+EXPRESS", "Amex"), (r"\bDISCOVER\b", "Discover"), (r"\bDEBIT\b", "Debit card"),
               (r"\bCARD\s*(ENDING|#|\*{2,})", "Card")]
    for row in reversed(rows):
        up = row.text.upper()
        for pat, label in methods:
            m = re.search(pat, up)
            if m:
                return FieldValue("payment", label, round(0.9 * row.score_in(m.start(), m.end()), 3),
                                  row.page, row.box_in(m.start(), m.end()), source)
    return FieldValue("payment", None, 0.0, note="not found")


# ---------------------------------------------------------------- entry --
def parse_receipt(pages: list[Page], known_vendors: list[str] = ()) -> dict[str, FieldValue]:
    tokens = [t for p in pages for t in p.tokens]
    rows = group_rows(tokens)
    source = "pdf-text" if pages and all(p.source_kind == "pdf-text" for p in pages) else "ocr"
    fields = {"vendor": find_vendor(rows, pages, source, known_vendors),
              "date": find_date(rows, source)}
    fields.update(find_amounts(rows, source))
    fields["payment"] = find_payment(rows, source)
    return fields
