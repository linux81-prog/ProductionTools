# Stage 1 — Test Results and Demo Report

Generated 2026-10-31 20:35 in the cloud development environment. **All data is fictional.**

## 1. Automated tests

**Result: 52 passed, 1 warning in 59.61s**

Every test runs with the app-level network lock installed, so any accidental outbound
connection would make the suite fail.

<details><summary>All test names and results</summary>

```
tests/test_annotate.py::test_only_number_is_added_no_labels_footer_or_signatures PASSED
tests/test_annotate.py::test_page_size_is_unchanged_for_pdf_receipts PASSED
tests/test_annotate.py::test_existing_pen_circle_is_not_duplicated PASSED
tests/test_annotate.py::test_existing_number_is_not_duplicated PASSED
tests/test_annotate.py::test_manual_position_from_reviewer_is_used PASSED
tests/test_annotate.py::test_clean_version_has_no_marks PASSED
tests/test_end_to_end.py::test_all_outputs_exist_with_consistent_names PASSED
tests/test_end_to_end.py::test_combined_pdf_order_and_bookmarks PASSED
tests/test_end_to_end.py::test_reconciliation_flags_the_planted_problems PASSED
tests/test_end_to_end.py::test_topsheet_values_and_preservation PASSED
tests/test_end_to_end.py::test_originals_preserved_and_locked PASSED
tests/test_end_to_end.py::test_annotated_receipts_carry_only_number_and_circles PASSED
tests/test_end_to_end.py::test_no_unexpected_network_attempts PASSED
tests/test_end_to_end.py::test_second_run_creates_new_version_without_overwriting PASSED
tests/test_end_to_end.py::test_master_template_envelope PASSED
tests/test_filestore.py::test_import_copies_fingerprints_and_locks PASSED
tests/test_filestore.py::test_duplicate_import_is_detected_not_copied PASSED
tests/test_filestore.py::test_verify_detects_a_changed_original PASSED
tests/test_filestore.py::test_never_overwrite PASSED
tests/test_filestore.py::test_versions_are_never_reused PASSED
tests/test_line_list_and_ids.py::test_line_list_formats PASSED
tests/test_line_list_and_ids.py::test_conflicting_duplicate_line_is_rejected PASSED
tests/test_line_list_and_ids.py::test_description_filled_only_when_blank PASSED
tests/test_line_list_and_ids.py::test_envelope_ids_unique_per_project PASSED
tests/test_netguard.py::test_outbound_connection_is_blocked_and_recorded PASSED
tests/test_netguard.py::test_dns_lookup_of_outside_name_is_blocked PASSED
tests/test_netguard.py::test_udp_send_to_outside_is_blocked PASSED
tests/test_netguard.py::test_loopback_is_allowed PASSED
tests/test_netguard.py::test_summary_states_scope_honestly PASSED
tests/test_ocr_accuracy.py::test_demo_receipts_extract_correctly PASSED
tests/test_ocr_accuracy.py::test_stress_set_accuracy_and_no_silent_errors PASSED
tests/test_parse_and_recon.py::test_parse_basic_receipt PASSED
tests/test_parse_and_recon.py::test_total_line_split_from_amount_and_balance_due_zero_ignored PASSED
tests/test_parse_and_recon.py::test_arithmetic_mismatch_lowers_confidence PASSED
tests/test_parse_and_recon.py::test_missing_total_is_reported_not_guessed PASSED
tests/test_parse_and_recon.py::test_tidy_vendor PASSED
tests/test_parse_and_recon.py::test_balanced_envelope_has_no_errors PASSED
tests/test_parse_and_recon.py::test_shortage_and_overage PASSED
tests/test_parse_and_recon.py::test_flags_duplicates_dates_limits_codes_and_unverified PASSED
tests/test_parse_and_recon.py::test_reported_total_mismatch PASSED
tests/test_template_preservation.py::test_fill_passes_every_preservation_check PASSED
tests/test_template_preservation.py::test_values_and_formulas_after_fill PASSED
tests/test_template_preservation.py::test_recalculate_flag_added_when_template_lacks_it PASSED
tests/test_template_preservation.py::test_calcpr_inserted_when_missing_entirely PASSED
tests/test_template_preservation.py::test_refuses_to_overwrite_formula_cell PASSED
tests/test_template_preservation.py::test_refuses_non_anchor_merged_cell PASSED
tests/test_template_preservation.py::test_refuses_existing_destination_and_template_as_destination PASSED
tests/test_template_preservation.py::test_writes_cells_that_do_not_exist_yet PASSED
tests/test_template_preservation.py::test_checker_catches_an_unmapped_change PASSED
tests/test_template_preservation.py::test_checker_catches_a_dropped_image PASSED
tests/test_template_preservation.py::test_profile_loads_and_matches_template PASSED
tests/test_template_preservation.py::test_master_template_preserved PASSED
```
</details>

