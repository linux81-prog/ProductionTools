"""End-to-end petty cash pipeline (Stage 1: run from a script, no screens yet).

import originals -> read receipts -> draft annotations -> apply human review
-> number receipts -> annotated + clean receipt PDFs -> fill top sheet copy
-> top sheet PDF (Excel on the Mac, or manual) -> combined PDFs
-> reconciliation report.

Nothing is ever finalized automatically: the result is "ready for review".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable

import yaml

from ..core import netguard
from ..core.audit import AuditLog
from ..core.filestore import OriginalsStore, write_new_bytes, write_new_text
from ..core.versioning import next_version_dir
from . import annotate, pdf_out, recon
from .extract import load_pages
from .mapping import load_profile
from .models import Envelope, Receipt
from .parse import parse_receipt
from .review import apply_review, load_review
from .envelope_ids import DEFAULT_FORMAT, make_envelope_id, register
from .line_list import fill_descriptions, load_line_list
from .template_fill import fill_topsheet, receipt_label

# A provider turns the filled .xlsx into a PDF. On the Mac this will be the
# Excel bridge (Stage 2); returning None means "not available" -> manual fallback.
TopSheetPdfProvider = Callable[[Path], bytes | None]


@dataclass
class RunResult:
    version_dir: Path
    envelope: Envelope
    flags: list
    preservation: dict
    extraction: dict
    files: dict = field(default_factory=dict)
    topsheet_pdf_source: str = ""


def load_envelope(path: Path) -> tuple[Envelope, list[str]]:
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    as_date = lambda v: v if isinstance(v, date) else date.fromisoformat(str(v))
    env = Envelope(
        envelope_number=d["envelope_number"], production=d["production"], production_number=d["production_number"],
        company=d["company"], crew_member=d["crew_member"], department=d["department"], position=d["position"],
        period_start=as_date(d["period_start"]), period_end=as_date(d["period_end"]),
        float_amount=Decimal(str(d["float_amount"])), cash_returned=Decimal(str(d["cash_returned"])),
        reported_total=Decimal(str(d["reported_total"])),
        per_receipt_limit=Decimal(str(d.get("per_receipt_limit", "250.00"))), crew_phone=str(d.get("crew_phone", "")))
    env.envelope_id = str(d.get("envelope_id") or make_envelope_id(env, d.get("envelope_id_format", DEFAULT_FORMAT)))
    return env, list(d["receipts"])


def _field_json(r: Receipt) -> dict:
    return {k: {"value": None if f.value is None else str(f.value), "confidence": f.confidence,
                "located": f.box is not None, "needs_review": f.needs_review, "note": f.note}
            for k, f in r.fields.items()}


def run_envelope(envelope_yaml: Path, receipts_dir: Path, profile_path: Path, chart: dict[str, str] | Path,
                 project_dir: Path, review_path: Path | None = None,
                 topsheet_pdf_provider: TopSheetPdfProvider | None = None,
                 topsheet_pdf_label: str = "") -> RunResult:
    netguard.install()  # app-level safeguard: no outbound connections from this process
    project_dir = Path(project_dir)
    audit = AuditLog(project_dir / "audit.log")
    store = OriginalsStore(project_dir / "originals")
    env, receipt_names = load_envelope(envelope_yaml)
    register(project_dir, env)  # refuses an ID already used by a different envelope
    audit.record("envelope_id", envelope_id=env.envelope_id)
    if not isinstance(chart, dict):  # a job line list file (CSV / XLSX / YAML)
        line_file = store.import_file(Path(chart))
        chart = load_line_list(line_file.stored_path)
        audit.record("line_list_loaded", file=Path(line_file.source_name).name, lines=len(chart))
    profile = load_profile(profile_path)
    known_vendors: list[str] = []

    # 1. import originals (copied, fingerprinted, read-only)
    for name in receipt_names:
        stored = store.import_file(Path(receipts_dir) / name)
        audit.record("original_imported", file=name, sha256=stored.sha256, duplicate=stored.duplicate_of_existing)
        pages = load_pages(stored.stored_path)
        r = Receipt(name, stored.stored_path, stored.sha256, pages)
        r.fields = parse_receipt(pages, known_vendors)
        env.receipts.append(r)
        audit.record("receipt_extracted", file=name,
                     fields={k: str(f.value) for k, f in r.fields.items()},
                     needs_review=[k for k, f in r.fields.items() if f.needs_review])

    vdir = next_version_dir(project_dir / "outputs")
    files: dict[str, str] = {}
    extraction = {r.source_name: {"pages": [{"kind": p.source_kind, "preprocessing": p.preprocessing} for p in r.pages],
                                  "fields": _field_json(r)} for r in env.receipts}
    write_new_text(vdir / "extraction_before_review.json", json.dumps(extraction, indent=2))

    # 2. review previews: the machine's own marks before any human review (dashed = unconfirmed).
    #    No number yet - numbering happens after review, once dates are confirmed.
    for i, r in enumerate(env.receipts, start=1):
        write_new_bytes(vdir / "review_previews" / f"preview-{i:02d}_{Path(r.source_name).stem}.pdf",
                        annotate.render_receipt_pdf(r, annotated=True, draft=True))

    # 3. human review decisions
    if review_path:
        apply_review(env.receipts, load_review(review_path), audit)

    # 3b. descriptions from the job's line list where the reviewer did not type one
    fill_descriptions(env.receipts, chart, audit)

    # 4. numbering: by date, then by the order received
    order = sorted(range(len(env.receipts)), key=lambda i: (env.receipts[i].date or date.max, i))
    env.receipts = [env.receipts[i] for i in order]
    for i, r in enumerate(env.receipts, start=1):
        r.number, r.seq = f"{env.envelope_number}-{i:03d}", i
        r.label = receipt_label(r, profile)
        audit.record("receipt_numbered", file=r.source_name, number=r.number, label=r.label)

    # 5. individual receipt PDFs
    annotated, clean = [], []
    for r in env.receipts:
        fname = pdf_out.receipt_filename(r)
        a = annotate.render_receipt_pdf(r, annotated=True)
        for field_name, why in r.annotation_notes.items():
            audit.record("annotation_skipped", file=r.source_name, field=field_name, reason=why)
        c = annotate.render_receipt_pdf(r, annotated=False)
        write_new_bytes(vdir / "receipts_annotated" / fname, a)
        write_new_bytes(vdir / "receipts_clean" / fname, c)
        label = f"{r.number}  {r.vendor or '?'}  ${r.total if r.total is not None else '?'}"
        annotated.append((label, a))
        clean.append((label, c))

    # 6. top sheet: filled COPY of the template + automatic preservation check
    xlsx = vdir / f"{env.envelope_number}_TopSheet.xlsx"
    info = fill_topsheet(env, profile, xlsx)
    audit.record("topsheet_filled", file=xlsx.name, cells=len(info["cells_written"]),
                 preservation_passed=info["preservation"]["passed"])
    files["topsheet_xlsx"] = str(xlsx)

    ts_pdf = topsheet_pdf_provider(xlsx) if topsheet_pdf_provider else None
    source = topsheet_pdf_label if ts_pdf else "pending (manual Excel export needed)"
    if ts_pdf is None:
        ts_pdf = pdf_out.placeholder_topsheet_pdf(xlsx.name)
    write_new_bytes(vdir / f"{env.envelope_number}_TopSheet.pdf", ts_pdf)

    # 7. combined PDFs (annotation toggle: both variants produced)
    ts_label = f"{env.envelope_number} Top Sheet"
    write_new_bytes(vdir / f"{env.envelope_number}_Combined_Annotated.pdf", pdf_out.combine(ts_pdf, ts_label, annotated))
    write_new_bytes(vdir / f"{env.envelope_number}_Combined_Clean.pdf", pdf_out.combine(ts_pdf, ts_label, clean))

    # 8. reconciliation report
    flags = recon.reconcile(env, chart)
    originals_check = store.verify()
    extra = [("Originals integrity", [f"{o['file']}: {'unchanged' if o['unchanged'] else 'CHANGED'}, "
                                      f"{'read-only' if o['read_only'] else 'WRITABLE'}" for o in originals_check]),
             ("Top sheet", [f"Filled copy: {xlsx.name}. Template preservation check: "
                            f"{'PASSED' if info['preservation']['passed'] else 'FAILED'}.",
                            f"Top sheet PDF source: {source}."]),
             ("Network", [f"App-level network lock installed: {netguard.is_installed()}; outbound attempts blocked during this run: "
                          f"{len(netguard.LOG.attempts)}. (Application-level safeguard only; not OS-enforced.)"])]
    write_new_bytes(vdir / f"{env.envelope_number}_Reconciliation_Report.pdf", recon.report_pdf(env, flags, extra))
    recon.report_xlsx(env, flags, vdir / f"{env.envelope_number}_Reconciliation_Report.xlsx")

    summary = {"status": "READY FOR HUMAN REVIEW - NOT FINALIZED",
               "blocking_errors": sum(f.severity == "ERROR" for f in flags),
               "numbers": {k: str(v) for k, v in recon.summary_numbers(env).items()},
               "receipts": [{"number": r.number, "file": pdf_out.receipt_filename(r), "source": r.source_name,
                             "fields": _field_json(r), "verified_by": r.verified_by} for r in env.receipts],
               "topsheet_pdf_source": source, "originals": originals_check, "network": netguard.summary(),
               "preservation": info["preservation"]}
    write_new_text(vdir / "run_summary.json", json.dumps(summary, indent=2, default=str))
    audit.record("run_complete", version=vdir.name, blocking_errors=summary["blocking_errors"])
    return RunResult(vdir, env, flags, info["preservation"], extraction, files, source)
