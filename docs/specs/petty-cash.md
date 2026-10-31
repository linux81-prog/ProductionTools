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
  - "Category" holds the crew member's department (confirmed).
  - "Envelope No" holds the **unique envelope ID**. It replaces the template's "1 of N"
    formula in the filled copy only. The replacement is approved explicitly in the profile
    (`replace_formula: true`) and recorded in the preservation report. All other formula
    cells stay protected.

## 1b. Unique envelope IDs
- Default format: `{production number}-{envelope number}`, e.g. `LK-0042-PC001`. A custom
  ID or format can be set per envelope.
- Each ID is recorded in an append-only registry, a list in the project folder that is only
  ever added to. Re-running the same envelope reuses its ID. A *different* envelope that tries
  to use an existing ID is refused with a clear message.

## 1c. Job line lists (preloaded line numbers)
- Each job can have a **line list**: budget line numbers with their descriptions, loaded
  once from CSV, Excel or YAML. The first two columns are used: line number, description.
- When a receipt is given a line number, its **description is filled in automatically**
  from the job's line list, unless the reviewer typed their own description, which always
  wins. The reconciliation report notes each auto-filled description so it can be reviewed.
- Line numbers not on the job's list are flagged as errors. Conflicting duplicate entries
  in a list are rejected when it's loaded.
- The line list is stored with the project's originals: fingerprinted and read-only.
- Later: the browser app will offer the job's line numbers as a pick-list, and Budget
  Conversion / the PO module will share the same list.

## 1d. Handwritten tips and gratuities
Each receipt keeps three separate amounts:
- **printed total**: the total printed before any tip
- **tip**
- **final amount paid**

The **expense amount** used everywhere else is the confirmed final amount.

| Situation on the receipt | What the app does |
|---|---|
| Suggested gratuity lines (percentages, "tip guide") | Ignored. They are **never** assumed to have been paid (noted as INFO). |
| Tip/gratuity printed *above* the printed total | Already included in the total, so **never added again**. |
| Tip and final total both written | Checks that printed total + tip = final total. Any difference → WARNING, and the amounts must be confirmed. |
| Tip written, final total blank | **Proposes** printed total + tip as the final amount. Nothing is used until the user confirms it, and the confirmation is logged. |
| Final total written, no readable tip | Works out the implied tip (final − printed) and flags it for confirmation. |
| Nothing written | The expense amount is the printed total. |

- **Handwritten amounts are never silently accepted.** Any amount in the tip/final area is
  capped below the review threshold, so a person must always confirm it.
- **Manual correction:** the user can correct the tip, the final total or the printed total.
  The expense amount is then recalculated and logged. The user can also enter a tip that
  couldn't be read.
- **Card or cash tip:** a tip written on a card slip is treated as part of the card charge
  and is reimbursed once, never added again. "CASH TIP" text, or a bill paid in cash, means
  a cash tip. If it's unclear, the app asks (WARNING) so the reimbursement is right.
- **Mode A (Create):** the confirmed final amount goes onto the top sheet.
- **Mode B (Verify):** the top sheet's amount is compared with the receipt's confirmed final
  amount, including any tip. A top sheet showing the printed total when a tip was paid, or the
  other way round, is flagged.
- **Annotations:** the confirmed final total is circled when it appears on the receipt. If the
  final total is blank, the printed total and the tip are circled instead. No labels and no
  calculations are ever written on the receipt.
- **Testing limits:** Stage 1 uses *simulated* handwriting (a font drawn with random tilt,
  size and slant in blue ink). Real handwriting varies far more, so accuracy on real receipts
  will be lower than the test figures. That's why every handwritten amount requires confirmation.

## 2. Receipt annotations (default output)
- **Only** circles around the vendor name, the transaction date and the final total (the
  confirmed final amount paid, including any tip, when it appears on the receipt).
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
