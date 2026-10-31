"""Job line lists: the budget line numbers for a particular job, with descriptions.

Loaded once per job (CSV, Excel or YAML). When a receipt is given a line number,
its ACCOUNT description is filled in automatically from this list. The purchase
description stays a separate field entered by a person. Line numbers that are not on the job's list are flagged.

Accepted formats (first two columns are used; a header row is optional):
  CSV / XLSX:  Line, Description
  YAML:        "2410": "Art Dept - Expendables"
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import yaml


def _code(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if re.fullmatch(r"\d+\.0+", s):  # Excel stores 2410 as 2410.0
        s = s.split(".")[0]
    return s or None


def _rows_to_dict(rows) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        if not row or len(row) < 2:
            continue
        code, desc = _code(row[0]), (str(row[1]).strip() if row[1] is not None else "")
        if not code or not desc or not re.search(r"\d", code):  # skips header rows like "Line, Description"
            continue
        if code in out and out[code] != desc:
            raise ValueError(f"Line {code} appears twice with different descriptions")
        out[code] = desc
    return out


def load_line_list(path: Path) -> dict[str, str]:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as fh:
            return _rows_to_dict(csv.reader(fh))
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        return _rows_to_dict(wb.worksheets[0].iter_rows(values_only=True))
    if ext in (".yaml", ".yml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return {_code(k): str(v) for k, v in data.items()}
    raise ValueError(f"Unsupported line list format: {path.name}")


def fill_account_descriptions(receipts, lines: dict[str, str], audit=None) -> None:
    """Fill each receipt's ACCOUNT description from its budget line number.

    The purchase description (what was bought and why) is a separate field that only a
    person enters; it is never invented or overwritten here.
    """
    for r in receipts:
        code = _code(r.account_code)
        if code and code in lines:
            r.account_description = lines[code]
            if audit:
                audit.record("account_description_from_line_list", receipt=r.source_name, line=code,
                             account_description=r.account_description)
