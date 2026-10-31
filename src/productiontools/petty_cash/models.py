"""Data records for the petty cash module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from PIL import Image

# Fields below this confidence are flagged for a person to check.
REVIEW_THRESHOLD = 0.80


@dataclass
class Box:
    """Rectangle in page-image pixel coordinates (origin top-left)."""
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def union(self, other: "Box") -> "Box":
        return Box(min(self.x0, other.x0), min(self.y0, other.y0), max(self.x1, other.x1), max(self.y1, other.y1))

    def intersects(self, other: "Box") -> bool:
        return not (other.x0 >= self.x1 or other.x1 <= self.x0 or other.y0 >= self.y1 or other.y1 <= self.y0)

    def to_norm(self, width: int, height: int) -> list[float]:
        return [round(self.x0 / width, 5), round(self.y0 / height, 5), round(self.x1 / width, 5), round(self.y1 / height, 5)]

    @staticmethod
    def from_norm(v, width: int, height: int) -> "Box":
        return Box(v[0] * width, v[1] * height, v[2] * width, v[3] * height)


@dataclass
class Token:
    """One word found on a page, with its position and recognition score."""
    text: str
    score: float
    box: Box
    page: int


@dataclass
class Page:
    index: int
    image: Image.Image          # working image used for OCR and layout (a copy; originals untouched)
    tokens: list[Token]
    source_kind: str            # "photo", "pdf-text", "pdf-scan"
    pdf_scale: float | None = None   # pixels per PDF point, for PDF pages
    pdf_page_size: tuple[float, float] | None = None  # (width, height) in points
    preprocessing: list[str] = field(default_factory=list)


@dataclass
class FieldValue:
    name: str
    value: Any
    confidence: float
    page: int | None = None
    box: Box | None = None
    source: str = "ocr"         # "ocr", "pdf-text", "reviewer"
    verified: bool = False
    note: str = ""

    @property
    def needs_review(self) -> bool:
        return (not self.verified) and (self.value is None or self.confidence < REVIEW_THRESHOLD)


@dataclass
class Receipt:
    source_name: str
    original_path: Path
    sha256: str
    pages: list[Page]
    fields: dict[str, FieldValue] = field(default_factory=dict)
    number: str | None = None          # full receipt number, e.g. PC001-003 (used in file names)
    seq: int | None = None             # position in the envelope: 1, 2, 3...
    label: str | None = None           # what is written on the receipt (matches the top sheet's number column)
    annotation_notes: dict = field(default_factory=dict)
    account_code: str | None = None
    description: str | None = None
    description_source: str = ""       # "reviewer" or "job line list"
    verified_by: str | None = None
    number_position: list[float] | None = None   # optional reviewer override (normalised box)
    overrides: list[dict] = field(default_factory=list)

    def val(self, name: str):
        f = self.fields.get(name)
        return f.value if f else None

    @property
    def total(self) -> Decimal | None:
        return self.val("total")

    @property
    def date(self) -> date | None:
        return self.val("date")

    @property
    def vendor(self) -> str | None:
        return self.val("vendor")


@dataclass
class Envelope:
    envelope_number: str          # e.g. "PC001"
    production: str
    production_number: str
    company: str
    crew_member: str
    department: str
    position: str
    period_start: date
    period_end: date
    float_amount: Decimal
    cash_returned: Decimal
    reported_total: Decimal       # what the crew member wrote on the envelope
    per_receipt_limit: Decimal = Decimal("250.00")
    crew_phone: str = ""
    envelope_id: str = ""         # unique envelope ID (unique within the project)
    receipts: list[Receipt] = field(default_factory=list)
