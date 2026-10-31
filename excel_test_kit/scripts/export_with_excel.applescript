-- ProductionTools Stage 2 - Excel export test (FICTIONAL test file only)
--
-- What this script does, step by step:
--   1. REFUSES to start if any workbook is already open in Excel (all unrelated
--      workbooks must be closed first, so the wrong one can never be targeted).
--   2. Asks Excel to open ONE workbook (the uniquely named test copy) READ-ONLY.
--   3. Confirms the identity of what was opened: exactly one workbook is open, its
--      name is the expected unique name, and its full path matches the expected path.
--      If any of this cannot be confirmed, it REFUSES to export and touches nothing.
--      It never falls back to "whatever workbook is active".
--   4. Exports the sheet "PC Formulas (1)" of THAT confirmed workbook to a PDF.
--   5. Closes that confirmed workbook WITHOUT saving (the .xlsx is never changed).
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

	-- Excel's AppleScript commands use classic "Mac:Style:Paths"; some versions report POSIX paths.
	set workbookHFS to (POSIX file workbookPOSIX) as text
	set pdfHFS to (POSIX file pdfPOSIX) as text
	set expectedName to my lastPathPart(workbookPOSIX)

	set excelWasRunning to application "Microsoft Excel" is running
	set wb to missing value
	set verified to false
	try
		with timeout of 180 seconds
			tell application "Microsoft Excel"
				set excelVersion to version

				-- Safeguard 1: no other workbooks may be open.
				set openBefore to count of workbooks
				if openBefore is not 0 then
					return "REFUSED: " & openBefore & " workbook(s) already open in Excel. Close all workbooks (keep nothing open) and run the test again."
				end if

				open workbook workbook file name workbookHFS read only true

				-- Safeguard 2: confirm exactly one workbook is open and it is ours.
				set openAfter to count of workbooks
				if openAfter is not 1 then
					return "REFUSED: expected exactly 1 open workbook after opening the test copy, found " & openAfter & ". If Excel showed a Protected View or security message, that prevented normal opening. Nothing was exported."
				end if
				set wb to workbook 1
				set actualName to name of wb
				set actualPath to full name of wb
				if actualName is not expectedName then
					return "REFUSED: open workbook is named '" & actualName & "', not the expected test copy '" & expectedName & "'. Nothing was exported."
				end if
				if actualPath is not workbookHFS and actualPath is not workbookPOSIX then
					return "REFUSED: open workbook's path could not be confirmed as the test copy (Excel reported: " & actualPath & "). Nothing was exported."
				end if
				set verified to true

				-- Export the named sheet of the CONFIRMED workbook (no reliance on 'active workbook').
				set targetSheet to worksheet sheetName of wb
				activate object targetSheet
				if (name of active sheet) is not sheetName then
					close wb saving no
					return "REFUSED: could not select sheet '" & sheetName & "'. Nothing was exported."
				end if
				try
					calculate full
				on error
					calculate
				end try
				save as targetSheet filename pdfHFS file format PDF file format
				close wb saving no
				set wb to missing value
			end tell
		end timeout
	on error errMsg number errNum
		-- Clean up: close the test workbook without saving, but ONLY if its identity was confirmed.
		if verified and wb is not missing value then
			try
				tell application "Microsoft Excel" to close wb saving no
			end try
		end if
		my quitExcelIfWeStartedIt(excelWasRunning)
		return "ERROR " & errNum & ": " & errMsg
	end try

	my quitExcelIfWeStartedIt(excelWasRunning)
	return "OK Excel " & excelVersion
end run

on lastPathPart(p)
	set AppleScript's text item delimiters to "/"
	set parts to text items of p
	set AppleScript's text item delimiters to ""
	return item -1 of parts
end lastPathPart

on quitExcelIfWeStartedIt(excelWasRunning)
	if excelWasRunning is false then
		try
			tell application "Microsoft Excel"
				if (count of workbooks) is 0 then quit saving no
			end tell
		end try
	end if
end quitExcelIfWeStartedIt
