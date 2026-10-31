"""Template profiles: which cell of a company's top sheet holds which value.

A profile is a small YAML file, so supporting a new production company's
template means writing (later: clicking together) a new profile, not code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ..core.xlsx_fill import TemplateMappingError, split_ref

HEADER_FIELDS = {
    "crew_phone", "production", "production_number", "company", "crew_member", "department", "position",
    "envelope_number", "period_start", "period_end", "float_amount", "cash_returned",
    "reported_total", "receipts_total", "receipt_count",
}
LINE_FIELDS = {"number", "date", "vendor", "description", "account_code", "amount", "payment", "tax"}


VALUE_TYPES = {"auto", "text", "number", "money", "date", "digits"}


def _parse_target(v) -> tuple[str, str]:
    """A target is either "B4" / "A" or {cell|col: ..., type: number|text|money|date}."""
    if isinstance(v, dict):
        ref = str(v.get("cell") or v.get("col")).upper()
        typ = v.get("type", "auto")
        if typ not in VALUE_TYPES:
            raise TemplateMappingError(f"Unknown value type {typ!r}")
        return ref, typ
    return str(v).upper(), "auto"


@dataclass
class TemplateProfile:
    name: str
    template_file: Path
    sheet: str
    header: dict[str, str]
    first_row: int
    max_rows: int
    columns: dict[str, str]
    overflow: str
    source: Path
    types: dict = None                 # cell/column -> value type
    receipt_number_style: str = "full"  # "full" -> PC001-003 ; "index" -> 3

    def cells_for(self, n_lines: int) -> list[str]:
        cells = list(self.header.values())
        for i in range(n_lines):
            cells += [f"{col}{self.first_row + i}" for col in self.columns.values()]
        return cells


def load_profile(path: Path) -> TemplateProfile:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key in ("name", "template_file", "sheet", "header", "line_items"):
        if key not in data:
            raise TemplateMappingError(f"Profile {path.name} is missing '{key}'")
    types: dict[str, str] = {}
    header = {}
    for k, v in data["header"].items():
        ref, typ = _parse_target(v)
        header[k], types[ref] = ref, typ
    unknown = set(header) - HEADER_FIELDS
    if unknown:
        raise TemplateMappingError(f"Unknown header fields in profile: {sorted(unknown)}")
    li = data["line_items"]
    columns = {}
    for k, v in li["columns"].items():
        ref, typ = _parse_target(v)
        columns[k], types[ref] = ref, typ
    unknown = set(columns) - LINE_FIELDS
    if unknown:
        raise TemplateMappingError(f"Unknown line-item fields in profile: {sorted(unknown)}")
    for ref in header.values():
        split_ref(ref)  # validates
    template = Path(data["template_file"])
    if not template.is_absolute():
        template = path.parent / template
    style = data.get("receipt_number", "full")
    if style not in ("full", "index"):
        raise TemplateMappingError("receipt_number must be 'full' or 'index'")
    profile = TemplateProfile(data["name"], template, data["sheet"], header, int(li["first_row"]),
                              int(li["max_rows"]), columns, data.get("overflow", "refuse"), path, types, style)
    line_cells = {f"{c}{profile.first_row + i}" for i in range(profile.max_rows) for c in columns.values()}
    clash = line_cells & set(header.values())
    if clash:
        raise TemplateMappingError(f"Header cells overlap the line-item table: {sorted(clash)}")
    return profile
