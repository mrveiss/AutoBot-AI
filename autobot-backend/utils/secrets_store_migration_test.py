# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the legacy-to-canonical secrets-store migration (#14081 review).

These exercise ``migrate_legacy_secrets_store`` directly, against the real
``utils.paths_manager.get_data_path`` (never a monkeypatched stand-in for
it, per the review requirement) with the process CWD controlled via
``monkeypatch.chdir`` -- exactly how that resolver is CWD-sensitive in
production.
"""

from __future__ import annotations

import os
import shutil
import time

import pytest

import utils.secrets_store_migration as migration_module
from utils.secrets_store_migration import (
    AmbiguousSecretsStoreError,
    SecretsStoreLockTimeoutError,
    migrate_legacy_secrets_store,
)


class TestSameLocationIsNoOp:
    """The common dev case: legacy and canonical resolve identically."""

    def test_no_move_no_warning(self, tmp_path, monkeypatch, caplog):
        # get_data_path("secrets.key") falls back to the literal relative
        # Path("data") / "secrets.key", resolved against CWD -- so chdir to
        # tmp_path and point canonical_dir at "<tmp_path>/data" to make the
        # two resolvers agree, as they do whenever CWD == base_dir.
        monkeypatch.chdir(tmp_path)
        canonical_dir = tmp_path / "data"
        canonical_dir.mkdir()
        (canonical_dir / "secrets.key").write_bytes(b"canonical-key-material")

        with caplog.at_level("WARNING"):
            migrate_legacy_secrets_store(canonical_dir, ["secrets.key"], "test store")

        assert (canonical_dir / "secrets.key").read_bytes() == b"canonical-key-material"
        assert not any("Migrated" in r.message for r in caplog.records)


class TestGenuineFirstBoot:
    """Neither location has data: still a no-op, caller proceeds to provision fresh."""

    def test_no_move_when_nothing_exists(self, tmp_path, monkeypatch):
        legacy_root = tmp_path / "legacy_cwd"
        legacy_root.mkdir()
        monkeypatch.chdir(legacy_root)

        canonical_dir = tmp_path / "canonical"
        canonical_dir.mkdir()

        migrate_legacy_secrets_store(canonical_dir, ["secrets.key", "secrets.json"], "test store")

        assert list(canonical_dir.iterdir()) == []


class TestSuccessfulMigration:
    """Legacy has data, canonical is empty: files move, key permissions locked down."""

    def test_moves_files_and_locks_down_key_permissions(self, tmp_path, monkeypatch, caplog):
        legacy_root = tmp_path / "legacy_cwd"
        legacy_root.mkdir()
        monkeypatch.chdir(legacy_root)
        legacy_data_dir = legacy_root / "data"
        legacy_data_dir.mkdir()
        (legacy_data_dir / "secrets.key").write_bytes(b"legacy-key-material")
        (legacy_data_dir / "secrets.key").chmod(0o644)  # deliberately loose, to prove it gets locked down
        (legacy_data_dir / "secrets.json").write_text('{"a": 1}', encoding="utf-8")

        canonical_dir = tmp_path / "canonical"
        canonical_dir.mkdir()

        with caplog.at_level("WARNING"):
            migrate_legacy_secrets_store(canonical_dir, ["secrets.key", "secrets.json"], "test store")

        assert (canonical_dir / "secrets.key").read_bytes() == b"legacy-key-material"
        assert (canonical_dir / "secrets.json").read_text(encoding="utf-8") == '{"a": 1}'
        assert not (legacy_data_dir / "secrets.key").exists()
        assert not (legacy_data_dir / "secrets.json").exists()
        assert oct((canonical_dir / "secrets.key").stat().st_mode)[-3:] == "600"
        assert any("Migrated" in r.message for r in caplog.records)

    def test_log_line_carries_no_absolute_path(self, tmp_path, monkeypatch, caplog):
        """Log lines must stay safe to paste into an issue or PR (#14081 review)."""
        legacy_root = tmp_path / "legacy_cwd"
        legacy_root.mkdir()
        monkeypatch.chdir(legacy_root)
        legacy_data_dir = legacy_root / "data"
        legacy_data_dir.mkdir()
        (legacy_data_dir / "secrets.key").write_bytes(b"legacy-key-material")

        canonical_dir = tmp_path / "canonical"
        canonical_dir.mkdir()

        with caplog.at_level("WARNING"):
            migrate_legacy_secrets_store(canonical_dir, ["secrets.key"], "test store")

        for record in caplog.records:
            assert str(tmp_path) not in record.message


class TestBothLocationsPopulated:
    """An ambiguous state a wrong choice would destroy: fail loudly instead."""

    def test_raises_and_does_not_move_anything(self, tmp_path, monkeypatch):
        legacy_root = tmp_path / "legacy_cwd"
        legacy_root.mkdir()
        monkeypatch.chdir(legacy_root)
        legacy_data_dir = legacy_root / "data"
        legacy_data_dir.mkdir()
        (legacy_data_dir / "secrets.key").write_bytes(b"legacy-key-material")

        canonical_dir = tmp_path / "canonical"
        canonical_dir.mkdir()
        (canonical_dir / "secrets.key").write_bytes(b"canonical-key-material")

        with pytest.raises(AmbiguousSecretsStoreError, match="test store"):
            migrate_legacy_secrets_store(canonical_dir, ["secrets.key"], "test store")

        # Neither side was touched.
        assert (legacy_data_dir / "secrets.key").read_bytes() == b"legacy-key-material"
        assert (canonical_dir / "secrets.key").read_bytes() == b"canonical-key-material"


class TestAtomicMoveVerification:
    """#14081 review round 5, finding 3: shutil.move is not atomic across
    filesystems (copy2+unlink), so an interrupted copy can leave a
    truncated file at the destination and the untouched source at the
    legacy location -- permanently "both populated". The replacement
    (copy-to-tmp, fsync, verify size, os.replace, then unlink source) must
    refuse to finish and must leave the source untouched when the copy
    comes up short.
    """

    def test_size_mismatch_aborts_and_preserves_the_source(self, tmp_path, monkeypatch):
        legacy_root = tmp_path / "legacy_cwd"
        legacy_root.mkdir()
        monkeypatch.chdir(legacy_root)
        legacy_data_dir = legacy_root / "data"
        legacy_data_dir.mkdir()
        (legacy_data_dir / "secrets.key").write_bytes(b"legacy-key-material-32-bytes!!!")

        canonical_dir = tmp_path / "canonical"
        canonical_dir.mkdir()

        def _truncated_copy(src, dst, *a, **kw):
            # Simulate an interrupted cross-filesystem copy: fewer bytes
            # land at the destination than the source actually has.
            with open(src, "rb") as f:
                data = f.read()
            with open(dst, "wb") as f:
                f.write(data[:4])

        monkeypatch.setattr(shutil, "copy2", _truncated_copy)

        with pytest.raises(OSError, match="size mismatch"):
            migrate_legacy_secrets_store(canonical_dir, ["secrets.key"], "test store")

        # Source untouched, no truncated file left at the destination, and
        # no stray .tmp file -- a caller retrying later sees a clean legacy
        # location, not a poisoned canonical one.
        assert (legacy_data_dir / "secrets.key").read_bytes() == b"legacy-key-material-32-bytes!!!"
        assert not (canonical_dir / "secrets.key").exists()
        assert not (canonical_dir / "secrets.key.tmp").exists()


class TestCrossProcessLock:
    """#14081 review round 5, finding 3: backend and worker are separate OS
    processes and can both reach a genuine first boot at the same moment on
    an upgrade -- an in-process lock cannot see across that boundary.
    """

    def test_a_held_lock_blocks_a_second_migration_until_timeout(self, tmp_path, monkeypatch):
        legacy_root = tmp_path / "legacy_cwd"
        legacy_root.mkdir()
        monkeypatch.chdir(legacy_root)
        legacy_data_dir = legacy_root / "data"
        legacy_data_dir.mkdir()
        (legacy_data_dir / "secrets.key").write_bytes(b"legacy-key-material")

        canonical_dir = tmp_path / "canonical"
        canonical_dir.mkdir()
        # Simulate another process mid-migration: a fresh lockfile already
        # held in the canonical directory.
        (canonical_dir / migration_module._LOCK_FILENAME).write_text(str(9999999), encoding="utf-8")

        monkeypatch.setattr(migration_module, "_LOCK_WAIT_TIMEOUT_SECONDS", 0.3)
        monkeypatch.setattr(migration_module, "_LOCK_POLL_INTERVAL_SECONDS", 0.05)

        with pytest.raises(SecretsStoreLockTimeoutError):
            migrate_legacy_secrets_store(canonical_dir, ["secrets.key"], "test store")

        # The blocked caller must not have touched anything while waiting.
        assert (legacy_data_dir / "secrets.key").read_bytes() == b"legacy-key-material"
        assert not (canonical_dir / "secrets.key").exists()

    def test_a_stale_lock_is_reclaimed(self, tmp_path, monkeypatch):
        legacy_root = tmp_path / "legacy_cwd"
        legacy_root.mkdir()
        monkeypatch.chdir(legacy_root)
        legacy_data_dir = legacy_root / "data"
        legacy_data_dir.mkdir()
        (legacy_data_dir / "secrets.key").write_bytes(b"legacy-key-material")

        canonical_dir = tmp_path / "canonical"
        canonical_dir.mkdir()
        stale_lock = canonical_dir / migration_module._LOCK_FILENAME
        stale_lock.write_text(str(9999999), encoding="utf-8")
        # Back-date the lockfile's mtime so it reads as abandoned by a
        # crashed holder rather than actively held.
        old_time = time.time() - 3600
        os.utime(stale_lock, (old_time, old_time))

        monkeypatch.setattr(migration_module, "_LOCK_STALE_SECONDS", 60)
        monkeypatch.setattr(migration_module, "_LOCK_WAIT_TIMEOUT_SECONDS", 2)

        migrate_legacy_secrets_store(canonical_dir, ["secrets.key"], "test store")

        assert (canonical_dir / "secrets.key").read_bytes() == b"legacy-key-material"
        assert not (legacy_data_dir / "secrets.key").exists()
        assert not stale_lock.exists()
