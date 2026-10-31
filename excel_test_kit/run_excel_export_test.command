#!/bin/bash
# ProductionTools Stage 2 - Excel PDF export test (FICTIONAL test file only).
#
# DO NOT RUN until the user has reviewed this code and explicitly approved it.
#
# What it does (nothing else):
#   1. Works only inside this kit's own folder.
#   2. Checks the fictional test workbook against its published SHA-256 fingerprint.
#   3. Makes a uniquely named working COPY in ./work/ (a plain copy: macOS's
#      "downloaded file" information is NOT removed; if that triggers a Protected View
#      or security prompt that blocks the export, the test reports it).
#   4. Asks Microsoft Excel, via AppleScript, to export sheet "PC Formulas (1)" of that
#      copy as a PDF in ./results/ - only after confirming no other workbook is open and
#      that the opened workbook is exactly the test copy.
#   5. Checks what is visible in the PDF (page count + expected fictional text).
#   6. Re-checks the test workbook's fingerprint. If it changed, the result is FAILED,
#      even if a PDF was produced.
#   7. Writes a plain-text report to ./results/excel_export_result.txt.
# It installs nothing, needs no administrator password, and makes no network connections.

cd "$(dirname "$0")" || exit 1
KIT="$(pwd)"
TEST_FILE="test_files/FICTIONAL_LK-0042-PC001_TopSheet.xlsx"
EXPECTED_HASH="$(cut -d' ' -f1 test_files/FICTIONAL_LK-0042-PC001_TopSheet.xlsx.sha256 2>/dev/null)"
SHEET="PC Formulas (1)"
STAMP="$(date +%Y%m%d-%H%M%S)"
WORK="work/$STAMP"
COPY="$WORK/PTtest_$STAMP.xlsx"          # unique name, used to confirm the workbook's identity
RESULTS="results"
PDF="$RESULTS/excel_export_$STAMP.pdf"
REPORT="$RESULTS/excel_export_result.txt"

mkdir -p "$WORK" "$RESULTS"
log() { echo "$1" >> "$REPORT"; }
final() { echo "$1"; log "$1"; }

log ""
log "=============================================================="
log "ProductionTools - Excel export test report"
log "Run at:          $(date)"
log "macOS:           $(sw_vers -productVersion)"
log "Test file:       $TEST_FILE (fictional)"
log "Method:          AppleScript 'save as <sheet> ... PDF file format' (simplest), with workbook identity checks"
# Informational only: reads the Mac's routing table (sends nothing). This is NOT proof of
# offline operation. Offline operation is tested by disabling internet connectivity yourself.
if route -n get default >/dev/null 2>&1; then
  log "Network route:   a default route exists (informational only; not proof either way)"
else
  log "Network route:   no default route found (informational only; not proof of offline operation)"
fi

if [ ! -f "$TEST_FILE" ] || [ -z "$EXPECTED_HASH" ]; then
  final "RESULT: FAILED - test file or its fingerprint file is missing."
  exit 1
fi
if [ ! -d "/Applications/Microsoft Excel.app" ]; then
  final "RESULT: FAILED - Microsoft Excel was not found in /Applications. Use the manual fallback (MANUAL_FALLBACK.md)."
  exit 1
fi

HASH_BEFORE="$(shasum -a 256 "$TEST_FILE" | cut -d' ' -f1)"
if [ "$HASH_BEFORE" != "$EXPECTED_HASH" ]; then
  final "RESULT: FAILED - the test workbook does not match its published fingerprint (it was changed or replaced). Nothing was run."
  exit 1
fi
log "Fingerprint:     test workbook matches the published fingerprint"

cp "$TEST_FILE" "$COPY"     # plain copy; downloaded-file attributes are kept, not bypassed
if xattr -p com.apple.quarantine "$COPY" >/dev/null 2>&1; then
  log "Download flag:   present on the copy (macOS marks downloaded files; Excel may show Protected View)"
else
  log "Download flag:   not present on the copy"
fi

echo "Before continuing: in Microsoft Excel, close ALL open workbooks (the test refuses to run otherwise)."
echo "If macOS asks whether Terminal may control Microsoft Excel, see README before answering."
echo "If Excel shows 'Grant File Access', Protected View or any security message, note it in CHECKLIST.md."
START=$(date +%s)
OUTCOME="$(osascript "scripts/export_with_excel.applescript" "$KIT/$COPY" "$KIT/$PDF" "$SHEET" 2>&1)"
END=$(date +%s)
log "Excel said:      $OUTCOME"
log "Duration:        $((END - START)) seconds"

HASH_AFTER="$(shasum -a 256 "$TEST_FILE" | cut -d' ' -f1)"
UNCHANGED=no
if [ "$HASH_AFTER" = "$EXPECTED_HASH" ]; then
  UNCHANGED=yes
  log "Fingerprint:     test workbook unchanged after the test"
else
  log "Fingerprint:     TEST WORKBOOK CHANGED - this must never happen"
fi

VERDICT=FAILED
if [[ "$OUTCOME" == OK* ]] && [ -s "$PDF" ]; then
  log "PDF:             $PDF ($(stat -f%z "$PDF") bytes)"
  CHECK="$(osascript -l JavaScript "scripts/pdf_check.js" "$KIT/$PDF" 2>&1)"
  log "Visible-output checks (not conclusive proof of formula recalculation):"
  log "$CHECK"
  VERDICT="$(echo "$CHECK" | sed -n 's/^VERDICT=//p')"
  [ -z "$VERDICT" ] && VERDICT=FAILED
fi

if [ "$UNCHANGED" != yes ]; then
  final "RESULT: FAILED - the original fictional test workbook's fingerprint changed (regardless of the PDF)."
elif [ "$VERDICT" = PASSED ]; then
  final "RESULT: PASSED - Excel exported the PDF automatically; visible output matched; test workbook unchanged."
elif [ "$VERDICT" = PARTIAL ]; then
  final "RESULT: PARTIAL - a PDF was made but some visible-output checks did not match (see above)."
elif [[ "$OUTCOME" == REFUSED* ]]; then
  final "RESULT: FAILED (safely refused) - see 'Excel said' above. Nothing was exported."
else
  final "RESULT: FAILED - automatic export did not produce a usable PDF. You can use the manual fallback (MANUAL_FALLBACK.md)."
fi

echo
echo "Done. Report: $KIT/$REPORT"
echo "Please open the report and the PDF, then fill in CHECKLIST.md."
