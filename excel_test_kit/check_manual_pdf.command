#!/bin/bash
# ProductionTools Stage 2 - check a PDF you exported MANUALLY from Excel (fallback test).
#
# DO NOT RUN until the user has reviewed this code and explicitly approved it.
#
# Reads results/manual_export.pdf (which you save yourself from Excel, see MANUAL_FALLBACK.md)
# and reports PASSED, PARTIAL or FAILED. A PDF merely existing is never reported as success:
#   PASSED   readable PDF, 1 page, all expected fictional text visible, test workbook unchanged
#   PARTIAL  readable PDF, but page count or some expected text differs
#   FAILED   PDF missing or unreadable, or the test workbook's fingerprint changed
# It only reads files. It does not control Excel or any other app, and uses no network.

cd "$(dirname "$0")" || exit 1
PDF="results/manual_export.pdf"
REPORT="results/excel_export_result.txt"
TEST_FILE="test_files/FICTIONAL_LK-0042-PC001_TopSheet.xlsx"
EXPECTED_HASH="$(cut -d' ' -f1 test_files/FICTIONAL_LK-0042-PC001_TopSheet.xlsx.sha256 2>/dev/null)"
mkdir -p results
log() { echo "$1" | tee -a "$REPORT"; }

echo "" >> "$REPORT"
log "Manual fallback check - $(date)"

ACTUAL_HASH="$(shasum -a 256 "$TEST_FILE" 2>/dev/null | cut -d' ' -f1)"
if [ -z "$EXPECTED_HASH" ] || [ "$ACTUAL_HASH" != "$EXPECTED_HASH" ]; then
  log "Fingerprint: the test workbook does not match its published fingerprint (it was saved, changed or replaced)."
  log "RESULT (manual): FAILED"
  exit 1
fi
log "Fingerprint: test workbook unchanged"

if [ ! -s "$PDF" ]; then
  log "RESULT (manual): FAILED - $PDF not found or empty. Save the PDF there and run this check again."
  exit 1
fi

CHECK="$(osascript -l JavaScript "scripts/pdf_check.js" "$(pwd)/$PDF" 2>&1)"
log "Visible-output checks (not conclusive proof of formula recalculation):"
log "$CHECK"
VERDICT="$(echo "$CHECK" | sed -n 's/^VERDICT=//p')"
case "$VERDICT" in
  PASSED)  log "RESULT (manual): PASSED - 1 page, all expected text visible, test workbook unchanged." ;;
  PARTIAL) log "RESULT (manual): PARTIAL - the PDF is readable but some checks did not match (see above)." ;;
  *)       log "RESULT (manual): FAILED - the PDF could not be read." ;;
esac
