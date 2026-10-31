# Manual fallback: export the PDF yourself (about 1 minute)

Use this if the automatic test fails, or to compare the two methods.

1. In Excel, close any other workbooks. This isn't strictly required here, but it avoids confusion.
2. Open `test_files/FICTIONAL_LK-0042-PC001_TopSheet.xlsx` from the kit folder.
   - If Excel shows **Protected View** or a security message, note it in the checklist. You
     don't need to Enable Editing to export a PDF.
3. Click the sheet tab **"PC Formulas (1)"**.
4. Choose **File → Save As…** (or File → Export…).
5. Set **File Format** to **PDF**.
6. If Excel offers a choice, select **"Best for printing"**. Do **not** choose "Best for
   electronic distribution and accessibility", which uses a Microsoft online service.
7. If Excel offers **Sheet** or **Workbook**, choose **Sheet**.
8. Save it in the kit's `results` folder as **`manual_export.pdf`**.
9. **Close the workbook without saving.** If the workbook is saved, its fingerprint changes and
   the check will report **FAILED**.
10. Double-click `check_manual_pdf.command` (after approval). It reports:
    - **PASSED:** 1 page, all expected text visible, workbook unchanged.
    - **PARTIAL:** the PDF is readable, but some checks differ.
    - **FAILED:** the PDF is missing or unreadable, or the workbook was changed.

    A PDF merely existing is never reported as success. The checks cover the visible output
    only, so please also look at the PDF yourself.
