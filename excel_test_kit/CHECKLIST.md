# Stage 2 test checklist (fill in during the test)

Fictional data only. Please send back only this checklist, the report text and (if you're
happy to) the exported PDFs. All three contain fictional data only.

**Your setup**
- [ ] Excel version (Excel → About Microsoft Excel): ______________
- [ ] macOS version (Apple menu → About This Mac): ______________
- [ ] MANIFEST.txt fingerprints checked by your reviewer (optional): yes / no

**Run 1: automatic, internet connected**
- [ ] All Excel workbooks were closed before starting: yes / no
- [ ] macOS asked "Terminal wants to control Microsoft Excel": yes / no. Allowed? yes / no
- [ ] Excel asked to "Grant File Access": yes / no. Which folder? ______________
- [ ] Excel showed Protected View or a security message: yes / no. Did it block the export? yes / no
- [ ] Result line in the report: PASSED / PARTIAL / FAILED (if refused, copy the "Excel said" line): ______
- [ ] The PDF looks like the top sheet (compare with `REFERENCE_cloud_preview_NOT_excel.pdf`): yes / no
- [ ] The PDF shows total 331.52, balance due 68.48 and "1 of 1": yes / no
- [ ] Anything unexpected happened (dialogs, windows left open, error messages): ______________

**Run 2: automatic, internet connectivity disabled by you** (Wi-Fi off, Ethernet unplugged)
- [ ] Internet confirmed off (for example, a web page won't load): yes / no
- [ ] Result line: PASSED / PARTIAL / FAILED
- [ ] Were any prompts from Run 1 asked again? yes / no

**Manual fallback**
- [ ] Saved `results/manual_export.pdf` using "Best for printing": yes / no
- [ ] `check_manual_pdf.command` result: PASSED / PARTIAL / FAILED
- [ ] Any differences between the automatic and manual PDFs: ______________

**Afterwards (optional)**
- [ ] Removed the Automation permission (System Settings → Privacy & Security → Automation): yes / no
