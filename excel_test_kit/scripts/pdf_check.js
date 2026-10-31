// ProductionTools Stage 2 - PDF checker (runs locally with macOS's built-in PDF library).
//
// Reads a PDF (never changes it) and reports what is VISIBLE in it:
//   - the page count (expected: 1),
//   - whether the text we expect on the fictional top sheet appears.
// The amounts 331.52 (TOTAL ALL ENVELOPES) and 68.48 (BALANCE DUE) and "1 of 1"
// (page numbering) are values the template's formulas produce. Seeing them in the PDF
// verifies the visible output is as expected; it is NOT conclusive proof that Excel
// recalculated every formula.
//
// Last line of output is a verdict:
//   VERDICT=PASSED   readable PDF, 1 page, all expected text visible
//   VERDICT=PARTIAL  readable PDF, but page count or some expected text differs
//   VERDICT=FAILED   not a readable PDF
//
// Usage: osascript -l JavaScript pdf_check.js <file.pdf>

ObjC.import('Foundation');
ObjC.import('Quartz');

function run(argv) {
  if (argv.length !== 1) { return 'ERROR: expected one PDF path\nVERDICT=FAILED'; }
  var url = $.NSURL.fileURLWithPath(argv[0]);
  var doc = $.PDFDocument.alloc.initWithURL(url);
  if (doc.isNil()) { return 'not a readable PDF\nVERDICT=FAILED'; }
  var pages = doc.pageCount;
  var text = doc.string.isNil() ? '' : ObjC.unwrap(doc.string);
  var expected = ['PETTY CASH SUMMARY', 'Jordan Avery', 'Hardware Barn', '331.52', '68.48', '1 of 1'];
  var allFound = true;
  var lines = ['pages=' + pages];
  expected.forEach(function (t) {
    var found = text.indexOf(t) !== -1;
    if (!found) { allFound = false; }
    lines.push('visible "' + t + '"=' + (found ? 'yes' : 'NO'));
  });
  lines.push('VERDICT=' + ((pages === 1 && allFound) ? 'PASSED' : 'PARTIAL'));
  return lines.join('\n');
}
