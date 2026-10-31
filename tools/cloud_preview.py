"""CLOUD-ONLY top-sheet preview. NOT part of the ProductionTools app.

There is no Microsoft Excel in the cloud development environment, so for the
Stage 1 demonstration the filled .xlsx is converted to a PDF with LibreOffice
(installed only in the cloud dev container) and stamped
"CLOUD PREVIEW - NOT EXCEL OUTPUT". On the user's Mac, Excel produces this
PDF instead (Stage 2), with a manual Excel export as the fallback.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

LABEL = "cloud preview (LibreOffice in the dev container; NOT Excel output, not part of the app)"


def available() -> bool:
    return shutil.which("soffice") is not None


def _copy_first_sheet_only(xlsx: Path, dest: Path) -> None:
    """Hide every sheet except the first in a throwaway copy, so only the top sheet prints."""
    import re
    import zipfile

    with zipfile.ZipFile(xlsx) as zin, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "xl/workbook.xml":
                xml = data.decode("utf-8")
                tags = re.findall(r"<sheet\b[^>]*/>", xml)
                for tag in tags[1:]:
                    hidden = re.sub(r'\s*state="[^"]*"', "", tag)[:-2].rstrip() + ' state="hidden"/>'
                    xml = xml.replace(tag, hidden, 1)
                data = xml.encode("utf-8")
            zout.writestr(info, data)


def preview_pdf(xlsx: Path) -> bytes | None:
    if not available():
        return None
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.colors import Color
    from reportlab.pdfgen import canvas

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / xlsx.name
        _copy_first_sheet_only(xlsx, src)  # throwaway copy; mimics Excel's "save active sheet as PDF"
        subprocess.run(["soffice", f"-env:UserInstallation=file://{tmp}/profile", "--headless",
                        "--convert-to", "pdf", "--outdir", str(tmp), str(src)],
                       check=True, capture_output=True, timeout=180)
        pdf = (tmp / xlsx.name).with_suffix(".pdf").read_bytes()

    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    for page in reader.pages:
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.setFillColor(Color(0.85, 0.1, 0.1, alpha=0.13))
        c.setFont("Helvetica-Bold", 40)
        c.translate(w / 2, h / 2)
        c.rotate(35)
        c.drawCentredString(0, 10, "CLOUD PREVIEW")
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(0, -24, "NOT EXCEL OUTPUT")
        c.showPage()
        c.save()
        page.merge_page(PdfReader(io.BytesIO(buf.getvalue())).pages[0])
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
