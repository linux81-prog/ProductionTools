"""Generate the FICTIONAL Stage 1 test material.

Everything here is invented: businesses, people, addresses, phone numbers
(555 numbers), card digits and the production company. Output is
deterministic (fixed random seed) so tests are repeatable.

Creates in ``fixtures/``:
  receipts/01_hardware_barn_photo.jpg   crumpled thermal receipt, phone photo
                                          on a table, tilted, stored sideways
                                          with an iPhone-style rotation tag
  receipts/02_copper_kettle_scan.pdf     scanned paper receipt (image-only PDF)
                                          with a deliberate tax/total mismatch
  receipts/03_prop_depot_invoice.pdf     emailed invoice with a real text layer
  answer_keys.json                       the correct values for each receipt
  templates/bluebird_lane_topsheet.xlsx  fictional petty cash top-sheet template
  templates/bluebird_lane_topsheet.profile.yaml   its mapping profile
  envelope.yaml                          the envelope (crew member, float, etc.)

Run:  python tools/make_fixtures.py
"""

from __future__ import annotations

import io
import json
from decimal import Decimal
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SANS_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
rng = np.random.default_rng(2026)


# --------------------------------------------------------------- helpers --
def render_thermal(lines, width=600, size=24, pad=36, paper=(250, 248, 241), ink=(45, 45, 48)):
    """lines: list of (text, style) where style in {'c','l','r','big','lr'}; 'lr' text is 'left|right'."""
    f = ImageFont.truetype(MONO, size)
    fb = ImageFont.truetype(MONO_B, int(size * 1.55))
    lh = int(size * 1.45)
    height = pad * 2 + sum(int(lh * (1.6 if s == "big" else 1)) for _, s in lines)
    img = Image.new("RGB", (width, height), paper)
    d = ImageDraw.Draw(img)
    y = pad
    for text, style in lines:
        font = fb if style == "big" else f
        if style == "lr":
            left, right = text.split("|")
            d.text((pad, y), left, font=font, fill=ink)
            d.text((width - pad - d.textlength(right, font=font), y), right, font=font, fill=ink)
        else:
            w = d.textlength(text, font=font)
            x = {"l": pad, "r": width - pad - w}.get(style, (width - w) / 2)
            d.text((x, y), text, font=font, fill=ink)
        y += int(lh * (1.6 if style == "big" else 1))
    return img


