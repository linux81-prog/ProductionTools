"""Versioned output folders: every export goes into a new v1, v2, v3... folder."""

from __future__ import annotations

import re
from pathlib import Path


def next_version_dir(outputs_root: Path) -> Path:
    outputs_root = Path(outputs_root)
    outputs_root.mkdir(parents=True, exist_ok=True)
    existing = [int(m.group(1)) for p in outputs_root.iterdir()
                if p.is_dir() and (m := re.fullmatch(r"v(\d+)", p.name))]
    n = max(existing, default=0) + 1
    while True:
        candidate = outputs_root / f"v{n}"
        try:
            candidate.mkdir()  # fails if it exists -> never reuse a version
            return candidate
        except FileExistsError:
            n += 1
