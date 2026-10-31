# ProductionTools: Stage 2 Excel Export Test Kit (revision 2)

> **Status: FOR REVIEW ONLY. Do not run anything until you have reviewed this kit and
> explicitly approved it.**

Revision 2 makes six corrections requested by an independent review:
1. The test won't target the wrong workbook.
2. A changed fingerprint (a code calculated from the file's contents) always means FAILED.
3. The manual check now gives PASSED, PARTIAL or FAILED.
4. macOS's "downloaded file" information is no longer removed.
5. The network check is described as informational only.
6. The PDF checks are described as checks of the visible output only.

## Purpose
This kit answers one question: **can Microsoft Excel on your Mac export a filled petty cash
top sheet to PDF automatically, without changing the spreadsheet?** If it can't, the kit also
tests the manual fallback, where you save the PDF from Excel yourself.

It uses **one fictional test file only**: a copy of your master template filled with the
fictional Stage 1 envelope (Jordan Avery, The Lighthouse Keeper, LK-0042-PC001).

## What is in the kit

| File | What it is |
|---|---|
| `run_excel_export_test.command` | The automatic test (a short shell script). |
| `scripts/export_with_excel.applescript` | The only part that talks to Excel. It checks the workbook's identity, exports one sheet to PDF, and closes without saving. |
| `scripts/pdf_check.js` | Reads the resulting PDF with macOS's built-in PDF library and reports what is visible in it. Read-only. |
| `check_manual_pdf.command` | Checks a PDF you exported **manually** (the fallback). Read-only. |
| `test_files/FICTIONAL_LK-0042-PC001_TopSheet.xlsx` | The fictional filled top sheet. All 5 sheets and all formulas of your template are preserved, including the "1 of N" page numbering; this was verified in the cloud. |
| `test_files/FICTIONAL_LK-0042-PC001_TopSheet.xlsx.sha256` | Its published fingerprint. Both checks compare against this. |
| `test_files/REFERENCE_cloud_preview_NOT_excel.pdf` | A watermarked preview from the cloud (made with LibreOffice), for visual comparison only. It is not Excel output. |
| `MANUAL_FALLBACK.md` | Step-by-step manual export instructions. |
| `CHECKLIST.md` | What to note down during the test. |
| `MANIFEST.txt` | The fingerprint of every file in the kit, so you or a reviewer can confirm nothing was altered after review. |

## Exactly what the automatic test does
When you eventually double-click `run_excel_export_test.command`, after you have approved it:

1. **Stays inside the kit folder.** It creates `work/` and `results/` there, and doesn't read
   or write anywhere else.
2. **Checks the test workbook against its published fingerprint.** If they don't match, it
   stops with **FAILED** before doing anything else.
3. **Makes a plain copy** of the test workbook in `work/`, under a unique name such as
   `PTtest_20261101-101500.xlsx`. macOS's "downloaded from the internet" information is
   **kept** on the copy; nothing is bypassed. The report notes whether that flag is present.
   If it causes Protected View or a security prompt that blocks the export, the test
   reports it rather than working around it.
4. **Notes the network route.** It reads the Mac's own routing table (nothing is sent) and
   records whether a default route exists. **This is informational only; it is not proof that
   the test ran offline.** You will test offline operation yourself by disabling internet
   connectivity.
5. **Asks Excel, through AppleScript** (Apple's built-in way for one app to control another), to
   do the following. **Workbook-identity safeguards come first:**
   - **Refuse to start if any workbook is already open in Excel.** You will be asked to close
     all workbooks first, so an unrelated workbook can never be the target.
   - Open the uniquely named copy **read-only**.
   - **Confirm what was opened.** Exactly one workbook must be open, its name must be the
     unique test name, and its full path must match the copy's exact path. If any of these
     can't be confirmed, it **refuses to export and touches nothing**. It never falls back to
     "whichever workbook happens to be active".
   - Select the sheet "PC Formulas (1)" of that confirmed workbook and check that the sheet
     really was selected.
   - Ask Excel to recalculate, then **export that sheet as a PDF** in `results/`, using the
     simplest supported command (`save as <sheet> … PDF file format`).
   - **Close the confirmed workbook without saving.**
   - Quit Excel **only if Excel wasn't already open** and no workbooks remain.
6. **Checks the visible output of the PDF** with macOS's built-in PDF library. It looks for:
   1 page, plus "PETTY CASH SUMMARY", "Jordan Avery", "Hardware Barn", 331.52 (total), 68.48
   (balance due) and "1 of 1" (page numbering). **This verifies the visible output only; it is
   not conclusive proof that Excel recalculated every formula.** Please also look at the PDF
   yourself.
7. **Re-checks the test workbook's fingerprint.** **If it changed, the result is FAILED, even if
   a PDF was produced.**
8. **Writes a plain-text report** to `results/excel_export_result.txt`. It includes the date,
   the macOS and Excel version numbers, the network-route note, the download-flag note, what
   Excel said, the duration, the visible-output checks, the fingerprint checks and one result
   line. It contains no names, file paths from outside the kit, or personal data.

**Possible results:**
- **PASSED:** a PDF was exported automatically, all visible-output checks matched, and the
  workbook is unchanged.
- **PARTIAL:** a PDF was made, but some visible checks didn't match.
- **FAILED:** no usable PDF, a safety refusal, or a changed fingerprint. You can then try the
  manual fallback.

## What it does NOT do
- It doesn't install anything, ask for an administrator password, or change system settings.
- It doesn't remove macOS security information or bypass security prompts.
- It doesn't connect to the internet or any server, and it doesn't use OneDrive or any cloud
  conversion.
- It doesn't open, read or modify your real template, your real production files, or any
  other workbook. It refuses to run while another workbook is open.
- It doesn't run in the background, at login, or more than once.
- It doesn't send the results anywhere. You read them and decide what to share.

## Permissions it may ask for

| Prompt you may see | Why | Your choice / how to undo |
|---|---|---|
| **"Terminal" wants access to control "Microsoft Excel"** (macOS Automation) | AppleScript needs this to give Excel commands. It allows controlling Excel only: no access to files, camera, microphone or other apps. | Allow it to run the automatic test, or choose Don't Allow and use only the manual fallback. Undo any time: System Settings → Privacy & Security → Automation → Terminal → turn off Microsoft Excel. |
| **Excel: "Grant File Access"** for the kit folder (possible) | Excel for Mac is sandboxed, which means macOS limits which folders it may open or save in. Whether this appears is one of the things the test finds out. | Note it in the checklist, then decide. You can remove access later: System Settings → Privacy & Security → Files and Folders. |
| **Excel: Protected View / security message** (possible) | The kit came from a download, so macOS may mark its files as downloaded. | Note it in the checklist. The test doesn't bypass it. If it blocks the export, the report says so. |
| **"…cannot be opened because it is from an unidentified developer"** (Gatekeeper) | The scripts aren't signed with an Apple Developer certificate. | Right-click the `.command` file → Open → Open. That allows only this file. |

**Not requested:** administrator password, Full Disk Access, Accessibility, Screen Recording,
network access, or any background permission.

## Testing offline
The network-route line in the report is **informational only**. To test offline operation,
disable internet connectivity yourself (Wi-Fi off, Ethernet unplugged), then run the test.
Optionally, an outbound firewall such as LuLu can watch Excel during the test. macOS's
built-in firewall only blocks incoming connections, so it can't show this.

## What was and wasn't verified in advance
- Verified in the cloud:
  - the test workbook keeps every sheet, formula, format and the "1 of N" page numbering of
    your template (two independent checks);
  - your template is byte-for-byte identical to your upload;
  - both shell scripts pass a syntax check;
  - with stand-in commands replacing Excel and macOS tools, the scripts produce the right
    result in every case: PASSED, PARTIAL, a safety refusal, an Excel error, a missing PDF,
    and a changed fingerprint (FAILED even when a PDF exists).
- **Not verifiable in the cloud:** the AppleScript and the PDF checker run only on a Mac with
  Excel, and there is no Mac or Excel in the cloud environment. Excel's AppleScript commands
  differ slightly between versions, so the first run is a genuine test. That's why the manual
  fallback is included.
