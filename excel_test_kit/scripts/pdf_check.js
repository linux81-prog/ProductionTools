// ProductionTools Stage 2 - PDF checker (runs locally with macOS's built-in PDF library).
//
// Reads a PDF and prints: page count, and whether it contains the text we expect
// to see on the fictional top sheet. Reading only - it never changes the PDF.
// The expected values prove Excel recalculated the template's own formulas:
//   331.52 = TOTAL (ALL ENVELOPES), 68.48 = BALANCE DUE, "1 of 1" = page numbering.
//
// Usage: osascript -l JavaScript pdf_check.js <file.pdf>

ObjC.import('Foundation');
ObjC.import('Quartz');

function run(argv) {
  if (argv.length !== 1) { return 'ERROR: expected one PDF path'; }
  var url = $.NSURL.fileURLWithPath(argv[0]);
  var doc = $.PDFDocument.alloc.initWithURL(url);
  if (doc.isNil()) { return 'ERROR: not a readable PDF'; }
  var pages = doc.pageCount;
  var text = doc.string.isNil() ? '' : ObjC.unwrap(doc.string);
  var expected = ['PETTY CASH SUMMARY', 'Jordan Avery', 'Hardware Barn', '331.52', '68.48', '1 of 1'];
  var lines = ['pages=' + pages];
  expected.forEach(function (t) {
    lines.push('contains "' + t + '"=' + (text.indexOf(t) !== -1 ? 'yes' : 'NO'));
  });
  return lines.join('\n');
}
