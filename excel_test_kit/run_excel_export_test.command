#!/bin/bash
# ProductionTools Stage 2 - Excel PDF export test (FICTIONAL test file only).
#
# DO NOT RUN until the user has reviewed this code and explicitly approved it.
#
# What it does (nothing else):
#   1. Works only inside this kit's own folder.
#   2. Records the test file's fingerprint (SHA-256).
#   3. Makes a working COPY of the fictional test workbook in ./work/
#      (the original test file and the user's real template are never opened or changed).
#   4. Asks Microsoft Excel, via AppleScript, to save sheet "PC Formulas (1)" of that
#      copy as a PDF in ./results/  (simplest supported method).
#   5. Checks the PDF (page count + expected fictional text) with macOS's built-in PDF reader.
#   6. Re-checks the test file's fingerprint to prove it was not changed.
#   7. Writes a plain-text report to ./results/excel_export_result.txt.
# It installs nothing, needs no administrator password, and makes no network connections.

cd "$(dirname "$0")" || exit 1
KIT="$(pwd)"
TEST_FILE="test_files/FICTIONAL_LK-0042-PC001_TopSheet.xlsx"
SHEET="PC Formulas (1)"
STAMP="$(date +%Y%m%d-%H%M%S)"
WORK="work/$STAMP"
RESULTS="results"
PDF="$RESULTS/excel_export_$STAMP.pdf"
REPORT="$RESULTS/excel_export_result.txt"

mkdir -p "$WORK" "$RESULTS"
say_and_log() { echo "$1"; echo "$1" >> "$REPORT"; }

{
  echo "ProductionTools - Excel export test report"
  echo "Run at:        $(date)"
  echo "macOS:         $(sw_vers -productVersion)"
  echo "Test file:     $TEST_FILE (fictional)"
  # Local check only: is there a default network route? (reads the routing table; sends nothing)
  if route -n get default >/dev/null 2>&1; then
    echo "Network:       appears ON  (for the offline proof, turn Wi-Fi off and run again)"
  else
    echo "Network:       appears OFF (good: this run proves the export works offline)"
  fi
  echo "Method:        AppleScript 'save as active sheet ... PDF file format' (simplest)"
} >> "$REPORT"

if [ ! -f "$TEST_FILE" ]; then
  say_and_log "RESULT: FAILED - test file missing: $TEST_FILE"
  exit 1
fi
if [ ! -d "/Applications/Microsoft Excel.app" ]; then
  say_and_log "RESULT: FAILED - Microsoft Excel was not found in /Applications."
  say_and_log "Use the manual fallback (MANUAL_FALLBACK.md)."
  exit 1
fi

HASH_BEFORE="$(shasum -a 256 "$TEST_FILE" | cut -d' ' -f1)"

# Copy WITHOUT extended attributes (-X) so Excel does not open the copy in
# "Protected View" (downloaded-file mode), which would block automation.
cp -X "$TEST_FILE" "$WORK/topsheet_copy.xlsx"

echo "Asking Microsoft Excel to export the PDF..."
echo "If macOS asks whether Terminal may control Microsoft Excel, choose OK (see README)."
echo "If Excel asks to 'Grant File Access' to a folder, note it in the checklist, then allow it."
START=$(date +%s)
OUTCOME="$(osascript "scripts/export_with_excel.applescript" "$KIT/$WORK/topsheet_copy.xlsx" "$KIT/$PDF" "$SHEET" 2>&1)"
END=$(date +%s)

echo "Excel said:    $OUTCOME" >> "$REPORT"
echo "Duration:      $((END - START)) seconds" >> "$REPORT"

HASH_AFTER="$(shasum -a 256 "$TEST_FILE" | cut -d' ' -f1)"
if [ "$HASH_BEFORE" = "$HASH_AFTER" ]; then
  echo "Test file:     unchanged (fingerprint identical before and after)" >> "$REPORT"
else
  echo "Test file:     CHANGED - this should never happen; please report it" >> "$REPORT"
fi

if [[ "$OUTCOME" == OK* ]] && [ -s "$PDF" ]; then
  echo "PDF:           $PDF ($(stat -f%z "$PDF") bytes)" >> "$REPORT"
  CHECK="$(osascript -l JavaScript "scripts/pdf_check.js" "$KIT/$PDF" 2>&1)"
  echo "$CHECK" >> "$REPORT"
  if echo "$CHECK" | grep -q '=NO' || ! echo "$CHECK" | grep -qx 'pages=1'; then
    say_and_log "RESULT: PARTIAL - a PDF was made but some checks did not match (see above)."
  else
    say_and_log "RESULT: PASSED - Excel exported the PDF automatically and all checks matched."
  fi
else
  say_and_log "RESULT: FAILED - automatic export did not produce a PDF."
  say_and_log "Please use the manual fallback (MANUAL_FALLBACK.md); nothing else is needed."
fi

echo
echo "Done. Report: $KIT/$REPORT"
echo "Please open the report and the PDF, then fill in CHECKLIST.md."