## 2. OCR / extraction accuracy

"Correct" means the extracted value exactly matches the answer key (amounts to the cent,
dates to the day, vendor names ignoring capitalisation and punctuation).

### 2a. The three demo receipts (phone photo, scanned PDF, emailed invoice)

**18/18 fields correct (100%).**

| Field | Correct | Wrong | Not found | Wrong/missing but flagged for review |
|---|---|---|---|---|
| vendor | 3/3 | 0 | 0 | 0/0 |
| date | 3/3 | 0 | 0 | 0/0 |
| subtotal | 3/3 | 0 | 0 | 0/0 |
| tax | 3/3 | 0 | 0 | 0/0 |
| total | 3/3 | 0 | 0 | 0/0 |
| payment | 3/3 | 0 | 0 | 0/0 |

### 2b. Stress set: 12 harder fictional phone photos

These were made deliberately difficult (blur, noise, crumpling, fading, dim light, low
resolution) so this figure is more honest than the clean demo receipts alone.

**68/72 fields correct (94%).
Wrong values that were NOT flagged for human review: 0.**

| Field | Correct | Wrong | Not found | Wrong/missing but flagged for review |
|---|---|---|---|---|
| vendor | 11/12 | 1 | 0 | 1/1 |
| date | 12/12 | 0 | 0 | 0/0 |
| subtotal | 11/12 | 0 | 1 | 1/1 |
| tax | 11/12 | 1 | 0 | 1/1 |
| total | 11/12 | 0 | 1 | 1/1 |
| payment | 12/12 | 0 | 0 | 0/0 |

| File | Condition | Fields correct |
|---|---|---|
| s01_clean_photo.jpg | clean photo | 6/6 |
| s02_motion_blur.jpg | motion blur | 6/6 |
| s03_heavy_blur.jpg | heavy blur | 2/6 |
| s04_sensor_noise.jpg | sensor noise | 6/6 |
| s05_heavy_noise.jpg | heavy noise | 6/6 |
| s06_heavy_crumple.jpg | heavy crumple | 6/6 |
| s07_faded_thermal.jpg | faded thermal | 6/6 |
| s08_very_faded_thermal.jpg | very faded thermal | 6/6 |
| s09_dim_light.jpg | dim light | 6/6 |
| s10_low_resolution.jpg | low resolution | 6/6 |
| s11_very_low_resolution.jpg | very low resolution | 6/6 |
| s12_blur_and_noise_and_fade.jpg | blur + noise + fade | 6/6 |

Failures in detail:

| File | Condition | Field | Expected | Got | Flagged for review? |
|---|---|---|---|---|---|
| s03_heavy_blur.jpg | heavy blur | vendor | Main ST Deli | C0o3e Ans | yes |
| s03_heavy_blur.jpg | heavy blur | subtotal | 100.45 | None | yes |
| s03_heavy_blur.jpg | heavy blur | tax | 9.54 | 109.99 | yes |
| s03_heavy_blur.jpg | heavy blur | total | 109.99 | None | yes |

**What this means:** on clear and moderately degraded photos the reader was accurate. On
the heavily blurred photo it failed, but it flagged every wrong or missing value for a
person, which is the safety behaviour we need. Real receipts will vary more than synthetic
ones; expect lower accuracy on handwriting, very faded thermal paper and unusual layouts.
Handwriting was not tested in Stage 1.

