-- ProductionTools Stage 2 - Excel export test (FICTIONAL test file only)
--
-- What this script does, step by step:
--   1. Notes whether Microsoft Excel was already open.
--   2. Asks Excel to open ONE workbook (the test copy) READ-ONLY.
--   3. Selects the sheet named "PC Formulas (1)".
--   4. Asks Excel to recalculate, then save that one sheet as a PDF.
--   5. Closes the workbook WITHOUT saving (the .xlsx is never changed).
--   6. Quits Excel only if Excel was NOT open before the test started.
-- It does not touch any other workbook, file, folder, app, or the network.
--
-- Usage (called by run_excel_export_test.command):
--   osascript export_with_excel.applescript <workbook.xlsx> <output.pdf> <sheet name>

on run argv
	if (count of argv) is not 3 then return "ERROR: expected 3 arguments (workbook, pdf, sheet name)"
	set workbookPOSIX to item 1 of argv
	set pdfPOSIX to item 2 of argv
	set sheetName to item 3 of argv

	-- Excel's AppleScript commands use classic "Mac:Style:Paths".
	set workbookHFS to (POSIX file workbookPOSIX) as text
	set pdfHFS to (POSIX file pdfPOSIX) as text

	set excelWasRunning to application "Microsoft Excel" is running
	set wb to missing value
	try
		with timeout of 180 seconds
			tell application "Microsoft Excel"
				set excelVersion to version
				set wb to open workbook workbook file name workbookHFS read only true
				-- Some Excel versions do not return the opened workbook; use the active one then.
				if wb is missing value then set wb to active workbook
				activate object worksheet sheetName of wb
				-- Recalculate all formulas (the copy also asks Excel to recalculate on open).
				try
					calculate full
				on error
					calculate
				end try
				save as active sheet filename pdfHFS file format PDF file format
				close wb saving no
				set wb to missing value
			end tell
		end timeout
	on error errMsg number errNum
		-- Clean up: close the test workbook without saving, if it is still open.
		try
			if wb is not missing value then
				tell application "Microsoft Excel" to close wb saving no
			end if
		end try
		my quitExcelIfWeStartedIt(excelWasRunning)
		return "ERROR " & errNum & ": " & errMsg
	end try

	my quitExcelIfWeStartedIt(excelWasRunning)
	return "OK Excel " & excelVersion
end run

on quitExcelIfWeStartedIt(excelWasRunning)
	if excelWasRunning is false then
		try
			tell application "Microsoft Excel" to quit saving no
		end try
	end if
end quitExcelIfWeStartedIt