def smooth_noise(h, w, scale, amp):
    small = rng.standard_normal((max(2, h // scale), max(2, w // scale))).astype("float32")
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC) * amp


def crumple(img: Image.Image, amp=3.5) -> Image.Image:
    a = np.asarray(img).astype("float32")
    h, w = a.shape[:2]
    dx = smooth_noise(h, w, 60, amp)
    dy = smooth_noise(h, w, 60, amp)
    mx, my = np.meshgrid(np.arange(w, dtype="float32"), np.arange(h, dtype="float32"))
    warped = cv2.remap(a, mx + dx, my + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    gy, gx = np.gradient(smooth_noise(h, w, 45, 30))
    shade = np.clip(1.0 + 0.012 * (gx - gy), 0.82, 1.06)[..., None]
    fade = (1.0 - 0.25 * np.clip(smooth_noise(h, w, 200, 1.0), 0, 1))[..., None]  # thermal fade patches
    out = 255 - (255 - warped) * fade
    out = np.clip(out * shade, 0, 255)
    return Image.fromarray(out.astype("uint8"))


def phone_photo(receipt: Image.Image) -> Image.Image:
    rw, rh = receipt.size
    W, H = int(rw * 1.9), int(rh * 1.35)
    # warm wooden-table background
    base = np.zeros((H, W, 3), "float32")
    grain = smooth_noise(H, W, 6, 12)[:, :1].repeat(W, axis=1) * 0 + smooth_noise(H, W, 8, 10)
    base[..., 0] = 120 + grain
    base[..., 1] = 82 + grain * 0.8
    base[..., 2] = 52 + grain * 0.6
    stripes = (np.sin(np.linspace(0, 40, W))[None, :] * 8).astype("float32")
    base += stripes[..., None]
    # paper placement with perspective tilt
    src = np.float32([[0, 0], [rw, 0], [rw, rh], [0, rh]])
    cx, cy = W / 2, H / 2
    dst = np.float32([[cx - rw * 0.47, cy - rh * 0.44], [cx + rw * 0.50, cy - rh * 0.415],
                      [cx + rw * 0.46, cy + rh * 0.45], [cx - rw * 0.52, cy + rh * 0.435]])
    m = cv2.getPerspectiveTransform(src, dst)
    paper = cv2.warpPerspective(np.asarray(receipt).astype("float32"), m, (W, H))
    mask = cv2.warpPerspective(np.ones((rh, rw), "float32"), m, (W, H))
    shadow = cv2.GaussianBlur(cv2.warpAffine(mask, np.float32([[1, 0, 14], [0, 1, 18]]), (W, H)), (0, 0), 18)
    base *= (1 - 0.45 * shadow)[..., None]
    out = base * (1 - mask[..., None]) + paper * mask[..., None]
    # uneven lighting, blur, sensor noise
    yy, xx = np.mgrid[0:H, 0:W]
    light = 1.05 - 0.25 * (((xx - W * 0.3) / W) ** 2 + ((yy - H * 0.25) / H) ** 2)
    out *= light[..., None]
    out = cv2.GaussianBlur(out, (0, 0), 0.9)
    out += rng.normal(0, 4.0, out.shape)
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"))


def scanned_page(receipt: Image.Image) -> Image.Image:
    dpi = 200
    W, H = int(8.5 * dpi), int(11 * dpi)
    page = Image.new("L", (W, H), 246)
    r = receipt.convert("L").rotate(1.3, resample=Image.BICUBIC, expand=True, fillcolor=246)
    page.paste(r, (int(W * 0.30), int(H * 0.08)))
    a = np.asarray(page).astype("float32")
    a += rng.normal(0, 5, a.shape)
    a = cv2.GaussianBlur(a, (0, 0), 0.7)
    a = np.clip((a - 18) * 1.08, 0, 255)  # scanner contrast
    return Image.fromarray(a.astype("uint8"))


# -------------------------------------------------------------- receipts --
def receipt_1():
    lines = [("HARDWARE BARN", "big"), ("1420 Fictional Ave", "c"), ("Burbank CA 91502", "c"),
             ("Tel (555) 010-4477", "c"), ("STORE #0217   REG 03", "c"), ("", "c"),
             ("10/14/2026|3:42 PM", "lr"), ("-" * 34, "c"),
             ("GAFFER TAPE 2IN BLK|", "lr"), ("  2 @ 21.49|42.98", "lr"),
             ("ZIP TIES 100PK|8.99", "lr"), ("WORK GLOVES L|12.49", "lr"),
             ("SASH CORD 50FT|9.79", "lr"), ("-" * 34, "c"),
             ("SUBTOTAL|74.25", "lr"), ("SALES TAX 9.5%|7.05", "lr"), ("TOTAL|$81.30", "lr"),
             ("", "c"), ("CASH|100.00", "lr"), ("CHANGE|18.70", "lr"), ("ITEMS SOLD 5|", "lr"),
             ("", "c"), ("THANK YOU FOR SHOPPING", "c"), ("RETURNS WITHIN 30 DAYS", "c")]
    rec = crumple(render_thermal(lines))
    photo = phone_photo(rec)
    stored = photo.rotate(90, expand=True)  # stored sideways, like many phone photos
    exif = Image.Exif()
    exif[0x0112] = 6                          # "rotate 90° clockwise to display"
    path = FIX / "receipts" / "01_hardware_barn_photo.jpg"
    stored.save(path, "JPEG", quality=84, exif=exif)
    return path.name, {"vendor": "Hardware Barn", "date": "2026-10-14", "subtotal": "74.25",
                       "tax": "7.05", "total": "81.30", "payment": "Cash"}


def receipt_2():
    lines = [("COPPER KETTLE CAFE", "big"), ("88 Placeholder Blvd", "c"), ("Glendale CA 91203", "c"),
             ("(555) 013-2290", "c"), ("", "c"), ("Order #4471   Server: SAM", "c"),
             ("10/15/26|08:12", "lr"), ("-" * 34, "c"),
             ("DRIP COFFEE BOX x2|48.00", "lr"), ("ASSORTED PASTRY DOZ|32.50", "lr"),
             ("OAT MILK QT|5.75", "lr"), ("-" * 34, "c"),
             ("SUBTOTAL|86.25", "lr"), ("TAX|8.19", "lr"), ("TOTAL|94.94", "lr"), ("", "c"),
             ("CASH TENDERED|100.00", "lr"), ("CHANGE|5.06", "lr"), ("", "c"), ("THANK YOU!", "c")]
    rec = render_thermal(lines, width=560, size=23, paper=(255, 255, 255), ink=(25, 25, 25))
    page = scanned_page(rec)
    buf = io.BytesIO()
    page.save(buf, "JPEG", quality=80)
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    path = FIX / "receipts" / "02_copper_kettle_scan.pdf"
    c = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1)
    c.drawImage(ImageReader(io.BytesIO(buf.getvalue())), 0, 0, 612, 792)
    c.showPage()
    c.save()
    return path.name, {"vendor": "Copper Kettle Cafe", "date": "2026-10-15", "subtotal": "86.25",
                       "tax": "8.19", "total": "94.94", "payment": "Cash"}


def receipt_3():
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen import canvas
    path = FIX / "receipts" / "03_prop_depot_invoice.pdf"
    c = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1)
    c.setTitle("Invoice PD-20931 (fictional)")
    c.setFillColor(HexColor("#1F3A5F"))
    c.setFont("Helvetica-Bold", 20)
    c.drawString(54, 730, "PROP DEPOT SUPPLY CO.")
    c.setFont("Helvetica", 9.5)
    c.setFillColor(HexColor("#333333"))
    for i, t in enumerate(["2201 Example Street, Suite 4", "Van Nuys, CA 91406", "(555) 019-8810  |  orders@propdepot.example"]):
        c.drawString(54, 712 - i * 13, t)
    c.setFont("Helvetica-Bold", 26)
    c.setFillColor(HexColor("#9AA5B1"))
    c.drawRightString(558, 726, "INVOICE")
    c.setFillColor(HexColor("#222222"))
    c.setFont("Helvetica", 10)
    meta = [("Invoice #", "PD-20931"), ("Invoice Date", "October 16, 2026"), ("Due Date", "November 15, 2026"),
            ("Payment", "Visa ending 0000")]
    for i, (k, v) in enumerate(meta):
        c.drawRightString(470, 690 - i * 15, k + ":")
        c.drawRightString(558, 690 - i * 15, v)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(54, 640, "Bill To")
    c.setFont("Helvetica", 10)
    for i, t in enumerate(["Jordan Avery (fictional)", "The Lighthouse Keeper - Art Dept", "Production #LK-0042"]):
        c.drawString(54, 626 - i * 13, t)
    y = 560
    c.setFillColor(HexColor("#1F3A5F"))
    c.rect(54, y - 4, 504, 18, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y + 1, "Description")
    c.drawRightString(400, y + 1, "Qty")
    c.drawRightString(470, y + 1, "Unit")
    c.drawRightString(552, y + 1, "Amount")
    c.setFillColor(HexColor("#222222"))
    c.setFont("Helvetica", 10)
    items = [("Antique brass ship lantern (prop)", "1", "64.00", "64.00"), ("Weathered manila rope coil, 25 ft", "1", "18.50", "18.50")]
    for i, (dsc, q, u, a) in enumerate(items):
        yy = y - 22 - i * 18
        c.drawString(60, yy, dsc)
        c.drawRightString(400, yy, q)
        c.drawRightString(470, yy, u)
        c.drawRightString(552, yy, a)
    c.line(54, y - 66, 558, y - 66)
    totals = [("Subtotal", "82.50"), ("Shipping", "9.95"), ("Sales Tax (9.5%)", "7.84"), ("Total", "100.29"),
              ("Amount Paid", "100.29"), ("Balance Due", "0.00")]
    for i, (k, v) in enumerate(totals):
        yy = y - 86 - i * 16
        c.setFont("Helvetica-Bold" if k == "Total" else "Helvetica", 10.5 if k == "Total" else 10)
        c.drawRightString(470, yy, k)
        c.drawRightString(552, yy, "$" + v)
    c.setFont("Helvetica-Oblique", 8.5)
    c.setFillColor(HexColor("#666666"))
    c.drawString(54, 120, "Thank you for your order. All businesses, names and numbers on this invoice are fictional.")
    c.showPage()
    c.save()
    return path.name, {"vendor": "Prop Depot Supply Co.", "date": "2026-10-16", "subtotal": "82.50",
                       "tax": "7.84", "total": "100.29", "payment": "Visa"}


# -------------------------------------------------------------- template --
ACCOUNT_CODES = [
    ("2410", "Art Dept - Expendables"), ("2420", "Art Dept - Purchases"), ("2510", "Props - Purchases"),
    ("2520", "Props - Rentals"), ("2610", "Set Dressing - Purchases"), ("3510", "Craft Service"),
    ("3520", "Catering / Meals"), ("4110", "Transportation - Fuel"), ("4120", "Parking"),
    ("5110", "Office Supplies"), ("5120", "Shipping & Postage"), ("9990", "Miscellaneous"),
]


def make_logo(path: Path):
    img = Image.new("RGBA", (360, 120), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 10, 106, 110), fill=(44, 104, 168, 255))
    d.polygon([(40, 60), (90, 40), (75, 70)], fill=(255, 255, 255, 255))
    d.text((120, 24), "BLUEBIRD", font=ImageFont.truetype(SANS_B, 34), fill=(30, 50, 80, 255))
    d.text((122, 66), "LANE PRODUCTIONS", font=ImageFont.truetype(SANS, 19), fill=(30, 50, 80, 255))
    img.save(path)


