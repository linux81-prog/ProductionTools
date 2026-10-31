"""Workbook preservation: only mapped cells may change; everything else must survive."""

import re
import shutil
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from conftest import PROFILE, TEMPLATE
from productiontools.core import xlsx_integrity
from productiontools.core.filestore import OverwriteRefusedError, sha256_file
from productiontools.core.xlsx_fill import TemplateMappingError, fill_template_copy, set_full_calc_on_load

VALUES = {"B4": "The Lighthouse Keeper", "F5": "PC001", "B7": date(2026, 10, 12), "F7": Decimal("300.00"),
          "A10": "PC001-001", "C10": "Hardware Barn & Co <test>", "G10": Decimal("81.30"), "G28": Decimal("21.47")}


def _rewrite_part(src, dest, part, fn):
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == part:
                data = fn(data.decode()).encode()
            zout.writestr(info, data)


def test_fill_passes_every_preservation_check(tmp_path, template_copy):
    before = sha256_file(template_copy)
    out = tmp_path / "filled.xlsx"
    info = fill_template_copy(template_copy, out, "Top Sheet", VALUES)
    rep = xlsx_integrity.compare(template_copy, out, "Top Sheet", info["sheet_part"], VALUES)
    assert rep.passed, [c for c in rep.checks if not c.passed]
    assert len(rep.checks) >= 10
    assert sha256_file(template_copy) == before  # template never modified


def test_values_and_formulas_after_fill(tmp_path, template_copy):
    import openpyxl
    out = tmp_path / "filled.xlsx"
    fill_template_copy(template_copy, out, "Top Sheet", VALUES)
    ws = openpyxl.load_workbook(out)["Top Sheet"]
    assert ws["C10"].value == "Hardware Barn & Co <test>"   # special characters escaped safely
    assert ws["G10"].value == 81.3
    assert ws["B7"].value.date() == date(2026, 10, 12)       # stored as a real Excel date
    assert ws["B7"].number_format == "mm/dd/yyyy"            # kept the template's date format
    assert ws["G25"].value == "=SUM(G10:G24)"                # template formula intact
    assert ws["F10"].value.startswith("=IF(E10")


def test_recalculate_flag_added_when_template_lacks_it(tmp_path, template_copy):
    """Real Excel templates usually lack fullCalcOnLoad; the only allowed workbook.xml change is adding it."""
    plain = tmp_path / "plain.xlsx"
    _rewrite_part(template_copy, plain, "xl/workbook.xml", lambda x: re.sub(r'\s*fullCalcOnLoad="1"', "", x))
    assert b"fullCalcOnLoad" not in zipfile.ZipFile(plain).read("xl/workbook.xml")
    out = tmp_path / "filled.xlsx"
    info = fill_template_copy(plain, out, "Top Sheet", VALUES)
    assert b'fullCalcOnLoad="1"' in zipfile.ZipFile(out).read("xl/workbook.xml")
    rep = xlsx_integrity.compare(plain, out, "Top Sheet", info["sheet_part"], VALUES)
    assert rep.passed
    assert any("fullCalcOnLoad" in a for a in rep.allowed_changes_seen)


def test_calcpr_inserted_when_missing_entirely():
    xml = '<workbook xmlns="x"><sheets><sheet name="A"/></sheets><definedNames><definedName name="n">1</definedName></definedNames></workbook>'
    out = set_full_calc_on_load(xml)
    assert '</definedNames><calcPr fullCalcOnLoad="1"/></workbook>' in out


def test_refuses_to_overwrite_formula_cell(tmp_path, template_copy):
    with pytest.raises(TemplateMappingError, match="formula"):
        fill_template_copy(template_copy, tmp_path / "x.xlsx", "Top Sheet", {"G25": 1})


def test_refuses_non_anchor_merged_cell(tmp_path, template_copy):
    with pytest.raises(TemplateMappingError, match="merged"):
        fill_template_copy(template_copy, tmp_path / "x.xlsx", "Top Sheet", {"C4": "x"})