## 3. Workbook preservation (your master template vs. the filled copy)

Template: `fixtures/templates/master_pc/PC_Sheet_Template.xlsx`, as you supplied it. It has
5 sheets, array formulas, hidden helper columns and a Google Sheets export extension.

**Overall: PASSED.** Two independent methods were used:
(A) raw comparison of every internal part of the .xlsx file, and (B) re-opening both files
with a separate spreadsheet library and comparing values, formulas, formatting and print settings.

| Result | Check | Detail |
|---|---|---|
| PASS | Same internal parts (no part added or removed) | 25 parts in template, 25 in filled copy |
| PASS | All unrelated parts byte-identical (styles, images, drawings, shared strings, printer settings, other sheets, theme, metadata) | 23 parts identical |
| PASS | workbook.xml identical apart from the recalculate-on-open flag (sheet order, defined names, print areas) |  |
| PASS | Worksheet settings outside the cell grid byte-identical (merged cells, conditional formatting, data validation, page setup, margins, header/footer, column widths, drawing link) |  |
| PASS | Only mapped cells changed; every mapped cell kept its formatting style | 31000 template cells checked |
| PASS | Sheet names and order unchanged | PC Formulas (1), PC Formulas (2), PC Formulas (3), PC Formulas (4), PC Blank (For Printing) |
| PASS | Workbook defined names unchanged | 0 names: [] |
| PASS | All cell values and formulas unchanged outside mapped cells (all sheets) | 150000 cells compared, 2699 formulas |
| PASS | All cell formatting unchanged, including mapped cells (fonts, fills, borders, alignment, number formats, protection) | 150000 cells compared |
| PASS | Merged cells, conditional formatting, data validation, print area/titles, page setup, margins, header/footer, print options, images, column widths, row heights, frozen panes unchanged | checked on 5 sheets |

**Documented intentional changes (the only differences allowed):**
- **Mapped cell values**: Only the cells listed in the template profile receive new values; each keeps its original formatting style.
- **workbook.xml <calcPr fullCalcOnLoad="1">**: Tells Excel to recalculate every formula when the file is opened, so totals reflect the new values.
- **Formula replaced in an explicitly approved cell**: Only where the template profile marks a cell replace_formula: true (e.g. the master template's Envelope No cell now shows the unique envelope ID instead of the '1 of N' formula).
- **Row 'spans' hint (only if needed)**: An optional performance hint listing which columns a row uses; widened only when a mapped cell is outside it. No visual effect.

**Allowed changes actually seen in this run:**
- workbook.xml: fullCalcOnLoad="1" set (Excel recalculates on open)
- S3: template formula replaced as approved in the profile

The tests also confirm that the checker **catches** problems. It fails on a changed formula
in an unmapped cell, and on a damaged logo image. They also confirm that filling **refuses**
to write into a formula cell or into the hidden part of a merged cell. And a template
*without* the recalculate flag is tested too: the flag is added, and that is the only change
to workbook.xml.

## 4. Reconciliation results for envelope PC001

| Severity | Scope | Check | Finding |
|---|---|---|---|
| ERROR | Envelope | Cash reconciliation | Float $300.00 − receipts $276.53 = $23.47 expected back; $21.47 returned. SHORT by $2.00. |
| WARNING | PC001-002 | Receipt arithmetic | Subtotal $86.25 + tax $8.19 = $94.44, but the receipt's printed total is $94.94 (difference $0.50). |
| INFO | PC001-001 | Description | Filled from the job's line list for line 2410: "Art Dept - Expendables". |
| INFO | PC001-003 | Description | Filled from the job's line list for line 2510: "Props - Purchases". |
| INFO | PC001-003 | Payment method | Receipt shows payment by Visa, not cash. |

All three were planted on purpose in the fictional data: the crew member returned $2.00
too little, the café receipt's printed total is $0.50 more than subtotal + tax, and the
invoice was paid by card.

## 5. What failed, or needed manual correction

**Fields the machine flagged for review before any person looked** (shown with dashed circles in
`review_previews/`):
- `02_copper_kettle_scan.pdf`: **total** = 94.94 (confidence 72%) — subtotal 86.25 + tax 8.19 = 94.44, not 94.94 (cross-check failed)

**Manual corrections the reviewer had to make on the demo receipts: 0.** All vendor, date, total, subtotal, tax and payment values were read correctly.

**About the review step:** Stage 1 has no screens yet, so the review was **simulated** with
`fixtures/review.yaml`. No real person reviewed these receipts, and nothing in the outputs claims
otherwise. That simulated review:
- entered the account code and description for each receipt (the app never guesses these),
- accepted the café receipt's printed total despite its arithmetic error (left for the accountant),
- confirmed each receipt. In the real app, a receipt only counts as confirmed once a person
  confirms it on screen.

**Manual annotation positioning needed: 0** in this demo. Every vendor, date and total was located automatically. Manual positioning is supported and tested (`tests/test_annotate.py`),
and the visual editor arrives in Stage 3.

**Known limitations and things that did not work perfectly:**
- **Top sheet PDF:** there is no Excel in the cloud, so `PC001_TopSheet.pdf` is a *cloud preview*
  made with LibreOffice and is clearly watermarked. It is not part of the app. On your Mac,
  Excel produces this page (Stage 2). The manual-export fallback page is tested too.
- **Receipt-number placement:** the number is small and goes automatically in the emptiest spot on or
  just beside the printed text. On some receipts that spot is in the paper margin; the Stage 3 editor
  lets you move it.
- **Existing pen marks:** a field that already has a coloured pen circle is not circled again (tested).
  Circles drawn in black or pencil are hard to tell apart from printing and may not be detected.
  You'll be able to remove a duplicate circle in the editor.
- **Long descriptions** shrink to fit the template's narrow "For What" column (that's the template's own
  shrink-to-fit setting). Shorter descriptions print larger.
