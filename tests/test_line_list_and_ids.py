from datetime import date
from decimal import Decimal

import pytest

from conftest import FIX
from productiontools.core.audit import AuditLog
from productiontools.petty_cash.envelope_ids import DuplicateEnvelopeIdError, make_envelope_id, register
from productiontools.petty_cash.line_list import fill_descriptions, load_line_list
from productiontools.petty_cash.models import Envelope, Receipt


def test_line_list_formats(tmp_path):
    csv_lines = load_line_list(FIX / "jobs" / "LK-0042_line_list.csv")
    assert csv_lines["2410"] == "Art Dept - Expendables" and len(csv_lines) == 12
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Line #", "Description"])
    ws.append([2410, "Art Dept - Expendables"])
    ws.append([3510.0, "Craft Service"])
    wb.save(tmp_path / "lines.xlsx")
    assert load_line_list(tmp_path / "lines.xlsx") == {"2410": "Art Dept - Expendables", "3510": "Craft Service"}
    assert load_line_list(FIX / "account_codes.yaml")["5110"] == "Office Supplies"


def test_conflicting_duplicate_line_is_rejected(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("2410,Art A\n2410,Art B\n")
    with pytest.raises(ValueError):
        load_line_list(p)


def test_description_filled_only_when_blank(tmp_path):
    a, b, c = (Receipt(n, None, n, []) for n in "abc")
    a.account_code, b.account_code, c.account_code = "2410", "3510", "7777"
    b.description = "Typed by reviewer"
    fill_descriptions([a, b, c], {"2410": "Art Dept - Expendables", "3510": "Craft Service"}, AuditLog(tmp_path / "log"))
    assert (a.description, a.description_source) == ("Art Dept - Expendables", "job line list")
    assert b.description == "Typed by reviewer"
    assert c.description is None  # unknown line: left blank and flagged by reconciliation


def _env(crew="Jordan Avery", num="PC001"):
    e = Envelope(num, "Prod", "LK-0042", "Co", crew, "Art", "Coord", date(2026, 10, 1), date(2026, 10, 7),
                 Decimal("300"), Decimal("0"), Decimal("0"))
    e.envelope_id = make_envelope_id(e)
    return e


def test_envelope_ids_unique_per_project(tmp_path):
    e = _env()
    assert e.envelope_id == "LK-0042-PC001"
    register(tmp_path, e)
    register(tmp_path, _env())  # same envelope re-run: fine
    with pytest.raises(DuplicateEnvelopeIdError):
        register(tmp_path, _env(crew="Someone Else"))
    register(tmp_path, _env(num="PC002"))