def make_template(path: Path):
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.formatting.rule import CellIsRule, FormulaRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.workbook.defined_name import DefinedName
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Top Sheet"
    codes = wb.create_sheet("Account Codes")
    codes["A1"], codes["B1"] = "Code", "Description (PLACEHOLDER - not a real chart of accounts)"
    for i, (k, v) in enumerate(ACCOUNT_CODES, start=2):
        codes[f"A{i}"], codes[f"B{i}"] = k, v
    codes.column_dimensions["A"].width = 10
    codes.column_dimensions["B"].width = 58
    codes["A1"].font = codes["B1"].font = Font(bold=True)

    thin = Side(style="thin", color="7F8C9A")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    under = Border(bottom=Side(style="thin", color="1F3A5F"))
    hdr_fill = PatternFill("solid", fgColor="1F3A5F")
    label = Font(name="Calibri", size=10, bold=True, color="1F3A5F")
    money = '"$"#,##0.00_);[Red]("$"#,##0.00)'

    for col, w in zip("ABCDEFG", [12, 11, 22, 31, 11, 21, 12]):
        ws.column_dimensions[col].width = w
    ws.row_dimensions[1].height = 34
    ws.row_dimensions[2].height = 20

    ws.merge_cells("C1:G1")
    ws["C1"] = "PETTY CASH TOP SHEET"
    ws["C1"].font = Font(name="Calibri", size=18, bold=True, color="1F3A5F")
    ws["C1"].alignment = Alignment(horizontal="right", vertical="center")
    ws.merge_cells("C2:G2")
    ws["C2"] = "Bluebird Lane Productions (fictional company)"
    ws["C2"].font = Font(name="Calibri", size=10, italic=True, color="555555")
    ws["C2"].alignment = Alignment(horizontal="right")
    logo_path = path.parent / "bluebird_logo.png"
    make_logo(logo_path)
    logo = XLImage(str(logo_path))
    logo.width, logo.height = 180, 60
    ws.add_image(logo, "A1")

    header = [(4, "Production:", "B4:D4", "Prod #:", "F4:G4"), (5, "Name:", "B5:D5", "Envelope #:", "F5:G5"),
              (6, "Dept:", "B6:D6", "Position:", "F6:G6")]
    for r, l1, m1, l2, m2 in header:
        ws[f"A{r}"] = l1
        ws[f"A{r}"].font = label
        ws.merge_cells(m1)
        ws[f"E{r}"] = l2
        ws[f"E{r}"].font = label
        ws.merge_cells(m2)
        for c in "BCD":
            ws[f"{c}{r}"].border = under
        for c in "FG":
            ws[f"{c}{r}"].border = under
    ws["A7"], ws["C7"], ws["E7"] = "Period:", "To:", "Float Issued:"
    for a in ("A7", "C7", "E7"):
        ws[a].font = label
    ws["C7"].alignment = Alignment(horizontal="right")
    ws["B7"].number_format = ws["D7"].number_format = "mm/dd/yyyy"
    ws["B7"].border = ws["D7"].border = under
    ws.merge_cells("F7:G7")
    ws["F7"].number_format = money
    ws["F7"].border = ws["G7"].border = under

    heads = ["No.", "Date", "Vendor", "Description", "Acct", "Acct Description", "Amount"]
    for col, h in zip("ABCDEFG", heads):
        cell = ws[f"{col}9"]
        cell.value = h
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = hdr_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = box
    first, last = 10, 24
    for r in range(first, last + 1):
        for col in "ABCDEFG":
            ws[f"{col}{r}"].border = box
            ws[f"{col}{r}"].font = Font(name="Calibri", size=10)
        ws[f"A{r}"].alignment = Alignment(horizontal="center")
        ws[f"C{r}"].alignment = ws[f"D{r}"].alignment = Alignment(shrink_to_fit=True)
        ws[f"B{r}"].number_format = "mm/dd/yy"
        ws[f"G{r}"].number_format = money
        ws[f"F{r}"] = f'=IF(E{r}="","",IFERROR(VLOOKUP(E{r},AccountCodes,2,FALSE),"CODE NOT FOUND"))'
        ws[f"F{r}"].font = Font(name="Calibri", size=9, color="555555")
        if r % 2 == 0:
            for col in "ABCDEFG":
                ws[f"{col}{r}"].fill = PatternFill("solid", fgColor="F2F5F9")

    dv = DataValidation(type="list", formula1="AccountCodes_List", allow_blank=True)
    dv.add(f"E{first}:E{last}")
    ws.add_data_validation(dv)
    ws.conditional_formatting.add(f"G{first}:G{last}", CellIsRule(operator="greaterThan", formula=["250"],
                                  fill=PatternFill("solid", fgColor="F8D7DA")))
    ws.conditional_formatting.add(f"F{first}:F{last}", FormulaRule(formula=[f'F{first}="CODE NOT FOUND"'],
                                  font=Font(color="C00000", bold=True)))

    summary = [(25, "Total Receipts", f"=SUM(G{first}:G{last})"), (26, "Float Issued", "=F7"),
               (27, "Expected Cash Return", "=G26-G25"), (28, "Cash Returned", None), (29, "Over / (Short)", "=G28-G27")]
    for r, text, formula in summary:
        ws[f"F{r}"] = text
        ws[f"F{r}"].font = label
        ws[f"F{r}"].alignment = Alignment(horizontal="right")
        if formula:
            ws[f"G{r}"] = formula
        ws[f"G{r}"].number_format = money
        ws[f"G{r}"].border = box
    ws["G25"].font = Font(bold=True)
    ws.conditional_formatting.add("G29", CellIsRule(operator="lessThan", formula=["0"],
                                  fill=PatternFill("solid", fgColor="F8D7DA"), font=Font(color="C00000", bold=True)))
    ws["A26"], ws["A27"] = "Receipts:", "Crew-reported total:"
    ws["A26"].font = ws["A27"].font = label
    ws["C26"] = f"=COUNT(G{first}:G{last})"
    ws["C27"].number_format = money
    ws["C27"].border = under

    ws["A31"], ws["D31"], ws["F31"] = "Submitted by:", "Approved by (Production Accountant):", "Date:"
    for a in ("A31", "D31", "F31"):
        ws[a].font = Font(size=9, color="555555")
    for c in "ABC":
        ws[f"{c}32"].border = under
    ws["D32"].border = ws["E32"].border = under
    ws["G32"].border = under
    ws["A34"] = "All names and figures in this template are fictional test data."
    ws["A34"].font = Font(size=8, italic=True, color="888888")

    wb.defined_names["AccountCodes"] = DefinedName("AccountCodes", attr_text="'Account Codes'!$A$2:$B$13")
    wb.defined_names["AccountCodes_List"] = DefinedName("AccountCodes_List", attr_text="'Account Codes'!$A$2:$A$13")
    wb.defined_names["TotalSpent"] = DefinedName("TotalSpent", attr_text="'Top Sheet'!$G$25")

    ws.print_area = "A1:G34"
    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.5
    ws.page_margins.top, ws.page_margins.bottom = 0.6, 0.6
    ws.print_options.horizontalCentered = True
    ws.oddHeader.center.text = "Bluebird Lane Productions - CONFIDENTIAL"
    ws.oddHeader.center.size = 9
    ws.oddFooter.left.text = "&F"
    ws.oddFooter.right.text = "Page &P of &N"
    ws.freeze_panes = "A10"
    wb.save(path)
    logo_path.unlink()


