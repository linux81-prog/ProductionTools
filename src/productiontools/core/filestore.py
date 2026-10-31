"""Never-overwrite file store for original documents.

Every imported document is *copied* into ``originals/``. The copy is:
  * fingerprinted with SHA-256 (a unique code computed from the file's bytes),
  * made read-only,
  * recorded in an append-only manifest (``manifest.jsonl``).

The file the user selected is only ever read, never moved or modified.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class OverwriteRefusedError(FileExistsError):
    """Raised whenever an operation would replace an existing file."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_new_bytes(path: Path, data: bytes) -> Path:
    """Write a brand-new file. Refuses (never overwrites) if it already exists."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "xb") as fh:  # 'x' = fail if the file exists
            fh.write(data)
    except FileExistsError as exc:
        raise OverwriteRefusedError(f"Refusing to overwrite existing file: {path}") from exc
    return path


def write_new_text(path: Path, text: str) -> Path:
    return write_new_bytes(path, text.encode("utf-8"))


def _safe_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip() or "file"
    return name[:120]


@dataclass(frozen=True)
class StoredOriginal:
    sha256: str
    stored_path: Path
    source_name: str
    size: int
    duplicate_of_existing: bool


class OriginalsStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / "manifest.jsonl"

    # -- manifest -----------------------------------------------------------
    def entries(self) -> list[dict]:
        if not self.manifest.exists():
            return []
        with open(self.manifest, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def _append(self, entry: dict) -> None:
        with open(self.manifest, "a", encoding="utf-8") as fh:  # append-only
            fh.write(json.dumps(entry, sort_keys=True) + "\n")

    # -- import -------------------------------------------------------------
    def import_file(self, source: Path) -> StoredOriginal:
        source = Path(source)
        digest = sha256_file(source)
        for e in self.entries():
            if e["sha256"] == digest:
                return StoredOriginal(digest, self.root / e["stored_name"], source.name,
                                      e["size"], duplicate_of_existing=True)

        stored_name = f"{digest[:12]}_{_safe_name(source.name)}"
        dest = self.root / stored_name
        if dest.exists():
            raise OverwriteRefusedError(f"Refusing to overwrite existing original: {dest}")
        # Copy via exclusive create so a race can never clobber a file.
        with open(source, "rb") as src, open(dest, "xb") as dst:
            shutil.copyfileobj(src, dst)
        shutil.copystat(source, dest)
        os.chmod(dest, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # read-only

        if sha256_file(dest) != digest:  # paranoid copy verification
            raise IOError(f"Copy verification failed for {source}")

        size = dest.stat().st_size
        self._append({
            "sha256": digest,
            "stored_name": stored_name,
            "source_name": source.name,
            "size": size,
            "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        return StoredOriginal(digest, dest, source.name, size, duplicate_of_existing=False)

    # -- verification -------------------------------------------------------
    def verify(self) -> list[dict]:
        """Re-fingerprint every original; returns one result per file."""
        results = []
        for e in self.entries():
            p = self.root / e["stored_name"]
            ok = p.exists() and sha256_file(p) == e["sha256"]
            writable = p.exists() and bool(p.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
            results.append({"file": e["stored_name"], "unchanged": ok, "read_only": not writable})
        return results