- **Master template:** "Envelope No" (S3) is a formula, so the envelope ID is not written on the sheet
  (it's used in file names). "Category" is mapped to the department. Both need your confirmation.
- **Heavy blur:** one of 12 stress photos failed (see 2b). It was flagged, not silently wrong.
- **Overflow:** more than 35 receipts (the master template's first sheet) stops with a clear message.
  Continuation onto the template's sheets 2–4 comes in a later stage.
- **Vendor names** are tidied from ALL CAPS ("HARDWARE BARN" → "Hardware Barn"). Unusual names
  may need a person to adjust them.

## 6. Network and privacy (Stage 1)

- **App-level network lock (application-level safeguard):** installed for every run and every
  test; outbound attempts during the demo run: 0.
  This covers only ProductionTools' own Python process.
- The OCR models ship inside the installed package; nothing is downloaded at run time.
- See `docs/NETWORK-SECURITY.md` for the difference between the app's own safeguards, macOS's
  built-in firewall (incoming connections only), and independent outbound blockers.

## 7. Files in this folder

| File | What it is |
|---|---|
| `receipts_annotated/` | The three receipt PDFs: circles around vendor, date and total, plus a small receipt number (#1–#3); nothing else added |
| `receipts_clean/` | The same receipts with no marks |
| `review_previews/` | The machine's own circles before review (dashed = not yet confirmed); a review aid, not a deliverable |
| `PC001_TopSheet.xlsx` | A filled copy of **your master template** (the template file itself is unchanged) |
| `PC001_TopSheet.pdf` | Cloud preview of the top sheet (watermarked; Excel makes this on the Mac) |
| `PC001_Combined_Annotated.pdf` | Top sheet + annotated receipts, with bookmarks |
| `PC001_Combined_Clean.pdf` | Top sheet + clean receipts (the annotation toggle) |
| `PC001_Reconciliation_Report.pdf` / `.xlsx` | Discrepancies and missing information |
| `extraction_before_review.json`, `run_summary.json`, `audit.log`, `ocr_accuracy.json` | Machine-readable records |
