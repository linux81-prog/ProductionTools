"""Run the Stage 1 end-to-end demo on the FICTIONAL fixtures.

    python tools/run_demo.py [--out DIR]

Produces a fresh project folder (default: demo_runs/<timestamp>) containing
originals/, outputs/v1/... and audit.log.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cloud_preview  # noqa: E402  (cloud-only helper, not part of the app)
from productiontools.petty_cash.pipeline import run_envelope  # noqa: E402

FIX = ROOT / "fixtures"


def run(out: Path):
    chart = {str(k): v for k, v in yaml.safe_load((FIX / "account_codes.yaml").read_text()).items()}
    return run_envelope(
        envelope_yaml=FIX / "envelope.yaml",
        receipts_dir=FIX / "receipts",
        profile_path=FIX / "templates" / "master_pc" / "PC_Sheet_Template.profile.yaml",
        chart=chart,
        project_dir=out,
        review_path=FIX / "review.yaml",
        topsheet_pdf_provider=cloud_preview.preview_pdf,
        topsheet_pdf_label=cloud_preview.LABEL,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "demo_runs" / datetime.now().strftime("%Y%m%d-%H%M%S"))
    args = ap.parse_args()
    res = run(args.out)
    print(f"Output: {res.version_dir}")
    for f in res.flags:
        print(f"  [{f.severity}] {f.scope}: {f.check} - {f.message}")
    print("Preservation:", "PASSED" if res.preservation["passed"] else "FAILED")


if __name__ == "__main__":
    main()
