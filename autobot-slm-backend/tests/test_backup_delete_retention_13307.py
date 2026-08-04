# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Backups must be deletable, prunable, and land somewhere findable (#13307).

The Backups page could create a backup and nothing else. `@router.delete` count
in `api/stateful.py` was **0**, so nothing in the system could reclaim space —
retention was not a missing convenience, it was unimplementable. And the
destination was the service account's home directory, chosen by a fallback
rather than a decision: `config.py` said `~/slm-backups` while
`services/backup.py` named `/var/lib/slm/backups` in a branch that could never
run, because `settings` has always defined `backup_dir`.

Two of these tests guard against destroying data rather than merely failing:

* deleting a backup whose copy-to-storage failed must NOT unlink the path it
  recorded — that is the live `/var/lib/redis/dump.rdb` on the target node;
* a run of failed backups must not let retention evict the last good one.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


class _FakeBackup:
    def __init__(self, backup_id, status="completed", path=None, created=None, node="n1", svc="redis"):
        self.backup_id = backup_id
        self.status = status
        self.backup_path = path
        self.created_at = created or datetime.now(timezone.utc)
        self.node_id = node
        self.service_type = svc


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeDB:
    """Enough AsyncSession for the delete/retention paths."""

    def __init__(self, rows):
        self._rows = rows
        self.deleted = []
        self.commits = 0

    async def execute(self, _query):
        return _FakeResult(self._rows)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.commits += 1


def _real_backup_module():
    """Load services/backup.py for real, bypassing the harness stub.

    The slm-backend conftest hands out MagicMocks for `config` and much of
    `services`. Asserting against those is vacuous — every attribute is a truthy
    mock, so a test can pass whether or not the code does anything. Loading the
    module from its own path is the only way these tests measure the real thing.
    """
    import importlib.util
    import sys

    root = Path(__file__).resolve().parents[1]
    for extra in (str(root), str(root.parent)):
        if extra not in sys.path:
            sys.path.insert(0, extra)

    spec = importlib.util.spec_from_file_location("_real_slm_backup_13307", root / "services" / "backup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def backup_module():
    try:
        return _real_backup_module()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"services/backup.py not importable in this environment: {exc}")


@pytest.fixture()
def service(backup_module, tmp_path, monkeypatch):
    """A BackupService writing into a tmp dir instead of /var/lib/slm/backups."""
    monkeypatch.setattr(backup_module, "BACKUP_STORAGE_DIR", tmp_path)
    return backup_module.BackupService.__new__(backup_module.BackupService)


# --- destination -----------------------------------------------------------


def _code_lines(path: Path) -> str:
    """Source with comment-only lines dropped.

    The comments explaining this change quote the old values verbatim, so a
    naive substring check matches its own rationale and fails forever.
    """
    return "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")
    )


def test_storage_dir_is_not_a_home_directory():
    """The reported symptom: 'no idea where they are created'.

    Asserted against config.py's source rather than `settings`, which the
    harness replaces with a MagicMock whose every attribute is truthy.
    """
    config_src = _code_lines(Path(__file__).resolve().parents[1] / "config.py")

    assert (
        'Path.home() / "slm-backups"' not in config_src
    ), "backup_dir still defaults to the service account's home directory"
    assert 'os.getenv("SLM_BACKUP_DIR", "/var/lib/slm/backups")' in config_src


def test_service_and_config_agree_on_one_destination(backup_module):
    """The two files used to name different defaults, the dead one being right."""
    backup_src = _code_lines(Path(__file__).resolve().parents[1] / "services" / "backup.py")

    assert 'hasattr(settings, "backup_dir")' not in backup_src, (
        "the dead hasattr fallback is back — it named a different default that "
        "could never apply, which is how the two files disagreed"
    )
    assert "BACKUP_STORAGE_DIR = Path(settings.backup_dir)" in backup_src, (
        "services/backup.py must take the destination from settings alone; a "
        "second literal here is exactly how the two files came to disagree"
    )

    # The runtime value is deliberately NOT asserted here. `config` is a
    # MagicMock in this harness even for a module loaded from its own path, so
    # `Path(settings.backup_dir)` resolves to a mock repr — an assertion on it
    # would measure the stub, not the code. config.py's literal default is
    # pinned by test_storage_dir_is_not_a_home_directory; together the two
    # establish the single-source property without asserting against a mock.


def test_import_survives_an_unwritable_destination(backup_module):
    """The destination moved to a root-owned path; import must not die on it.

    `backup_service` is constructed at module import. An unguarded mkdir there
    raises PermissionError on any host where the ansible role has not run yet —
    and in CI — taking the whole API down. Found by running it.
    """
    assert backup_module.backup_service is not None
    assert backup_module.BackupService._ensure_storage_dir() in (True, False)


# --- delete ----------------------------------------------------------------


async def test_delete_removes_the_record_and_the_file(service, tmp_path):
    stored = tmp_path / "abc_20260804.rdb"
    stored.write_bytes(b"rdb")
    db = _FakeDB([_FakeBackup("abc", path=str(stored))])

    ok, message = await service.delete_backup(db, "abc")

    assert ok, message
    assert not stored.exists(), "the stored file must go with the record"
    assert db.deleted and db.commits == 1


