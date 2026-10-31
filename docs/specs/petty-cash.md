# Specification: Petty Cash Module (required functionality)

Standing rules apply throughout:
- fictional data during development
- offline only
- original documents are never modified
- a person verifies before anything counts
- nothing is ever marked approved or verified automatically

## 1. Top sheets supplied by the user (no fixed layout)
- The user uploads **their own blank Excel petty cash top sheet**. Different production
  companies use different formats. No layout created by the software is required. (The
  fictional "Bluebird Lane" template is a development fixture only.)
- Each template gets a **saved mapping profile** that says which field goes in which cell:
  - header cells (employee, phone, job name and number, category/department, float…)
  - the line-item rows and columns
  - the value type a cell needs, for example `number` for line numbers that the
    template's own formulas depend on
  - the receipt-number style (`index` → 1, 2, 3 or `full` → PC001-001)
- **Profiles are saved once they're approved** and reused for future envelopes.
  Stage 1 profiles are YAML files; the browser interface will add a visual mapping screen.
- The app **fills a copy and never touches the original**. Only mapped cells change.
  Formatting, formulas, merged cells, hidden columns and print layout are preserved, and
  this is verified automatically every time (the copy is rejected if the check fails).
- Cells that contain formulas are never written. For example, the master template's
  "Envelope No" cell is a formula, so it's left alone.
- **The final top-sheet PDF is made by Microsoft Excel on the Mac** (Stage 2), with the
  agreed manual Excel export as the fallback.
- The first real profile is for the user's master template:
  `fixtures/templates/master_pc/PC_Sheet_Template.profile.yaml`.
  - Rows 8–42 of the first sheet hold 35 receipts.
  - Continuation onto sheets 2–4 comes later; for now more than 35 receipts stops with
    a clear message.
  - Open questions for the user: what "Category" means, and whether the envelope ID
    should appear anywhere on the sheet.

## 2. Receipt annotations (default output)
- **Only** circles around the vendor name, the transaction date and the final total.
- A small, unobtrusive receipt number. It matches what the top sheet's receipt-number
  column shows (for example `#3`).
- **Nothing else is added:**
  - no VENDOR/DATE/TOTAL labels
  - no footer and no added margin
  - no account codes, descriptions or signatures
  - no claim that anyone verified the receipt
  - the page size is unchanged
- Account codes and descriptions belong on the top sheet, after the user's review.
- **No duplicate marks.** A field that already appears to be circled (coloured pen around
  it) is not circled again, and a number already on the receipt is not added again. Each
  skip is listed in the audit log and the reconciliation report.
- The system never invents a reviewer's name or states that something was verified unless
  a person actually did it. (The Stage 1 demo uses a file labelled as a *simulated* review.)
- Review previews (dashed circles = not yet confirmed) are an internal review aid, not
  a deliverable.

## 3. Two workflows

### Mode A: Create a petty cash envelope (what Stage 1 does)
The user provides receipts, photos or invoices, a blank top-sheet template, and the
production and envelope details. The app then:
1. extracts the receipt information
2. shows it to the user to verify
3. numbers and annotates the receipts where needed
4. fills a copy of the supplied top sheet
5. reconciles the envelope totals
6. produces the individual receipt PDFs, the completed top sheet and the combined PDF

### Mode B: Verify an existing petty cash envelope (planned)
The user provides a **completed** top sheet (Excel or PDF) plus the supporting receipts,
either as separate files or one combined PDF. The app then:
1. reads the completed top sheet. Excel sheets are read through the same mapping profile
   used for filling, in reverse. PDF sheets are read from their built-in text, or with OCR
   if they're scans.
2. lists the transactions and totals it found
3. splits a combined receipt PDF into individual receipts, which the user can adjust, and
   matches each top-sheet line to a receipt by number, amount, date and vendor
4. checks dates, vendors, amounts and account coding where available
5. finds missing receipts, duplicates, wrong amounts, receipts not listed on the sheet, and
   unexplained differences
6. recalculates the receipts total, float balance and cash return
7. flags discrepancies, uncertain matches and documentation problems for a person to review
8. produces a **verification report** with **PASS / WARNING / ERROR** findings

Rules for Mode B:
- **No new top sheet** is created by default.
- **Nothing is modified or renumbered.** Existing annotations stay exactly as submitted.
- The envelope is **never automatically marked approved or verified**.
- Corrections or annotations are made only when the user explicitly asks, and always on
  copies, saved as new versions.
- Submitted documents are never silently overwritten or altered. They're stored as
  fingerprinted, read-only originals.
