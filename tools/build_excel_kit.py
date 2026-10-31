"""Package excel_test_kit/ as a zip for review (cloud-side build step; runs nothing on a Mac).

Writes MANIFEST.txt (SHA-256 of every kit file) into the kit, then builds
packages/ProductionTools-Excel-Test-Kit-rev2.zip with the folder structure:

  ProductionTools-Excel-Test-Kit/
    README.md  MANUAL_FALLBACK.md  CHECKLIST.md  MANIFEST.txt
    run_excel_export_test.command  check_manual_pdf.command      (marked executable)
    scripts/export_with_excel.applescript  scripts/pdf_check.js
    test_files/FICTIONAL_LK-0042-PC001_TopSheet.xlsx (+ .sha256)
    test_files/REFERENCE_cloud_preview_NOT_excel.pdf
"""

import hashlib
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "excel_test_kit"
OUT = ROOT / "packages" / "ProductionTools-Excel-Test-Kit-rev2.zip"
TOP = "ProductionTools-Excel-Test-Kit"
SKIP_DIRS = {"work", "results", "__pycache__"}


def kit_files():
    return sorted(p for p in KIT.rglob("*") if p.is_file() and not (set(p.relative_to(KIT).parts) & SKIP_DIRS)
                  and p.name != "MANIFEST.txt" and not p.name.startswith("."))


def main():
    lines = ["ProductionTools Excel Test Kit - revision 2 - file fingerprints (SHA-256)",
             "Verify on a Mac with:  shasum -a 256 <file>", ""]
    for p in kit_files():
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(KIT).as_posix()}")
    (KIT / "MANIFEST.txt").write_text("\n".join(lines) + "\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in kit_files() + [KIT / "MANIFEST.txt"]:
            rel = p.relative_to(KIT).as_posix()
            info = zipfile.ZipInfo(f"{TOP}/{rel}", date_time=(2026, 11, 1, 0, 0, 0))
            mode = 0o755 if p.suffix == ".command" else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
