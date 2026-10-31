# ProductionTools

A private, offline production-management app for film and commercial producers.
It runs in your web browser, but everything happens on your own Mac, with no cloud
AI and no outside services.

**Current status: Stage 1. The petty cash pipeline is working from a script, run
on fictional data in the cloud.** There's no browser interface yet, and nothing for
you to install. See [docs/ROADMAP.md](docs/ROADMAP.md).

## Stage 1 results
The finished demo outputs and the test report are in **[docs/stage1-demo/](docs/stage1-demo/)**.
Start with [test-results.md](docs/stage1-demo/test-results.md).

## What the Stage 1 pipeline does
1. **Copies each receipt** into a read-only `originals/` folder and records its fingerprint
   (a unique code calculated from its contents). It never changes your files.
2. **Reads each receipt:** photos are straightened and read with offline OCR (text
   recognition); scanned PDFs are read with OCR; emailed PDFs are read from their built-in text.
3. **Finds the vendor, date, subtotal, tax, total and payment type**, each with a confidence score.
4. **Draws draft annotations**, with dashed circles where values are unverified, before any
   person has looked.
5. **Applies the person's review** (corrections, positions, account codes, descriptions,
   confirmation), and logs every change.
6. **Numbers the receipts** (`PC001-001`, …) by date, then draws red circles around the vendor,
   date and total, puts the number on each receipt, and saves annotated and clean PDFs named
   `PC001-001_2026-10-14_Hardware-Barn_81.30.pdf`.
7. **Fills a copy of the company's Excel top sheet.** It changes only the mapped cells, then
   automatically checks that nothing else in the workbook changed.
8. **Builds the combined PDFs** (top sheet first, then the receipts in order, with bookmarks)
   and a **reconciliation report** (PDF and Excel).

## For developers
```bash
uv venv && uv pip install -e . pytest
```

```bash
python tools/make_fixtures.py
```

```bash
python tools/make_stress_set.py
```

```bash
python -m pytest
```

```bash
python tools/run_demo.py
```

```bash
python tools/make_report.py
```

- The first two commands generate the fictional test data.
- `run_demo.py` runs the full demo into `demo_runs/`.
- `make_report.py` rebuilds `docs/stage1-demo/`.

Layout:
- `src/productiontools/core/`: shared code (never-overwrite file store, network lock, audit
  log, versioned output folders, surgical Excel filling plus the preservation checker)
- `src/productiontools/petty_cash/`: the petty cash module
- `tools/`: development scripts. `cloud_preview.py` is cloud-only and not part of the app.
- `fixtures/`: fictional receipts, template, template profile, envelope and reviewer decisions
- `tests/`: automated tests

Rules: fictional data only, offline only, originals are never modified, and a person must
verify. See [docs/NETWORK-SECURITY.md](docs/NETWORK-SECURITY.md).
