# ProductionTools: Stage 2 Excel Export Test Kit

> **Status: FOR REVIEW ONLY. Do not run anything until you have reviewed this kit and
> explicitly approved it.**

## Purpose
This kit answers one question: **on your Mac, can Microsoft Excel turn a filled petty cash
top sheet into a PDF automatically, offline, without changing the spreadsheet?** If it can't,
the kit also tests the manual fallback, where you save the PDF from Excel yourself.

It uses **one fictional test file only**. That file is a copy of your master template filled
with the fictional Stage 1 envelope: Jordan Avery, The Lighthouse Keeper, LK-0042-PC001.

## What is in the kit

| File | What it is |
|---|---|
| `run_excel_export_test.command` | The automatic test. A short shell script (about 90 lines). |
| `scripts/export_with_excel.applescript` | The only part that talks to Excel: open the copy read-only, export one sheet to PDF, close without saving. |
| `scripts/pdf_check.js` | Reads the resulting PDF with macOS's built-in PDF library and checks its page count and expected text. Read-only. |
| `check_manual_pdf.command` | Checks a PDF you exported **manually** (fallback test). Read-only. |
| `test_files/FICTIONAL_LK-0042-PC001_TopSheet.xlsx` | The fictional filled top sheet. All 5 sheets and all formulas of your template are preserved; this was verified automatically. |
| `test_files/REFERENCE_cloud_preview_NOT_excel.pdf` | A watermarked preview from the cloud, made with LibreOffice, for visual comparison. Not Excel output. |
| `MANUAL_FALLBACK.md` | Step-by-step manual export instructions. |
| `CHECKLIST.md` | What to note down during the test (prompts seen, results). |

## Exactly what the automatic test does
When you eventually double-click `run_excel_export_test.command`, after you've approved it:

1. **Stays inside the kit folder.** It creates `work/` and `results/` there, and doesn't read or
   write anywhere else.
2. **Fingerprints the test file** (SHA-256, a code calculated from the file's contents), so it
   can later prove the file wasn't changed.
3. **Copies the test file** into `work/`. The copy is made without macOS's "downloaded from the
   internet" tag (`cp -X`), so Excel opens it normally rather than in "Protected View", which
   would block automation. This applies only to the copy of the fictional file.
4. **Checks the network status locally.** It reads the Mac's own routing table to note whether
   networking appears on or off. It sends nothing.
5. **Asks Excel, using AppleScript (Apple's built-in way for one app to control another), to:**
   - open the copy **read-only**;
   - select the sheet "PC Formulas (1)";
   - recalculate all formulas;
   - **save that sheet as a PDF** in `results/`. This is the simplest supported command, `save as active sheet ... PDF file format`;
   - **close the copy without saving**;
   - quit Excel **only if Excel wasn't already open**. If you had Excel open, your other
     workbooks are left alone.
6. **Checks the PDF** with macOS's built-in PDF library: is it 1 page, and does it contain
   "PETTY CASH SUMMARY", "Jordan Avery", "Hardware Barn", **331.52** (total), **68.48**
   (balance due) and **"1 of 1"** (page numbering)? Those numbers appear only if Excel itself
   recalculated your template's formulas.
7. **Re-fingerprints the test file** to prove it's unchanged.
8. **Writes a plain-text report** to `results/excel_export_result.txt`. It contains the date,
   the macOS and Excel version numbers, the network status, the result, how long it took, the
   PDF checks, and the fingerprint check. It contains no names, file paths from outside the
   kit, or personal data.

If the automatic export fails for any reason, the report says so and points you to the manual
fallback. Nothing else is needed.

## What it does NOT do
- It doesn't install anything, ask for an administrator password, or change system settings.
- It doesn't connect to the internet or any server, and it doesn't use OneDrive or any cloud
  conversion.
- It doesn't open, read or modify your real template, your real production files, or any
  other workbook.
- It doesn't run in the background, at login, or more than once.
- It doesn't send the results anywhere. You read them and decide what to share.

## Permissions it may ask for

| Prompt you may see | Why | Your choice / how to undo |
|---|---|---|
| **"Terminal" wants access to control "Microsoft Excel"** (macOS Automation) | AppleScript needs this to give Excel the export command. It allows controlling Excel only: no access to files, camera, microphone or other apps. | Click OK to allow, or Don't Allow to skip straight to the manual fallback. Undo any time: System Settings → Privacy & Security → Automation → Terminal → turn off Microsoft Excel. |
| **Excel: "Grant File Access"** for the kit folder (possible) | Excel for Mac is "sandboxed", which means macOS limits which folders it may open or save in. This is the main thing the test needs to find out. | Note it in the checklist, then Select/Grant. You can remove Excel's access later in System Settings → Privacy & Security → Files and Folders. |
| **"... cannot be opened because it is from an unidentified developer"** (Gatekeeper) | The scripts aren't signed with an Apple Developer certificate. | Right-click the `.command` file → Open → Open. That allows only this file. |

**Not requested:** administrator password, Full Disk Access, Accessibility, Screen Recording,
network access, or any background permission.

## Offline proof
For the strongest result, run it **twice**: once normally, and once with **Wi-Fi turned off**.
The report notes whether networking appeared off. If the PDF is created with networking off,
Excel's export is local.

Optionally, an outbound firewall such as LuLu (independent of ProductionTools) can watch Excel
during the test. macOS's built-in firewall only blocks incoming connections, so it can't show this.

## What we can and cannot verify in advance
- Verified in the cloud:
  - the test workbook keeps every sheet, formula, format and the "1 of 1" page numbering of
    your template (two independent checks);
  - your original template file is byte-for-byte identical to your upload;
  - the shell scripts pass a syntax check.
- **Not verifiable in the cloud:** the AppleScript and the PDF checker can only run on a Mac
  with Excel, and there is no Mac or Excel in the cloud environment. Excel's AppleScript
  commands differ slightly between versions, so the first run is a genuine test, which is why
  the manual fallback is included.
