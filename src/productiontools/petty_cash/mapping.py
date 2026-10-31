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
    "envelope_id", "crew_phone", "production", "production_number", "company", "crew_member", "department", "position",
    "envelope_number", "period_start", "period_end", "float_amount", "cash_returned",
    "reported_total", "receipts_total", "receipt_count",
}
LINE_FIELDS = {"number", "date", "vendor", "description", "account_code", "account_description", "amount",
               "payment", "tax"}


VALUE_TYPES = {"auto", "text", "number", "money", "date", "digits"}


def _parse_target(v) -> tuple[str, str, object]:
    """A target is "B4" / "A", or {cell|col: ..., type: number|text|money|date|digits, replace_formula: bool}."""
    if isinstance(v, dict):
        ref = str(v.get("cell") or v.get("col")).upper()
        typ = v.get("type", "auto")
        if typ not in VALUE_TYPES:
            raise TemplateMappingError(f"Unknown value type {typ!r}")
        if v.get("replace_formula"):
            if not v.get("expect_formula"):
                raise TemplateMappingError(f"{ref}: replace_formula requires expect_formula (the exact formula being replaced)")
            return ref, typ, str(v["expect_formula"])
        return ref, typ, False
    return str(v).upper(), "auto", False


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
    replace_formulas: dict = None      # header cell -> the exact template formula the user approved replacing
    protected_formulas: tuple = ()     # "Sheet!Cell" formulas that must stay intact (e.g. page numbering)
    never_write: tuple = ()            # cells the app must never fill (e.g. TOTAL DISBURSED until confirmed)
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
    replace = {}
    for k, v in data["header"].items():
        ref, typ, rf = _parse_target(v)
        header[k], types[ref] = ref, typ
        if rf:
            replace[ref] = rf
    unknown = set(header) - HEADER_FIELDS
    if unknown:
        raise TemplateMappingError(f"Unknown header fields in profile: {sorted(unknown)}")
    li = data["line_items"]
    columns = {}
    for k, v in li["columns"].items():
        ref, typ, rf = _parse_target(v)
        if rf:
            raise TemplateMappingError("replace_formula is only allowed on single header cells")
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
                              int(li["max_rows"]), columns, data.get("overflow", "refuse"), path, types,
                              replace, tuple(data.get("protected_formulas", [])),
                              never_write=tuple(str(c).upper() for c in data.get("never_write", [])),
                              receipt_number_style=style)
    line_cells = {f"{c}{profile.first_row + i}" for i in range(profile.max_rows) for c in columns.values()}
    forbidden = (line_cells | set(header.values())) & set(profile.never_write)
    if forbidden:
        raise TemplateMappingError(f"Profile maps cells it must never write: {sorted(forbidden)}")
    clash = line_cells & set(header.values())
    if clash:
        raise TemplateMappingError(f"Header cells overlap the line-item table: {sorted(clash)}")
    return profile
