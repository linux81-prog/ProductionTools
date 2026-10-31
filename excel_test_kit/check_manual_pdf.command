#!/bin/bash
# ProductionTools Stage 2 - check a PDF you exported MANUALLY from Excel (fallback test).
#
# DO NOT RUN until the user has reviewed this code and explicitly approved it.
#
# Reads results/manual_export.pdf (which you save yourself from Excel, see MANUAL_FALLBACK.md),
# checks its page count and expected fictional text, and adds the result to the report.
# It only reads that PDF. It does not control Excel or any other app, and uses no network.

cd "$(dirname "$0")" || exit 1
PDF="results/manual_export.pdf"
REPORT="results/excel_export_result.txt"
mkdir -p results
{
  echo
  echo "Manual fallback check - $(date)"
} >> "$REPORT"
if [ ! -s "$PDF" ]; then
  echo "RESULT (manual): FAILED - $PDF not found. Save the PDF there and try again." | tee -a "$REPORT"
  exit 1
fi
osascript -l JavaScript "scripts/pdf_check.js" "$(pwd)/$PDF" | tee -a "$REPORT"
echo "RESULT (manual): PDF found and checked (see lines above)." | tee -a "$REPORT"
