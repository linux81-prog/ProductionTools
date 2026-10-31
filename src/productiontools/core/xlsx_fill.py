"""Surgical Excel (.xlsx) filling that preserves the template.

Why not just open and re-save the workbook with a spreadsheet library?
Because general-purpose libraries rebuild the whole file on save and can
silently drop things they do not understand (logos, certain formatting,
printer settings, custom XML). Instead this module:

  1. copies the template package part-by-part,
  2. edits ONLY the specific cells named in the mapping, directly in the
     worksheet XML, keeping each cell's existing style,
  3. sets Excel's "recalculate formulas on open" flag in ``workbook.xml``,
  4. leaves every other byte of every other part exactly as it was.

Documented, intentional changes (the complete list):
  * the values of mapped cells (their style ``s="..."`` is preserved),
  * ``fullCalcOnLoad="1"`` on ``<calcPr>`` in ``xl/workbook.xml`` so Excel
    recalculates every formula when it opens the file,
  * the optional ``spans`` hint on a row is widened only if a mapped cell
    falls outside it (a performance hint Excel uses; no visual effect).

Safety refusals: a mapped cell that contains a formula, or that sits inside
a merged range without being its top-left cell, raises an error instead of
being written.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

from .filestore import OverwriteRefusedError

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

ALLOWED_CHANGES = [
    ("Mapped cell values", "Only the cells listed in the template profile receive new values; each keeps its original formatting style."),
    ("workbook.xml <calcPr fullCalcOnLoad=\"1\">", "Tells Excel to recalculate every formula when the file is opened, so totals reflect the new values."),
    ("Row 'spans' hint (only if needed)", "An optional performance hint listing which columns a row uses; widened only when a mapped cell is outside it. No visual effect."),
]


class TemplateMappingError(ValueError):
    """The mapping asks for something that would damage the template."""


CellValue = str | int | float | Decimal | date | datetime | None


# ---------------------------------------------------------------- helpers --
def col_to_num(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n


def num_to_col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


_REF_RE = re.compile(r"^([A-Z]{1,3})(\d+)$")


def split_ref(ref: str) -> tuple[str, int]:
    m = _REF_RE.match(ref.upper().replace("$", ""))
    if not m:
        raise TemplateMappingError(f"Not a cell reference: {ref!r}")
    return m.group(1), int(m.group(2))


def _xml_text(s: str) -> str:
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_ATTR_RE = re.compile(r'([\w:]+)="([^"]*)"')


def _attrs(open_tag: str) -> list[tuple[str, str]]:
    return _ATTR_RE.findall(open_tag)


def excel_serial(d: date | datetime, date1904: bool = False) -> float:
    base = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 30)
    if not isinstance(d, datetime):
        d = datetime(d.year, d.month, d.day)
    delta = d - base
    return delta.days + delta.seconds / 86400


# ------------------------------------------------------- package structure --
def resolve_sheet_part(zf: zipfile.ZipFile, sheet_name: str) -> str:
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rid = None
    for sh in wb.iter(f"{{{NS_MAIN}}}sheet"):
        if sh.get("name") == sheet_name:
            rid = sh.get(f"{{{NS_REL}}}id")
    if rid is None:
        names = [s.get("name") for s in wb.iter(f"{{{NS_MAIN}}}sheet")]
        raise TemplateMappingError(f"Sheet {sheet_name!r} not found; template has {names}")
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rels.iter(f"{{{NS_PKG_REL}}}Relationship"):
        if rel.get("Id") == rid:
            target = rel.get("Target")
            if target.startswith("/"):
                return target.lstrip("/")
            return posixpath.normpath(posixpath.join("xl", target))
    raise TemplateMappingError(f"Relationship {rid} for sheet {sheet_name!r} not found")


def workbook_uses_1904(zf: zipfile.ZipFile) -> bool:
    xml = zf.read("xl/workbook.xml").decode("utf-8")
    m = re.search(r"<(?:\w+:)?workbookPr\b[^>]*\bdate1904=\"(1|true)\"", xml)
    return bool(m)


# ------------------------------------------------------------ sheet editing --
@dataclass
class _Span:
    start: int
    end: int
    text: str


def _prefix(xml: str) -> str:
    m = re.search(r"<(?:(\w+):)?sheetData\b", xml)
    if not m:
        raise TemplateMappingError("Worksheet has no <sheetData> element")
    return f"{m.group(1)}:" if m.group(1) else ""


def sheet_data_bounds(xml: str) -> tuple[int, int, str]:
    """Return (content_start, content_end, prefix) of the sheetData element.

    For a self-closing ``<sheetData/>`` both indices point at the tag itself.
    """
    p = _prefix(xml)
    m_self = re.search(rf"<{re.escape(p)}sheetData\s*/>", xml)
    if m_self:
        return m_self.start(), m_self.end(), p
    m_open = re.search(rf"<{re.escape(p)}sheetData\b[^>]*>", xml)
    m_close = xml.find(f"</{p}sheetData>", m_open.end())
    return m_open.end(), m_close, p


def iter_rows(content: str, p: str, offset: int = 0) -> list[tuple[int, _Span]]:
    pat = re.compile(rf"<{re.escape(p)}row\b[^>]*?(?:/>|>.*?</{re.escape(p)}row>)", re.S)
    out = []
    for m in pat.finditer(content):
        rnum = re.search(r'\br="(\d+)"', m.group(0)[: m.group(0).find(">") + 1])
        out.append((int(rnum.group(1)), _Span(m.start() + offset, m.end() + offset, m.group(0))))
    return out


def iter_cells(row_xml: str, p: str) -> list[tuple[str, _Span]]:
    pat = re.compile(rf"<{re.escape(p)}c\b[^>]*?(?:/>|>.*?</{re.escape(p)}c>)", re.S)
    out = []
    for m in pat.finditer(row_xml):
        tag = m.group(0)[: m.group(0).find(">") + 1]
        r = re.search(r'\br="([A-Z]+\d+)"', tag)
        out.append((r.group(1), _Span(m.start(), m.end(), m.group(0))))
    return out


def merged_ranges(xml: str) -> list[tuple[int, int, int, int]]:
    out = []
    for ref in re.findall(r'<(?:\w+:)?mergeCell\b[^>]*\bref="([A-Z]+\d+):([A-Z]+\d+)"', xml):
        (c1, r1), (c2, r2) = split_ref(ref[0]), split_ref(ref[1])
        out.append((col_to_num(c1), r1, col_to_num(c2), r2))
    return out


def _build_cell(p: str, ref: str, old_open_tag: str | None, value: CellValue, date1904: bool) -> str:
    keep = []
    if old_open_tag:
        for k, v in _attrs(old_open_tag):
            if k in ("r", "t", "vm", "cm"):
                continue
            keep.append((k, v))
    attrs = [("r", ref)] + keep
    if value is None:
        return f"<{p}c " + " ".join(f'{k}="{v}"' for k, v in attrs) + "/>"
    if isinstance(value, (date, datetime)):
        num = excel_serial(value, date1904)
        num_s = str(int(num)) if float(num).is_integer() else repr(num)
        return f"<{p}c " + " ".join(f'{k}="{v}"' for k, v in attrs) + f"><{p}v>{num_s}</{p}v></{p}c>"
    if isinstance(value, bool):
        attrs.append(("t", "b"))
        return f"<{p}c " + " ".join(f'{k}="{v}"' for k, v in attrs) + f"><{p}v>{int(value)}</{p}v></{p}c>"
    if isinstance(value, (int, float, Decimal)):
        num_s = format(Decimal(str(value)), "f")
        return f"<{p}c " + " ".join(f'{k}="{v}"' for k, v in attrs) + f"><{p}v>{num_s}</{p}v></{p}c>"
    text = str(value)
    attrs.append(("t", "inlineStr"))
    space = ' xml:space="preserve"' if text != text.strip() or "\n" in text else ""
    return (f"<{p}c " + " ".join(f'{k}="{v}"' for k, v in attrs)
            + f"><{p}is><{p}t{space}>{_xml_text(text)}</{p}t></{p}is></{p}c>")


def set_cells(sheet_xml: str, values: dict[str, CellValue], date1904: bool = False) -> str:
    """Return new sheet XML with only the given cells changed."""
    merges = merged_ranges(sheet_xml)
    by_row: dict[int, dict[str, CellValue]] = {}
    for ref, val in values.items():
        col, row = split_ref(ref)
        c = col_to_num(col)
        for (c1, r1, c2, r2) in merges:
            if c1 <= c <= c2 and r1 <= row <= r2 and (c, row) != (c1, r1):
                raise TemplateMappingError(
                    f"{ref} is inside merged range {num_to_col(c1)}{r1}:{num_to_col(c2)}{r2} "
                    f"but is not its top-left cell; map {num_to_col(c1)}{r1} instead.")
        by_row.setdefault(row, {})[f"{col}{row}"] = val

    start, end, p = sheet_data_bounds(sheet_xml)
    if re.fullmatch(rf"<{re.escape(p)}sheetData\s*/>", sheet_xml[start:end]):
        content = ""
        prefix_xml = sheet_xml[:start] + f"<{p}sheetData>"
        suffix_xml = f"</{p}sheetData>" + sheet_xml[end:]
    else:
        content, prefix_xml, suffix_xml = sheet_xml[start:end], sheet_xml[:start], sheet_xml[end:]

    rows = iter_rows(content, p)
    row_map = {r: span for r, span in rows}

    # Apply edits from the bottom of the string upward so offsets stay valid.
    edits: list[tuple[int, int, str]] = []
    for rnum in sorted(by_row):
        cells_wanted = by_row[rnum]
        if rnum in row_map:
            span = row_map[rnum]
            edits.append((span.start, span.end, _edit_row(span.text, p, cells_wanted, date1904)))
        else:
            new_cells = "".join(_build_cell(p, ref, None, v, date1904)
                                for ref, v in sorted(cells_wanted.items(), key=lambda kv: col_to_num(split_ref(kv[0])[0])))
            new_row = f'<{p}row r="{rnum}">{new_cells}</{p}row>'
            after = [span for r, span in rows if r > rnum]
            pos = after[0].start if after else len(content)
            edits.append((pos, pos, new_row))

    for s, e, txt in sorted(edits, key=lambda t: (t[0], t[1]), reverse=True):
        content = content[:s] + txt + content[e:]
    return prefix_xml + content + suffix_xml


def _edit_row(row_xml: str, p: str, wanted: dict[str, CellValue], date1904: bool) -> str:
    gt = row_xml.find(">")
    open_tag = row_xml[: gt + 1]
    if open_tag.endswith("/>"):
        open_tag = open_tag[:-2].rstrip() + ">"
        inner, close = "", f"</{p}row>"
    else:
        inner = row_xml[gt + 1: -len(f"</{p}row>")]
        close = f"</{p}row>"

    cells = iter_cells(inner, p)
    existing = {ref: span for ref, span in cells}
    edits = []
    for ref, val in wanted.items():
        if ref in existing:
            span = existing[ref]
            if re.search(rf"<{re.escape(p)}f\b", span.text):
                raise TemplateMappingError(f"{ref} contains a formula in the template; refusing to overwrite it.")
            old_tag = span.text[: span.text.find(">") + 1]
            edits.append((span.start, span.end, _build_cell(p, ref, old_tag, val, date1904)))
        else:
            c = col_to_num(split_ref(ref)[0])
            after = [s for r, s in cells if col_to_num(split_ref(r)[0]) > c]
            pos = after[0].start if after else len(inner)
            edits.append((pos, pos, _build_cell(p, ref, None, val, date1904)))
    for s, e, txt in sorted(edits, key=lambda t: (t[0], t[1]), reverse=True):
        inner = inner[:s] + txt + inner[e:]

    # Widen the optional spans hint only if needed.
    m = re.search(r'\bspans="(\d+):(\d+)"', open_tag)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        cols = [col_to_num(split_ref(r)[0]) for r in wanted]
        nlo, nhi = min([lo] + cols), max([hi] + cols)
        if (nlo, nhi) != (lo, hi):
            open_tag = open_tag[: m.start()] + f'spans="{nlo}:{nhi}"' + open_tag[m.end():]
    return open_tag + inner + close


def set_full_calc_on_load(workbook_xml: str) -> str:
    m = re.search(r"<(\w+:)?calcPr\b[^>]*?/?>", workbook_xml)
    if m:
        tag = m.group(0)
        if re.search(r'\bfullCalcOnLoad="[^"]*"', tag):
            new = re.sub(r'\bfullCalcOnLoad="[^"]*"', 'fullCalcOnLoad="1"', tag)
        else:
            end = -2 if tag.endswith("/>") else -1
            head = tag[:end].rstrip()
            new = head + ' fullCalcOnLoad="1"' + tag[len(head):]  # keep the original spacing before "/>"
        return workbook_xml[: m.start()] + new + workbook_xml[m.end():]
    pm = re.search(r"<(\w+:)?workbook\b", workbook_xml)
    p = pm.group(1) or "" if pm else ""
    # Schema order: ... sheets, functionGroups, externalReferences, definedNames, calcPr ...
    for anchor in (f"</{p}definedNames>", f"</{p}externalReferences>", f"</{p}functionGroups>", f"</{p}sheets>"):
        i = workbook_xml.find(anchor)
        if i != -1:
            i += len(anchor)
            return workbook_xml[:i] + f'<{p}calcPr fullCalcOnLoad="1"/>' + workbook_xml[i:]
    raise TemplateMappingError("Could not find where to place <calcPr> in workbook.xml")


# ----------------------------------------------------------------- driver --
def fill_template_copy(template: Path, dest: Path, sheet_name: str, values: dict[str, CellValue]) -> dict:
    """Create ``dest`` as a filled copy of ``template``. The template is only read."""
    template, dest = Path(template), Path(dest)
    if dest.exists():
        raise OverwriteRefusedError(f"Refusing to overwrite existing file: {dest}")
    if template.resolve() == dest.resolve():
        raise OverwriteRefusedError("Destination must differ from the template")

    with zipfile.ZipFile(template) as zin:
        sheet_part = resolve_sheet_part(zin, sheet_name)
        date1904 = workbook_uses_1904(zin)
        new_sheet = set_cells(zin.read(sheet_part).decode("utf-8"), values, date1904)
        new_wb = set_full_calc_on_load(zin.read("xl/workbook.xml").decode("utf-8"))

        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "xb") as fh, zipfile.ZipFile(fh, "w") as zout:
            for info in zin.infolist():
                if info.filename == sheet_part:
                    data = new_sheet.encode("utf-8")
                elif info.filename == "xl/workbook.xml":
                    data = new_wb.encode("utf-8")
                else:
                    data = zin.read(info.filename)
                zout.writestr(info, data, compress_type=info.compress_type)
    return {"sheet_part": sheet_part, "cells_written": sorted(values), "date1904": date1904}
