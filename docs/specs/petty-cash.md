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
  - "Envelope No" holds the **unique envelope ID**. This is the single, explicitly approved
    exception to the rule against changing formulas. It replaces the "1 of N" formula on
    sheet 1 of the filled copy only.
  - Before replacing, the app checks that the cell still holds exactly
    `=CONCATENATE("1 of ",V2)`. If it doesn't (a different template or a wrong cell), it
    refuses and writes nothing.
  - The page-numbering machinery is checked on every fill and must be unchanged: the
    envelope-count formula in V2 and the "2 of N", "3 of N" and "4 of N" labels on the
    continuation sheets. Only sheet 1's own "1 of N" label is replaced by the ID.
  - Every other formula cell stays protected.

## 1b. Unique envelope IDs
- Default format: `{production number}-{envelope number}`, e.g. `LK-0042-PC001`. A custom
  ID or format can be set per envelope.
- Each ID is recorded in an append-only registry, a list in the project folder that is only
  ever added to. Re-running the same envelope reuses its ID. A *different* envelope that tries
  to use an existing ID is refused with a clear message.

## 1c. Job line lists: budget-line (account) descriptions
- Each job can have a **line list**: budget line numbers with their account descriptions,
  loaded once from CSV, Excel or YAML. The first two columns are used.
- When a line number is chosen, the **account description fills in automatically**, for
  example 2410 → "Art Dept - Expendables".
- The **purchase description** (what was bought and why) is a **separate field**. Only a
  person enters it. It is **never invented and never overwritten** by the line list.
  - On the master template, "For What" holds the purchase description.
  - Templates with an account-description column can map `account_description`.
  - A missing purchase description is flagged as a WARNING.
- Line numbers that aren't on the job's list are flagged as errors. Conflicting duplicate
  entries are rejected when the list is loaded. The list is stored with the project's
  originals: fingerprinted and read-only.

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

## 1e. Production petty cash rules: payment method, who paid, eligibility, cash

**The production's rules decide eligibility.** Payment method, who paid and reimbursement
are recorded as separate facts. Each job has a rules file, e.g.
`fixtures/jobs/LK-0042_petty_cash_rules.yaml`, with these settings:
- `payment_policy` is one of:
  - `cash_only`: no card purchases of any kind, including personal cards
  - `cash_and_approved_personal_cards`: cash, plus personal card expenses approved one by one
  - `case_by_case`: non-cash only with approval **and** an authorization reference
- `production_cards`: identifiers of the production company cards (the last 4 digits are matched)
- If no rules file is given, the strictest policy (`cash_only`) applies.

**Rules that apply on every job:**
- **Production company card purchases are never eligible.** They're never on the top sheet,
  in the envelope totals, in the float calculation or in crew reimbursement.
  - The receipt is kept and documented as excluded, with the reason. It's marked for credit
    card reconciliation / the PO Log, so it's counted once, there.
  - Once a reviewer acknowledges the exclusion, it no longer blocks an otherwise correct
    envelope from being finalized.
- **An unidentified card is never assumed to be personal.** An unknown payment method or card
  owner blocks finalizing until the user identifies it.
- **Nothing is reimbursed automatically.** A personal card expense needs explicit approval on a
  permitting job, and is still flagged for sign-off after approval. On a cash-only job it's
  ineligible.
- **Tips follow the same rules.** A cash tip on a production-card bill is never included
  automatically. It needs explicit confirmation that it's eligible, **plus** a reference to
  where it's independently documented. Who paid a cash tip is never assumed.

**Outcome for each payment part:** eligible, review required (not counted, and blocks
finalizing), or ineligible (excluded; blocks finalizing until acknowledged). A receipt with
no eligible amount is left out of the envelope: it isn't numbered and isn't on the top
sheet, but it's listed in the report.

**Money is tracked in separate buckets:**