PROFILE = """\
# Template profile: tells ProductionTools which cell holds what.
# A new company's top sheet needs only a new profile like this one - no code changes.
name: Bluebird Lane Productions - Petty Cash Top Sheet (fictional)
profile_version: 1
template_file: bluebird_lane_topsheet.xlsx
sheet: Top Sheet

header:            # envelope field -> cell (top-left cell of a merged block)
  production: B4
  production_number: F4
  crew_member: B5
  envelope_number: F5
  department: B6
  position: F6
  period_start: B7
  period_end: D7
  float_amount: F7
  cash_returned: G28
  reported_total: C27

line_items:
  first_row: 10
  max_rows: 15
  columns:         # receipt field -> column
    number: A
    date: B
    vendor: C
    description: D
    account_code: E
    amount: G
  # Column F holds the template's own VLOOKUP formula and is deliberately not mapped.

overflow: refuse   # Stage 1: more receipts than rows -> stop and ask. (Continuation sheets: later stage.)
"""

ENVELOPE = """\
# FICTIONAL petty cash envelope used for the Stage 1 demo.
envelope_number: PC001
production: The Lighthouse Keeper
production_number: LK-0042
company: Bluebird Lane Productions
crew_member: Jordan Avery
department: Art
position: Art Department Coordinator
period_start: 2026-10-12
period_end: 2026-10-18
float_amount: "300.00"
reported_total: "276.53"   # what the crew member wrote on the envelope
cash_returned: "21.47"     # cash handed back (deliberately $2.00 short for the demo)
per_receipt_limit: "250.00"
receipts:
  - 01_hardware_barn_photo.jpg
  - 02_copper_kettle_scan.pdf
  - 03_prop_depot_invoice.pdf
"""


def main():
    (FIX / "receipts").mkdir(parents=True, exist_ok=True)
    (FIX / "templates").mkdir(parents=True, exist_ok=True)
    keys = dict([receipt_1(), receipt_2(), receipt_3()])
    (FIX / "answer_keys.json").write_text(json.dumps(keys, indent=2) + "\n")
    make_template(FIX / "templates" / "bluebird_lane_topsheet.xlsx")
    (FIX / "templates" / "bluebird_lane_topsheet.profile.yaml").write_text(PROFILE)
    (FIX / "envelope.yaml").write_text(ENVELOPE)
    acc = "# PLACEHOLDER account codes for testing - not a real chart of accounts.\n" + "".join(
        f'"{k}": "{v}"\n' for k, v in ACCOUNT_CODES)
    (FIX / "account_codes.yaml").write_text(acc)
    total = sum(Decimal(v["total"]) for v in keys.values())
    print(f"Fixtures written to {FIX}  (receipts total {total})")


if __name__ == "__main__":
    main()
