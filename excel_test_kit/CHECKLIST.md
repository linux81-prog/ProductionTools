# Stage 2 test checklist (fill in during the test)

Fictional data only. Please send back only this checklist, the report text, and (if you're
happy to) the exported PDFs. All three contain fictional data only.

**Your setup**
- [ ] Excel version (Excel → About Microsoft Excel): ______________
- [ ] macOS version (Apple menu → About This Mac): ______________

**Run 1: automatic, network on**
- [ ] macOS asked "Terminal wants to control Microsoft Excel": yes / no. Allowed? yes / no
- [ ] Excel asked to "Grant File Access": yes / no. Which folder? ______________
- [ ] Result line in the report: PASSED / PARTIAL / FAILED
- [ ] The PDF looks like the top sheet (compare with `REFERENCE_cloud_preview_NOT_excel.pdf`): yes / no
- [ ] Anything unexpected happened (dialogs, Excel windows left open, error messages): ______________

**Run 2: automatic, Wi-Fi off**
- [ ] Report says "Network: appears OFF": yes / no
- [ ] Result line: PASSED / PARTIAL / FAILED
- [ ] Were the prompts from Run 1 asked again? yes / no

**Manual fallback**
- [ ] Saved `results/manual_export.pdf` using "Best for printing": yes / no
- [ ] `check_manual_pdf.command` result: ______________
- [ ] Any differences between the automatic and manual PDFs: ______________

**Afterwards (optional)**
- [ ] Removed the Automation permission (System Settings → Privacy & Security → Automation): yes / no