| Bucket | Meaning |
|---|---|
| Eligible expenses | the top sheet total |
| Float disbursements | eligible money that actually left the float: cash, or a personal expense *explicitly recorded* as reimbursed from the float |
| Personal reimbursement owed | approved personal expenses not paid back from the float |
| Held for review | not counted until resolved |
| Ineligible: production card, and Ineligible: job policy | documented, never counted |

- **Cash expected back = float − float disbursements.** A personal card expense never reduces
  the cash expected back unless reimbursement from the float was recorded.
- The master template's own "Balance due" formula shows the net figure (float − eligible
  expenses). The report shows the physical cash and the reimbursement owed separately.

**In both modes:**
- **Create:** ineligible or pending items never reach the generated top sheet or the envelope
  calculations.
- **Verify:** prohibited card expenses on a completed envelope are reported as
  **policy violations**, and the submitted envelope is never modified. The shared policy check
  is built and tested; the Verify screens come in Stage 5.

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

## 4. Implementation status (as of this update)

**Implemented and covered by automated tests (Stage 1, run from a script in the cloud with fictional data):**

| Feature | Where |
|---|---|
| Never-overwrite originals (copied, fingerprinted, read-only), versioned outputs, audit log | `core/filestore.py`, `core/versioning.py`, `core/audit.py` |
| App-level network lock | `core/netguard.py` |
| Reading photos (straightening, offline OCR), scanned PDFs and text PDFs | `petty_cash/extract.py` |
| Vendor / date / subtotal / tax / printed total / payment (last 4 digits) with confidence scores | `petty_cash/parse.py` |
| Handwritten tips: suggested gratuity ignored, proposed / mismatch / implied cases, card vs cash tip, recalculation after correction | `petty_cash/parse.py`, `review.py`, `recon.py` |
| Production petty cash rules (cash only / approved personal cards / case by case), production-card exclusion, unknown-payment blocking, cash tips on production-card bills | `petty_cash/policy.py` |
| Separate buckets: eligible, float disbursements, personal reimbursement owed, held, ineligible; cash expected back from float disbursements only | `petty_cash/payments.py`, `recon.py` |
| Verify-mode policy check on a completed envelope (logic only; no screens), proven not to modify its inputs | `policy.check_completed_envelope` |
| Simplified annotations (circles + small number), duplicate-mark detection, annotated/clean outputs | `petty_cash/annotate.py` |
| User-supplied templates through mapping profiles, typed cells, surgical filling, two-method preservation check | `core/xlsx_fill.py`, `core/xlsx_integrity.py`, `petty_cash/mapping.py` |
| Master template profile, guarded Envelope No replacement, protected page-numbering formulas | `fixtures/templates/master_pc/` |
| Job line lists → account descriptions (purchase description kept separate) | `petty_cash/line_list.py` |
| Unique envelope IDs with a project registry | `petty_cash/envelope_ids.py` |
| Reconciliation report (PDF and Excel), combined PDFs with bookmarks | `petty_cash/recon.py`, `pdf_out.py` |
| Review decisions applied from a file (a stand-in for the review screen) | `petty_cash/review.py` |

**Planned (not built yet):**

| Feature | Stage |
|---|---|
| Excel export of the top-sheet PDF on the Mac, with manual fallback (the cloud uses a watermarked preview) | 2 |
| Browser app: Create/Verify choice, import, review screen, annotation editor, template upload, pick-lists for line numbers and who paid | 3 |
| Visual template-mapping screen; continuation sheets for more than 35 receipts | 4 |
| **Mode B — Verify an existing envelope**: screens, reading completed sheets, splitting combined PDFs, matching, PASS/WARNING/ERROR report (the policy check it will use is already built) | 5 |
| Sending excluded production-card receipts to credit card reconciliation / the PO Log | later modules |
| Locked numbering and revisions, full duplicate detection across envelopes, backups, network-activity page | 6 |
| Testing on real handwriting, plus user guide and local trial on the Mac | 7 |
