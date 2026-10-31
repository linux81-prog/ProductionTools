"""Workbook preservation checker.

Compares a filled copy against its original template with two independent
methods and reports every check in plain English:

  A. Package level (raw file contents): every internal part of the .xlsx must
     be byte-for-byte identical, except the documented allowed changes in
     ``xlsx_fill.ALLOWED_CHANGES``.
  B. Semantic level (opened with the openpyxl library): every cell value,
     formula and style outside the mapped cells, plus merged cells,
     conditional formatting, data validation, print area, page setup,
     margins, headers/footers, defined names, images, column widths, row
     heights and frozen panes must be identical.

The app runs this automatically after every fill and refuses to use a filled
workbook that fails.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .xlsx_fill import _attrs, iter_cells, iter_rows, sheet_data_bounds


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class PreservationReport:
    checks: list[Check] = field(default_factory=list)
    allowed_changes_seen: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(Check(name, passed, detail))

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [c.__dict__ for c in self.checks],
            "allowed_changes_seen": self.allowed_changes_seen,
        }


# ------------------------------------------------------------ package level --
def _normalise_workbook_xml(xml: str) -> str:
    xml = re.sub(r'\s+fullCalcOnLoad="[^"]*"', "", xml)
    xml = re.sub(r"<(\w+:)?calcPr\s*/>", "", xml)  # element we may have inserted
    return xml


def _rows(sheet_xml: str):
    s, e, p = sheet_data_bounds(sheet_xml)
    content = "" if re.fullmatch(rf"<{re.escape(p)}sheetData\s*/>", sheet_xml[s:e]) else sheet_xml[s:e]
    out = {}
    for rnum, span in iter_rows(content, p):
        tag = span.text[: span.text.find(">") + 1]
        attrs = {k: v for k, v in _attrs(tag)}
        cells = {ref: c.text for ref, c in iter_cells(span.text, p)}
        out[rnum] = (attrs, cells)
    return out


def _outside_sheetdata(sheet_xml: str) -> str:
    s, e, p = sheet_data_bounds(sheet_xml)
    return sheet_xml[:s].replace(f"<{p}sheetData>", "") + "\u0000" + sheet_xml[e:].replace(f"</{p}sheetData>", "")


def package_level(original: Path, filled: Path, sheet_part: str, mapped: set[str], report: PreservationReport) -> None:
    with zipfile.ZipFile(original) as zo, zipfile.ZipFile(filled) as zf:
        names_o, names_f = zo.namelist(), zf.namelist()
        report.add("Same internal parts (no part added or removed)", names_o == names_f,
                   f"{len(names_o)} parts in template, {len(names_f)} in filled copy")

        identical, differing = 0, []
        for n in names_o:
            if n in (sheet_part, "xl/workbook.xml") or n not in names_f:
                continue
            if zo.read(n) == zf.read(n):
                identical += 1
            else:
                differing.append(n)
        report.add("All unrelated parts byte-identical (styles, images, drawings, shared strings, printer settings, other sheets, theme, metadata)",
                   not differing, f"{identical} parts identical" + (f"; DIFFERENT: {differing}" if differing else ""))

        wo, wf = zo.read("xl/workbook.xml").decode(), zf.read("xl/workbook.xml").decode()
        same_wb = _normalise_workbook_xml(wo) == _normalise_workbook_xml(wf)
        report.add("workbook.xml identical apart from the recalculate-on-open flag (sheet order, defined names, print areas)", same_wb)
        if wo != wf:
            report.allowed_changes_seen.append('workbook.xml: fullCalcOnLoad="1" set (Excel recalculates on open)')

        so, sf = zo.read(sheet_part).decode(), zf.read(sheet_part).decode()
        report.add("Worksheet settings outside the cell grid byte-identical (merged cells, conditional formatting, data validation, page setup, margins, header/footer, column widths, drawing link)",
                   _outside_sheetdata(so) == _outside_sheetdata(sf))

        rows_o = _rows(so)
        rows_f = _rows(sf)
        problems, spans_changed, cells_checked = [], [], 0
        for rnum, (attrs_o, cells_o) in rows_o.items():
            if rnum not in rows_f:
                problems.append(f"row {rnum} removed")
                continue
            attrs_f, cells_f = rows_f[rnum]
            a_o = {k: v for k, v in attrs_o.items() if k != "spans"}
            a_f = {k: v for k, v in attrs_f.items() if k != "spans"}
            if a_o != a_f:
                problems.append(f"row {rnum} attributes changed (height/style/hidden)")
            if attrs_o.get("spans") != attrs_f.get("spans"):
                spans_changed.append(rnum)
            for ref, xml_o in cells_o.items():
                cells_checked += 1
                if ref in mapped:
                    s_o = dict(_attrs(xml_o[: xml_o.find(">") + 1])).get("s")
                    s_f = dict(_attrs(cells_f.get(ref, "<c>")[: cells_f.get(ref, "<c>").find(">") + 1])).get("s")
                    if s_o != s_f:
                        problems.append(f"{ref} style changed")
                elif cells_f.get(ref) != xml_o:
                    problems.append(f"{ref} changed but is not mapped")
            for ref in cells_f:
                if ref not in cells_o and ref not in mapped:
                    problems.append(f"{ref} added but is not mapped")
        for rnum, (_, cells_f) in rows_f.items():
            if rnum not in rows_o and any(ref not in mapped for ref in cells_f):
                problems.append(f"row {rnum} added with unmapped cells")
        report.add("Only mapped cells changed; every mapped cell kept its formatting style",
                   not problems, f"{cells_checked} template cells checked" + (f"; PROBLEMS: {problems[:10]}" if problems else ""))
        if spans_changed:
            report.allowed_changes_seen.append(f"row spans hint widened on rows {spans_changed}")


# ----------------------------------------------------------- semantic level --
def _style_sig(cell) -> tuple:
    return (repr(cell.font), repr(cell.fill), repr(cell.border), repr(cell.alignment),
            cell.number_format, repr(cell.protection))


def semantic_level(original: Path, filled: Path, sheet_name: str, mapped: set[str], report: PreservationReport) -> None:
    import openpyxl  # independent reader, used only for checking

    wo = openpyxl.load_workbook(original, rich_text=False)
    wf = openpyxl.load_workbook(filled, rich_text=False)
    report.add("Sheet names and order unchanged", wo.sheetnames == wf.sheetnames, ", ".join(wo.sheetnames))

    dn_o = {k: v.attr_text for k, v in wo.defined_names.items()}
    dn_f = {k: v.attr_text for k, v in wf.defined_names.items()}
    report.add("Workbook defined names unchanged", dn_o == dn_f, f"{len(dn_o)} names: {sorted(dn_o)}")

    value_diffs, style_diffs, formula_count, cells = [], [], 0, 0
    sheet_diffs: list[str] = []
    for name in wo.sheetnames:
        so, sf = wo[name], wf[name]
        coords = {c.coordinate for row in so.iter_rows() for c in row} | {c.coordinate for row in sf.iter_rows() for c in row}
        for coord in sorted(coords):
            co, cf = so[coord], sf[coord]
            cells += 1
            if isinstance(co.value, str) and co.value.startswith("="):
                formula_count += 1
            is_mapped = name == sheet_name and coord in mapped
            if not is_mapped and co.value != cf.value:
                value_diffs.append(f"{name}!{coord}")
            if _style_sig(co) != _style_sig(cf):
                style_diffs.append(f"{name}!{coord}")

        def cmp(label, a, b):
            if a != b:
                sheet_diffs.append(f"{name}: {label}")

        cmp("merged cells", sorted(map(str, so.merged_cells.ranges)), sorted(map(str, sf.merged_cells.ranges)))
        cmp("conditional formatting",
            sorted((str(cf.sqref), repr([r.formula for r in cf.rules])) for cf in so.conditional_formatting),
            sorted((str(cf.sqref), repr([r.formula for r in cf.rules])) for cf in sf.conditional_formatting))
        cmp("data validation", [(str(d.sqref), d.type, d.formula1) for d in so.data_validations.dataValidation],
            [(str(d.sqref), d.type, d.formula1) for d in sf.data_validations.dataValidation])
        cmp("print area", so.print_area, sf.print_area)
        cmp("print titles", (so.print_title_rows, so.print_title_cols), (sf.print_title_rows, sf.print_title_cols))
        ps = lambda s: (s.page_setup.orientation, s.page_setup.paperSize, s.page_setup.fitToWidth,
                        s.page_setup.fitToHeight, s.page_setup.scale, s.sheet_properties.pageSetUpPr and s.sheet_properties.pageSetUpPr.fitToPage)
        cmp("page setup", ps(so), ps(sf))
        pm = lambda s: (s.page_margins.left, s.page_margins.right, s.page_margins.top, s.page_margins.bottom,
                        s.page_margins.header, s.page_margins.footer)
        cmp("page margins", pm(so), pm(sf))
        hf = lambda s: (s.oddHeader.center.text, s.oddHeader.left.text, s.oddHeader.right.text,
                        s.oddFooter.center.text, s.oddFooter.left.text, s.oddFooter.right.text)
        cmp("header/footer", hf(so), hf(sf))
        cmp("print options", (so.print_options.horizontalCentered, so.print_options.gridLines),
            (sf.print_options.horizontalCentered, sf.print_options.gridLines))
        cmp("images", len(so._images), len(sf._images))
        cmp("column widths", {k: v.width for k, v in so.column_dimensions.items()},
            {k: v.width for k, v in sf.column_dimensions.items()})
        cmp("row heights", {k: v.height for k, v in so.row_dimensions.items() if v.height},
            {k: v.height for k, v in sf.row_dimensions.items() if v.height})
        cmp("frozen panes", so.freeze_panes, sf.freeze_panes)
        cmp("sheet-level defined names", {k: v.attr_text for k, v in so.defined_names.items()},
            {k: v.attr_text for k, v in sf.defined_names.items()})

    report.add("All cell values and formulas unchanged outside mapped cells (all sheets)", not value_diffs,
               f"{cells} cells compared, {formula_count} formulas" + (f"; DIFFERENT: {value_diffs[:10]}" if value_diffs else ""))
    report.add("All cell formatting unchanged, including mapped cells (fonts, fills, borders, alignment, number formats, protection)",
               not style_diffs, f"{cells} cells compared" + (f"; DIFFERENT: {style_diffs[:10]}" if style_diffs else ""))
    report.add("Merged cells, conditional formatting, data validation, print area/titles, page setup, margins, header/footer, print options, images, column widths, row heights, frozen panes unchanged",
               not sheet_diffs, "; ".join(sheet_diffs) if sheet_diffs else f"checked on {len(wo.sheetnames)} sheets")


def compare(original: Path, filled: Path, sheet_name: str, sheet_part: str, mapped_cells) -> PreservationReport:
    report = PreservationReport()
    mapped = {m.upper().replace("$", "") for m in mapped_cells}
    package_level(Path(original), Path(filled), sheet_part, mapped, report)
    semantic_level(Path(original), Path(filled), sheet_name, mapped, report)
    return report
