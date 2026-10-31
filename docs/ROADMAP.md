# ProductionTools: Long-Term Roadmap

ProductionTools is a private production-management app for film and commercial
producers. It runs in your web browser, but everything happens on your own Mac.

## Rules that apply to every module
- **Offline.** No cloud AI, no outside services, and no production data leaves the Mac.
- **Originals are never modified.** Every imported document is copied, fingerprinted
  (a unique code calculated from its contents) and made read-only. Outputs are
  saved as new, numbered versions.
- **A person checks before anything counts.** Uncertain readings, money
  discrepancies and sensitive paperwork all need a person to verify them.
- **Development uses only fictional data in the cloud.** Nothing is installed or
  run on the user's Mac without their approval.
- **Modular design.** A shared core handles projects, the file store, the audit log,
  templates, PDFs and the network lock. Each feature plugs into it as a separate module.

## Priority order

| # | Module | Status |
|---|--------|--------|
| 1 | Petty Cash Automation | **In progress (Stage 1)** |
| 2 | PO Log Management | Specified: [specs/po-management.md](specs/po-management.md) |
| 3 | PO Top Sheet Generator | Specified (part of PO Management) |
| 4 | PO Accounting Package Generator | Specified (part of PO Management) |
| 5 | Showbiz / HotBudget transfer and export tools | Showbiz Actuals format specified; HotBudget waits for a reference file |
| 6 | Financial / credit-card reconciliation | Planned |
| 7 | Budget conversion from PDF/CSV estimates | Planned |
| 8 | Talent paperwork management | Planned |
| 9 | Crew database, DOODs, call sheets | Planned |
| 10 | Crew email generation (drafts only, reviewed by a person, sent from your own mail app) | Planned |

Modules 2–4 together form **one integrated PO Management module**, and it takes
priority over the crew features.

## Petty Cash stages
1. **End-to-end demo on three fictional receipts (cloud only).** Reads each receipt,
   draws circles around vendor, date and total, adds the receipt number, fills a copy
   of the top sheet, and produces the individual receipt PDFs, combined PDFs and
   reconciliation report.
2. **Excel export test kit.** A small AppleScript test with nothing to install, run with
   Wi-Fi off. The simplest supported method is tried first, and a manual export fallback
   is always kept. Full source code, an explanation and the permissions it asks for are
   provided before anything runs on the Mac.
3. **The browser app on the Mac:** receipt import, review screen, annotation editor,
   annotated/clean toggle, and the Excel step with its fallback.
4. **Template mapping screen**, plus a profile for the user's real blank template.
5. **Envelope safeguards:** locked numbering and revisions, duplicate detection, audit
   log, automatic backups, the full set of reconciliation rules, and network-activity
   hardening.
6. **Polish, user guide, and a local trial on the Mac → v1.0.**

## Expected changes to the architecture for PO Management (no redesign)
The PO modules reuse the Stage 1 core unchanged:
- the file store
- the receipt and invoice reader
- template filling plus the preservation check
- template profiles
- PDF combining
- the audit log
- versioned outputs
- the reconciliation pattern (issues are raised for a person, never fixed automatically)

Additions planned for when PO work starts:
1. **Move shared code into `core/`.** The document reader and parser, and the profile
   loader, move into `core/` so other modules can use them. This is a file move only;
   petty cash keeps working the same way and its tests guard it.
2. **A project database** (SQLite, one local file) for the master transaction log,
   documents, budget lines and export batches.
3. **`core/sensitive.py`, a central guard for sensitive data.** Every write to a template,
   the database, a log or an export goes through it. Templates accept only fields on an
   approved list, and anything that looks like a bank, card or tax number is blocked.
4. **A restricted class of documents** (W-9, ACH): kept in a separate folder, never
   text-extracted (W-9s keep only approved fields), and logged only with generic
   wording that contains no file names or contents.
5. **Export mappings** (Showbiz Actuals CSV first, HotBudget later) stored as profile
   files, with export batches and revisions tracked.
6. **A budget-line list import** (CSV/XLSX), until Budget Conversion supplies the list.

## Things needed from the user later
- A blank or fictional copy of the **Showbiz Actuals.xlsx** reference. It is not in the
  cloud environment yet.
- A HotBudget reference file.
- A blank PO top-sheet template, and the PO numbering convention.
- A blank petty cash top-sheet template (Stage 4).
