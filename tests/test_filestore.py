import os
import stat

import pytest

from productiontools.core.filestore import OriginalsStore, OverwriteRefusedError, sha256_file, write_new_bytes
from productiontools.core.versioning import next_version_dir


def test_import_copies_fingerprints_and_locks(tmp_path):
    src = tmp_path / "receipt.jpg"
    src.write_bytes(b"fictional receipt bytes")
    before = sha256_file(src)
    store = OriginalsStore(tmp_path / "originals")
    s = store.import_file(src)
    assert s.stored_path.exists() and s.stored_path != src
    assert s.sha256 == before == sha256_file(s.stored_path)
    assert not (s.stored_path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    assert sha256_file(src) == before and src.exists()  # the user's file is untouched
    assert store.verify() == [{"file": s.stored_path.name, "unchanged": True, "read_only": True}]


def test_duplicate_import_is_detected_not_copied(tmp_path):
    a = tmp_path / "a.pdf"
    a.write_bytes(b"same")
    b = tmp_path / "b.pdf"
    b.write_bytes(b"same")
    store = OriginalsStore(tmp_path / "o")
    first, second = store.import_file(a), store.import_file(b)
    assert not first.duplicate_of_existing and second.duplicate_of_existing
    assert len(store.entries()) == 1


def test_verify_detects_a_changed_original(tmp_path):
    src = tmp_path / "x.pdf"
    src.write_bytes(b"original")
    store = OriginalsStore(tmp_path / "o")
    s = store.import_file(src)
    os.chmod(s.stored_path, 0o644)
    s.stored_path.write_bytes(b"tampered")
    assert store.verify()[0]["unchanged"] is False


def test_never_overwrite(tmp_path):
    p = write_new_bytes(tmp_path / "out.pdf", b"v1")
    with pytest.raises(OverwriteRefusedError):
        write_new_bytes(p, b"v2")
    assert p.read_bytes() == b"v1"


def test_versions_are_never_reused(tmp_path):
    v1 = next_version_dir(tmp_path)
    v2 = next_version_dir(tmp_path)
    assert (v1.name, v2.name) == ("v1", "v2")