def test_refuses_existing_destination_and_template_as_destination(tmp_path, template_copy):
    out = tmp_path / "x.xlsx"
    out.write_bytes(b"existing")
    with pytest.raises(OverwriteRefusedError):
        fill_template_copy(template_copy, out, "Top Sheet", VALUES)
    with pytest.raises(OverwriteRefusedError):
        fill_template_copy(template_copy, template_copy, "Top Sheet", VALUES)


def test_writes_cells_that_do_not_exist_yet(tmp_path, template_copy):
    import openpyxl
    out = tmp_path / "x.xlsx"
    info = fill_template_copy(template_copy, out, "Top Sheet", {"K40": "new", "J10": 5})
    assert openpyxl.load_workbook(out)["Top Sheet"]["K40"].value == "new"
    assert xlsx_integrity.compare(template_copy, out, "Top Sheet", info["sheet_part"], ["K40", "J10"]).passed


def test_checker_catches_an_unmapped_change(tmp_path, template_copy):
    out = tmp_path / "filled.xlsx"
    info = fill_template_copy(template_copy, out, "Top Sheet", VALUES)
    tampered = tmp_path / "tampered.xlsx"
    _rewrite_part(out, tampered, info["sheet_part"], lambda x: x.replace("SUM(G10:G24)", "SUM(G10:G20)"))
    rep = xlsx_integrity.compare(template_copy, tampered, "Top Sheet", info["sheet_part"], VALUES)
    assert not rep.passed


def test_checker_catches_a_dropped_image(tmp_path, template_copy):
    out = tmp_path / "filled.xlsx"
    info = fill_template_copy(template_copy, out, "Top Sheet", VALUES)
    media = [n for n in zipfile.ZipFile(out).namelist() if n.startswith("xl/media/")]
    assert media, "fixture template should contain a logo image"
    broken = tmp_path / "broken.xlsx"
    _rewrite_part(out, broken, "xl/workbook.xml", lambda x: x)
    with zipfile.ZipFile(out) as zin, zipfile.ZipFile(broken, "w") as zout:
        for i in zin.infolist():
            zout.writestr(i, b"" if i.filename == media[0] else zin.read(i.filename))
    assert not xlsx_integrity.compare(template_copy, broken, "Top Sheet", info["sheet_part"], VALUES).passed


def test_profile_loads_and_matches_template():
    from productiontools.petty_cash.mapping import load_profile
    p = load_profile(PROFILE)
    assert p.template_file == TEMPLATE and p.sheet == "Top Sheet"
    assert "F" not in p.columns.values()  # formula column deliberately unmapped


def test_master_template_preserved(tmp_path):
    """User-supplied template (Google-Sheets-exported, array formulas, hidden helper columns, 5 sheets)."""
    from conftest import FIX
    master = FIX / "templates" / "master_pc" / "PC_Sheet_Template.xlsx"
    values = {"A3": "Jordan Avery", "E3": 5550102020, "A8": date(2026, 10, 14), "B8": 1, "C8": "Hardware Barn",
              "D8": "Gaffer tape", "E8": Decimal("81.30"), "F8": 2410, "E48": Decimal("300.00")}
    out = tmp_path / "filled.xlsx"
    info = fill_template_copy(master, out, "PC Formulas (1)", values)
    rep = xlsx_integrity.compare(master, out, "PC Formulas (1)", info["sheet_part"], values)
    assert rep.passed, [c for c in rep.checks if not c.passed]
    assert any("fullCalcOnLoad" in a for a in rep.allowed_changes_seen)   # template had an empty <calcPr/>
    with pytest.raises(TemplateMappingError, match="formula"):  # not approved in this call -> refused
        fill_template_copy(master, tmp_path / "x.xlsx", "PC Formulas (1)", {"S3": "PC001"})
    approved = tmp_path / "approved.xlsx"
    info2 = fill_template_copy(master, approved, "PC Formulas (1)", {**values, "S3": "LK-0042-PC001"}, replace_formulas=["S3"])
    assert info2["formulas_replaced"] == ["S3"]
    assert xlsx_integrity.compare(master, approved, "PC Formulas (1)", info2["sheet_part"], {**values, "S3": 1}).passed
