# Specification: PO Management Module (roadmap items 2–5)

> Status: **specified, not implemented.** The model here (actual costs plus optional
> projections) is the authoritative accounting model. An earlier draft based on
> "commitment accounting", where a PO automatically counted as an outstanding
> commitment, was **superseded and does not apply**.

The PO Log, PO Top Sheet Generator and PO Accounting Package Generator are one
integrated module. They share the master transaction log and connect to Petty
Cash, Reconciliation and Budget Conversion.

All the standing rules apply:
- offline only
- fictional data during development
- originals are never modified
- a person verifies before anything counts
- nothing is ever sent automatically

---

## 1. Master PO Log (independent of Showbiz or HotBudget)

ProductionTools keeps its own master transaction log. Showbiz and HotBudget
outputs are produced from it through separate export mappings. The log is never
restricted to either program's layout.

**Transaction fields**
- PO number, vendor, invoice number, date, description
- **Budget-line splits:** one or more `{budget line, amount}` entries whose sum must
  equal the transaction total
- **Cost class:** `ACTUAL` or `PROJECTION`
- **Payment status:** `PAID` or `UNPAID`. This is separate from the cost class.
- **Payment type and label:** a type (INV, CC, CHK, ACH, TMC) plus a label such as
  `AE 4201`, `VISA 1234`, `CASH`, `CHECK` or `ACH`. Labels hold at most the last 4
  digits. **Full card or bank account numbers are never stored.**
- Petty cash envelope (for petty cash entries)
- Supporting documents (links to stored originals)
- Status, reconciliation links, and the export history

**Rules for actual costs and projections**
1. Every invoice entered is an **ACTUAL** cost, whether it has been paid or not.
2. Every credit-card purchase entered with a receipt is an **ACTUAL** cost.
3. PAID/UNPAID never changes whether something is an actual cost.
4. **PROJECTIONS** are optional. They are created only when the user asks to record
   an estimated cost for which no invoice exists yet.
5. A PO number on its own **never** creates an outstanding commitment.
6. When an invoice arrives for an existing projection, the two are linked and
   reconciled so the cost is counted only once.
7. If a projection still has money left after partial invoicing, the user must
   explicitly approve keeping that remainder. Otherwise it is closed.
8. One PO can have several invoices and several budget-line splits, with no
   double-counting.
9. Actual costs and projections are reported and exported separately.

**Entry workflow** (invoices and credit-card receipts)
1. Upload the document. The original is copied and fingerprinted.
2. The app extracts the vendor, date, total, invoice number and description, with
   confidence scores.
3. **The user verifies and corrects every field.**
4. The app asks which budget line or lines the cost belongs to.
5. For a credit card: the entry is recorded as ACTUAL + PAID with the payment label
   (for example `AE 4201`).
6. The original document stays attached as backup.
7. Possible duplicates are flagged (same file fingerprint; vendor + invoice number;
   vendor + date + amount). Later: matching against imported card statements.

**Duplicates and re-exports**
- Posting the same transaction twice, or importing the same document twice, is
  **blocked or flagged for a person**.
- Exporting again is **allowed**. Every export is recorded as an **export batch**
  (batch ID, date, target, the transactions included, a revision number). The user can
  regenerate or re-export a batch, or add a transaction to a new batch. Each time,
  the app shows whether a transaction was already exported (which batch and revision)
  and records the re-export in the audit log.

---

## 2. Showbiz Actuals CSV export (reference format)

This is a **Showbiz-specific export**, not the structure of the master log.

- **Exactly 10 columns, in this order:**
  `Line, ID, TYPE, PAY ID, Date, PONUM, PCENV, Vendor, Description, Total`
- **TYPE values:** `INV` = invoice, `CC` = credit card, `CHK` = check,
  `ACH` = ACH / wire (never "EFT"), `TMC` = timecard.
- The **TYPE KEY** shown in columns N–O of the reference workbook is reference
  information only and is **never exported**.
- **Only ACTUAL costs** are exported. Projections are never included.
- **Petty cash:** each approved petty cash expense becomes one line, with its envelope
  in `PCENV`. TYPE and PONUM may be blank, as in the reference. Each line keeps its own
  budget line, vendor, date, description and total. Multiple envelopes are supported.
- The date format, number format and blank-field conventions must match the reference
  workbook exactly.
- **Compatibility counts as confirmed only after a real Showbiz import test.**
- Reference file: `Showbiz Actuals.xlsx` from the user. *It is not yet in the cloud
  environment; a blank or fictional copy is needed before this export is built.*

**HotBudget** will get its own separate transfer mapping, defined later from a
reference file.

---

## 3. PO Top Sheet Generator

Takes an invoice, a W-9 and a supplied PO top-sheet template, and produces a filled
**copy** of the template. It starts with one master template; other companies'
templates are added through mapping profiles, using the same surgical filling and
preservation check as the petty cash top sheet.

**CRITICAL**
- **Banking details, account numbers, routing numbers and ACH payment information
  are never placed on the top sheet.** Templates accept only fields on an approved
  list, and the central sensitive-data guard blocks anything that looks like a bank
  number.
- Only the approved vendor fields are taken from W-9s: legal name, business name,
  address and entity type.
- **Tax identification numbers are never kept in general database records.** If a
  template ever genuinely needs one, the user must explicitly approve it each time.
- The template's formatting and formulas are preserved (automatic check).
- **The user verifies everything before finalizing.**

---

## 4. PO Accounting Package Generator

Produces one combined PDF, **in this order:**
1. the completed PO top sheet
2. the invoice
3. the W-9
4. the ACH payment document

- It checks that all four are present and refuses to finish, with a clear message,
  if one is missing.
- It applies consistent file naming (format to be agreed, e.g.
  `PO-<number>_<vendor>_<invoice#>_Package.pdf`).
- **W-9 and ACH documents are highly sensitive:**
  - They are handled locally only and stored in a separate restricted folder.
  - ACH documents are never text-extracted.
  - Their contents never appear in general records, logs, exported metadata or file
    names. Logs say only, for example, "ACH document attached to PO-0007".
  - The originals are preserved.
- **The finished package contains those sensitive documents and is treated as
  sensitive itself.** It is saved to the restricted outputs area, with no metadata
  derived from their contents.
- **The app never submits or emails packages.** The user reviews and sends them.

---

## 5. Links to other modules
- **Petty Cash** feeds approved, verified expenses into the master log as actual
  costs (PCENV = envelope number) and from there into the Showbiz export.
- **Reconciliation** matches card statements, the PO log, receipts and refunds
  against the master log.
- **Budget Conversion** supplies the list of budget lines and receives the
  transfer workbooks.