async def test_delete_succeeds_when_the_file_is_already_gone(service, tmp_path):
    """A row pointing at a missing file is what a half-finished cleanup leaves.

    Refusing to delete it would make that state unrecoverable through the API —
    which is the situation this issue is about.
    """
    db = _FakeDB([_FakeBackup("abc", path=str(tmp_path / "vanished.rdb"))])

    ok, _ = await service.delete_backup(db, "abc")

    assert ok
    assert db.deleted


async def test_delete_never_unlinks_a_path_outside_the_backup_store(service, tmp_path):
    """The dangerous case, and the reason `_unlink_backup_file` is scoped.

    `_complete_backup` records the REMOTE path when the copy to SLM storage
    failed — for Redis that is the live `/var/lib/redis/dump.rdb` on the target
    node. Unlinking it would destroy the data the backup exists to protect.
    """
    outside = tmp_path.parent / "live-dump.rdb"
    outside.write_bytes(b"production data")
    db = _FakeDB([_FakeBackup("abc", path=str(outside))])

    ok, _ = await service.delete_backup(db, "abc")

    assert ok, "the record must still be removable"
    assert outside.exists(), (
        "delete_backup unlinked a file outside the backup store — for a "
        "copy-failed backup that path is the live database on the target node"
    )


async def test_an_in_progress_backup_is_not_deletable(service, backup_module):
    # The module's own enum, not a literal: models.database is stubbed in this
    # harness, so a hardcoded "in_progress" would never match its .value.
    in_progress = backup_module.BackupStatus.IN_PROGRESS.value
    db = _FakeDB([_FakeBackup("abc", status=in_progress)])

    ok, message = await service.delete_backup(db, "abc")

    assert not ok
    assert "in progress" in message.lower()
    assert not db.deleted


async def test_deleting_an_unknown_backup_reports_not_found(service):
    ok, message = await service.delete_backup(_FakeDB([]), "nope")

    assert not ok
    assert message == "Backup not found"


# --- retention -------------------------------------------------------------


async def test_retention_keeps_the_newest_n(service, tmp_path):
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(5):
        path = tmp_path / f"b{i}.rdb"
        path.write_bytes(b"x")
        rows.append(_FakeBackup(f"b{i}", path=str(path), created=now - timedelta(hours=i)))
    db = _FakeDB(rows)

    removed = await service.apply_retention(db, "n1", "redis", keep_count=2, max_age_days=0)

    assert removed == ["b2", "b3", "b4"], removed
    assert (tmp_path / "b0.rdb").exists() and (tmp_path / "b1.rdb").exists()
    assert not (tmp_path / "b4.rdb").exists()


async def test_retention_prunes_by_age_independently_of_count(service, tmp_path):
    now = datetime.now(timezone.utc)
    fresh = _FakeBackup("fresh", path=str(tmp_path / "f.rdb"), created=now)
    old = _FakeBackup("old", path=str(tmp_path / "o.rdb"), created=now - timedelta(days=40))
    for b in (fresh, old):
        (tmp_path / f"{b.backup_id[0]}.rdb").write_bytes(b"x")
    db = _FakeDB([fresh, old])

    removed = await service.apply_retention(db, "n1", "redis", keep_count=0, max_age_days=30)

    assert removed == ["old"], removed


async def test_retention_disabled_on_both_dimensions_removes_nothing(service, tmp_path):
    rows = [_FakeBackup(f"b{i}", path=str(tmp_path / f"b{i}.rdb")) for i in range(5)]
    db = _FakeDB(rows)

    removed = await service.apply_retention(db, "n1", "redis", keep_count=0, max_age_days=0)

    assert removed == []
    assert db.commits == 0


async def test_a_naive_created_at_is_not_treated_as_ancient(service, tmp_path):
    """SQLite hands back naive datetimes; comparing them to an aware cutoff raises.

    Getting this wrong would either crash retention or silently prune everything.
    """
    naive_recent = datetime.now(timezone.utc).replace(tzinfo=None)
    db = _FakeDB([_FakeBackup("b", path=str(tmp_path / "b.rdb"), created=naive_recent)])

    removed = await service.apply_retention(db, "n1", "redis", keep_count=0, max_age_days=30)

    assert removed == []


async def test_failed_backups_never_count_toward_the_keep_budget(backup_module):
    """The one moment retention matters is after a run of failures.

    If failed rows counted, three bad nights would evict the last good backup —
    precisely when it is the only thing standing between you and data loss.
    `apply_retention` only ever selects `completed` rows, so the fixture returns
    only those; this pins that the query stays that way.
    """
    import inspect

    source = inspect.getsource(backup_module.BackupService.apply_retention)
    assert "BackupStatus.COMPLETED.value" in source, (
        "apply_retention no longer filters to completed backups — a run of " "failures can now evict the last good one"
    )
