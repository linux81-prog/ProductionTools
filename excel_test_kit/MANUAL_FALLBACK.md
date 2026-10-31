# Manual fallback: export the PDF yourself (about 1 minute)

Use this if the automatic test fails, or simply to compare the two methods.

1. In the kit folder, open `test_files/FICTIONAL_LK-0042-PC001_TopSheet.xlsx` in Microsoft Excel.
   If Excel offers to **Enable Editing**, you don't need to; viewing is enough.
2. Click the sheet tab **"PC Formulas (1)"**.
3. Choose **File → Save As…** (or File → Export…).
4. Set **File Format** to **PDF**.
5. If Excel shows a choice, select **"Best for printing"**. Do **not** choose "Best for
   electronic distribution and accessibility", which uses a Microsoft online service.
6. If Excel offers **Sheet** vs **Workbook**, choose **Sheet**.
7. Save it in the kit's `results` folder as **`manual_export.pdf`**.
8. **Close the workbook without saving** if Excel asks about changes.
9. Double-click `check_manual_pdf.command`, after approval. It checks the PDF and adds the
   result to `results/excel_export_result.txt`.

Nothing in these steps changes the test workbook or your real template.
