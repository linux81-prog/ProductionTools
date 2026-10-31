"""Unique envelope IDs.

Default format: "{production_number}-{envelope_number}", e.g. LK-0042-PC001.
Every ID is recorded in the project's append-only registry. Re-running the same
envelope reuses its ID; a different envelope trying to use an existing ID is refused.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_FORMAT = "{production_number}-{envelope_number}"


class DuplicateEnvelopeIdError(ValueError):
    pass


def make_envelope_id(env, fmt: str = DEFAULT_FORMAT) -> str:
    return fmt.format(production_number=env.production_number, envelope_number=env.envelope_number,
                      crew_member=env.crew_member, department=env.department).strip()


def _identity(env) -> dict:
    return {"crew_member": env.crew_member, "period_start": str(env.period_start),
            "period_end": str(env.period_end), "float": str(env.float_amount)}


def register(project_dir: Path, env) -> None:
    reg = Path(project_dir) / "envelope_ids.jsonl"
    entries = [json.loads(l) for l in reg.read_text().splitlines() if l.strip()] if reg.exists() else []
    for e in entries:
        if e["envelope_id"] == env.envelope_id:
            if e["identity"] != _identity(env):
                raise DuplicateEnvelopeIdError(
                    f"Envelope ID {env.envelope_id} is already used by a different envelope "
                    f"({e['identity']['crew_member']}, {e['identity']['period_start']}). Choose another envelope number.")
            return
    reg.parent.mkdir(parents=True, exist_ok=True)
    with open(reg, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"envelope_id": env.envelope_id, "identity": _identity(env),
                             "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}) + "\n")
