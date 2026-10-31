# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Attachment files follow their database transaction (#19756).

``upload()`` wrote the file to its final path before the commit, and ``delete()`` unlinked it
before the commit. A failed commit left an orphan file in one case and a row pointing at a
missing file in the other; a failed unlink was only logged, so it was never retried.

These tests use real files under ``tmp_path`` and a fake session, and assert on ORDER: what
was on disk at the moment the commit ran.
"""

import hashlib
import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from llc.models.attachment import LLCWorkItemAttachment
from llc.models.attachment_deletion import LLCAttachmentFileDeletion
from llc.services import attachment_files as files
from llc.services import attachment_outbox as outbox
from llc.services.attachment_service import AttachmentNotFound, AttachmentService
from testkit.fake_async_session import FakeAsyncSession, FakeResult

_COMPANY = str(uuid.uuid4())
_ITEM = str(uuid.uuid4())


@pytest.fixture
def root(tmp_path: Path):
    with (
        patch("llc.services.attachment_service._LOCAL_STORAGE_PATH", tmp_path),
        patch("llc.services.attachment_service._STORAGE_BACKEND", "local_disk"),
    ):
        yield tmp_path.resolve()


def _read(path: Path) -> bytes:
    return path.read_bytes()


def _write(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _published(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and files.STAGING_DIRNAME not in p.parts]


def _staged(root: Path) -> list[Path]:
    return list((root / files.STAGING_DIRNAME).glob("*")) if (root / files.STAGING_DIRNAME).is_dir() else []


async def _upload(session, content: bytes = b"hello", filename: str = "notes.txt") -> LLCWorkItemAttachment:
    return await AttachmentService().upload(
        session, company_id=_COMPANY, work_item_id=_ITEM, filename=filename, content_type="text/plain", content=content
    )


# --- AC1: a forced commit failure leaves no file at the final path -------------------------


@pytest.mark.asyncio
async def test_a_failed_commit_leaves_no_file_at_the_final_path(root):
    session = FakeAsyncSession(commit_error=RuntimeError("commit failed"))
    with pytest.raises(RuntimeError, match="commit failed"):
        await _upload(session)
    assert _published(root) == []


@pytest.mark.asyncio
async def test_a_failed_commit_keeps_the_staged_bytes_for_the_sweep_to_settle(root):
    """A raising commit does not prove the row is absent, so the bytes are not unlinked blind."""
    session = FakeAsyncSession(commit_error=RuntimeError("commit failed"))
    with pytest.raises(RuntimeError):
        await _upload(session)
    assert len(_staged(root)) == 1


@pytest.mark.asyncio
async def test_the_final_path_is_empty_when_the_commit_runs(root):
    """Order, not outcome: nothing is published before the row is durable."""
    seen: list[tuple[list[Path], list[Path]]] = []

    def at_commit(_n: int):
        seen.append((_published(root), _staged(root)))

    session = FakeAsyncSession(commit_error=at_commit)
    row = await _upload(session)
    assert seen == [([], seen[0][1])] and len(seen[0][1]) == 1
    assert [Path(row.storage_path)] == _published(root)
    assert _staged(root) == []


@pytest.mark.asyncio
async def test_upload_stores_the_sha256_of_the_content(root):
    row = await _upload(FakeAsyncSession(), content=b"\x00binary\xff", filename="blob.bin")
    assert row.sha256 == hashlib.sha256(b"\x00binary\xff").hexdigest()
    assert _read(Path(row.storage_path)) == b"\x00binary\xff"


# --- publish failure after commit --------------------------------------------------------


@pytest.mark.asyncio
async def test_a_publish_failure_after_commit_is_loud_readable_and_repaired_by_the_sweep(root, caplog):
    session = FakeAsyncSession()
    with patch("llc.services.attachment_files.os.replace", side_effect=OSError("disk full")):
        row = await _upload(session)
    assert session.commits == 1 and not Path(row.storage_path).exists()
    assert any("committed but publishing" in r.getMessage() and r.levelname == "ERROR" for r in caplog.records)

    service = AttachmentService()
    got, content = await service.download(
        FakeAsyncSession(results=[FakeResult([row])]),
        attachment_id=str(row.id),
        work_item_id=_ITEM,
        company_id=_COMPANY,
    )
    assert content == b"hello"  # served from the staged copy, not a silent 404

    _age(_staged(root)[0])
    counts = await service.sweep_staging(FakeAsyncSession(results=[FakeResult([row])]))
    assert counts["published"] == 1 and _read(Path(row.storage_path)) == b"hello" and _staged(root) == []


@pytest.mark.asyncio
async def test_a_missing_file_with_nothing_staged_is_still_not_found(root):
    row = await _upload(FakeAsyncSession())
    Path(row.storage_path).unlink()
    with pytest.raises(AttachmentNotFound):
        await AttachmentService().download(
            FakeAsyncSession(results=[FakeResult([row])]),
            attachment_id=str(row.id),
            work_item_id=_ITEM,
            company_id=_COMPANY,
        )


# --- AC2: delete goes through the outbox --------------------------------------------------


def _delete_session(row, **kw) -> FakeAsyncSession:
    """A session answering the row lookup, then the outbox claim with whatever delete() enqueued."""
    session = FakeAsyncSession(
        results=[
            FakeResult([row]),
            lambda _stmt: [o for o in session.added if isinstance(o, LLCAttachmentFileDeletion)],
        ],
        **kw,
    )
    return session


async def _delete(session, row) -> None:
    await AttachmentService().delete(session, attachment_id=str(row.id), work_item_id=_ITEM, company_id=_COMPANY)


async def _uploaded(root: Path) -> LLCWorkItemAttachment:
    return await _upload(FakeAsyncSession())


def _entry(path: Path | str, root: Path, **kw) -> LLCAttachmentFileDeletion:
    fields = {"root_id": outbox.storage_root_id(root), "attachment_id": uuid.uuid4(), "company_id": uuid.uuid4()}
    return LLCAttachmentFileDeletion(id=uuid.uuid4(), storage_path=str(path), **{**fields, **kw})


@pytest.mark.asyncio
async def test_delete_records_the_removal_in_the_same_transaction_and_unlinks_after_commit(root):
    row = await _uploaded(root)
    path = Path(row.storage_path)
    on_disk_at_commit: list[bool] = []

    def at_commit(_n: int):
        on_disk_at_commit.append(path.exists())

    session = _delete_session(row, commit_error=at_commit)
    await _delete(session, row)

    assert on_disk_at_commit[0] is True  # the commit that deletes the row runs BEFORE the unlink
    entries = [o for o in session.added if isinstance(o, LLCAttachmentFileDeletion)]
    assert len(entries) == 1 and entries[0].storage_path == str(path) and entries[0].attachment_id == row.id
    assert entries[0].root_id == outbox.storage_root_id(root)
    assert row in session.deleted and entries[0] in session.deleted  # cleared once the file was gone
    assert not path.exists()


@pytest.mark.asyncio
async def test_a_failed_delete_commit_leaves_the_file_and_unlinks_nothing(root):
    row = await _uploaded(root)
    with pytest.raises(RuntimeError):
        await _delete(_delete_session(row, commit_error=RuntimeError("commit failed")), row)
    assert Path(row.storage_path).exists()


@pytest.mark.asyncio
async def test_a_forced_unlink_failure_leaves_an_outbox_row_that_a_retry_clears(root):
    row = await _uploaded(root)
    path = Path(row.storage_path)
    session = _delete_session(row)
    with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
        await _delete(session, row)
    entry = next(o for o in session.added if isinstance(o, LLCAttachmentFileDeletion))
    assert entry not in session.deleted and path.exists()
    assert entry.attempts == 1 and "PermissionError" in entry.last_error

    retry = FakeAsyncSession(results=[FakeResult([entry]), FakeResult([0]), FakeResult([0])])
    result = await AttachmentService().drain_removals(retry)
    assert result["removed"] == 1 and not path.exists() and entry in retry.deleted and entry.attempts == 2


@pytest.mark.asyncio
async def test_a_failure_in_the_request_path_drain_does_not_fail_a_committed_delete(root, caplog):
    row = await _uploaded(root)
    session = _delete_session(row, commit_error=lambda n: RuntimeError("db gone") if n >= 2 else None)
    await _delete(session, row)  # must not raise: the row delete is already durable
    assert row in session.deleted and session.rollbacks == 1  # the entry stays for the sweep
    assert any("sweep will retry" in r.getMessage() and r.levelname == "ERROR" for r in caplog.records)


@pytest.mark.asyncio
async def test_a_lost_race_drains_nothing_and_unlinks_nothing(root):
    """Another worker holds the entry (SKIP LOCKED hides it): this drain claims nothing."""
    victim = root / "t" / "keep.txt"
    victim.parent.mkdir()
    _write(victim, b"keep")
    assert (
        await outbox.drain_removals(FakeAsyncSession(results=[FakeResult([])]), root, outbox.storage_root_id(root)) == 0
    )
    assert victim.exists()


def test_the_claim_is_skip_locked_oldest_attempt_first_and_excludes_stuck_and_foreign_entries(root):
    from sqlalchemy.dialects import postgresql

    sql = str(
        outbox.claim_statement("node-a").compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "FOR UPDATE SKIP LOCKED" in sql and "NULLS FIRST" in sql
    assert "root_id = 'node-a'" in sql and "stuck_at IS NULL" in sql and "last_attempt_at <=" in sql


@pytest.mark.asyncio
async def test_the_claim_runs_on_sqlite_and_selects_only_what_this_node_may_drain(tmp_path):
    from datetime import timedelta

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from autobot_shared.time_utils import now_utc

    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        f"sqlite+aiosqlite:///{tmp_path / 'o.db'}"
    )
    async with engine.begin() as conn:
        await conn.run_sync(LLCAttachmentFileDeletion.__table__.create)
    now = now_utc()
    mine = [
        _entry(f"/x/{n}", tmp_path, root_id="me", **kw)
        for n, kw in enumerate(
            [{}, {"last_attempt_at": now - timedelta(days=1)}, {"last_attempt_at": now}, {"stuck_at": now}]
        )
    ]
    foreign = _entry("/x/f", tmp_path, root_id="other")
    made = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False
    )
    async with made() as session:
        session.add_all([*mine, foreign])
        await session.commit()
        claimed = (await session.execute(outbox.claim_statement("me"))).scalars().all()
    await engine.dispose()
    # never-attempted first, then the older attempt; not the just-tried one (backoff), the stuck one or the foreign one
    assert [e.storage_path for e in claimed] == ["/x/0", "/x/1"]


@pytest.mark.asyncio
async def test_a_stuck_entry_is_kept_marked_skipped_and_counted(root):
    from llc.storage_root import LLC_ATTACHMENT_REMOVAL_MAX_ATTEMPTS

    entry = _entry("/etc/passwd", root, attempts=LLC_ATTACHMENT_REMOVAL_MAX_ATTEMPTS - 1)
    session = FakeAsyncSession(results=[FakeResult([entry]), FakeResult([1]), FakeResult([0])])
    result = await AttachmentService().drain_removals(session)
    assert entry.stuck_at is not None and entry not in session.deleted and "ValueError" in entry.last_error
    assert result == {"removed": 0, "stuck": 1, "other_root": 0}


@pytest.mark.asyncio
async def test_a_failing_entry_does_not_stop_a_later_one_in_the_same_drain(root):
    bad = _entry("/etc/passwd", root)
    good_file = root / "t" / "a.txt"
    good_file.parent.mkdir()
    _write(good_file, b"x")
    good = _entry(good_file, root)
    session = FakeAsyncSession(results=[FakeResult([bad, good]), FakeResult([0]), FakeResult([0])])
    result = await AttachmentService().drain_removals(session)
    assert result["removed"] == 1 and not good_file.exists() and bad not in session.deleted


@pytest.mark.asyncio
async def test_a_missing_parent_directory_is_a_failure_and_the_entry_stays(root):
    """An unmounted volume looks like 'nothing there'; clearing the entry would strand the real file."""
    gone = root / _COMPANY / _ITEM / f"{uuid.uuid4()}.txt"  # tenant directory does not exist
    entry = _entry(gone, root)
    session = FakeAsyncSession(results=[FakeResult([entry]), FakeResult([0]), FakeResult([0])])
    assert (await AttachmentService().drain_removals(session))["removed"] == 0
    assert entry not in session.deleted and "FileNotFoundError" in entry.last_error and entry.attempts == 1


@pytest.mark.asyncio
async def test_a_missing_root_is_a_failure_and_the_entry_stays(tmp_path):
    absent = tmp_path / "unmounted"
    entry = _entry(absent / "t" / "a.txt", absent)
    session = FakeAsyncSession(results=[FakeResult([entry])])
    with patch("llc.services.attachment_outbox.validate_path", return_value=absent / "t" / "a.txt"):
        assert await outbox.drain_removals(session, absent, entry.root_id) == 0
    assert entry not in session.deleted and "storage root is not present" in entry.last_error


@pytest.mark.asyncio
async def test_a_file_missing_under_a_present_parent_still_counts_as_removed(root):
    parent = root / _COMPANY / _ITEM
    parent.mkdir(parents=True)
    entry = _entry(parent / f"{uuid.uuid4()}.txt", root)
    session = FakeAsyncSession(results=[FakeResult([entry])])
    assert await outbox.drain_removals(session, root, entry.root_id) == 1 and entry in session.deleted


@pytest.mark.asyncio
async def test_the_sweep_warns_with_a_count_and_no_path_when_entries_belong_to_another_node(caplog):
    from unittest.mock import AsyncMock

    from llc.scheduler import attachment_file_sweep as sweep

    service = AsyncMock()
    service.drain_removals.return_value = {"removed": 0, "stuck": 0, "other_root": 3}
    service.sweep_staging.return_value = {}
    with (
        patch.object(sweep, "AttachmentService", return_value=service),
        patch.object(sweep, "get_async_session_factory", return_value=FakeAsyncSession),
    ):
        await sweep._async_sweep()
    warned = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("3 attachment file removal(s) belong to another node" in m for m in warned)


def test_the_root_identity_follows_the_root_and_the_override(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert outbox.storage_root_id(a) == outbox.storage_root_id(a) != outbox.storage_root_id(b)
    with patch("llc.services.attachment_outbox.LLC_ATTACHMENT_ROOT_ID_OVERRIDE", "shared-volume"):
        assert outbox.storage_root_id(a) == outbox.storage_root_id(b) == "shared-volume"


# --- the outbox is bounded by the storage root --------------------------------------------


@pytest.mark.asyncio
async def test_an_outbox_path_outside_the_root_is_refused_and_recorded(root, tmp_path_factory):
    outside = tmp_path_factory.mktemp("elsewhere") / "keep.txt"
    _write(outside, b"keep")
    entry = _entry(outside, root)
    session = FakeAsyncSession(results=[FakeResult([entry]), FakeResult([0]), FakeResult([0])])
    assert (await AttachmentService().drain_removals(session))["removed"] == 0
    assert _read(outside) == b"keep" and entry not in session.deleted and "ValueError" in entry.last_error


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["root", "staging"])
async def test_an_outbox_path_naming_the_root_or_staging_is_refused(root, target):
    victim = root / files.STAGING_DIRNAME / f"{uuid.uuid4()}.part" if target == "staging" else root
    victim.parent.mkdir(parents=True, exist_ok=True)
    if target == "staging":
        _write(victim, b"staged")
    entry = _entry(victim, root)
    session = FakeAsyncSession(results=[FakeResult([entry]), FakeResult([0]), FakeResult([0])])
    assert (await AttachmentService().drain_removals(session))["removed"] == 0
    assert victim.exists() and entry.last_error


# --- the staging sweep -------------------------------------------------------------------


def _age(path: Path, seconds: int = 7200) -> None:
    old = path.stat().st_mtime - seconds
    os.utime(path, (old, old))


def _stage(root: Path, age: int = 7200) -> Path:
    staged = files.stage_bytes(root, str(uuid.uuid4()), b"x")
    _age(staged, age)
    return staged


def _raw_stage(root: Path, name: str) -> Path:
    path = root / files.STAGING_DIRNAME / name
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(path, b"x")
    return path


@pytest.mark.asyncio
async def test_the_sweep_quarantines_an_old_staged_file_with_no_row_and_deletes_nothing(root):
    orphan = _stage(root)
    young = _stage(root, age=0)
    stray = _raw_stage(root, "notes.txt")  # not named for an attachment
    _age(stray)
    tenant = root / _COMPANY / _ITEM
    tenant.mkdir(parents=True)
    published = tenant / f"{uuid.uuid4()}.txt"
    _write(published, b"live")

    counts = await AttachmentService().sweep_staging(FakeAsyncSession(default_result=FakeResult([])))

    assert counts["quarantined"] == 1 and counts["waiting"] == 1 and counts["published"] == 0
    assert not orphan.exists() and young.exists() and stray.exists() and published.exists()
    quarantined = list((root / files.STAGING_DIRNAME / files.QUARANTINE_DIRNAME).iterdir())
    assert len(quarantined) == 1 and _read(quarantined[0]) == b"x"


@pytest.mark.asyncio
async def test_a_staged_file_with_a_row_is_published_whatever_its_age(root):
    row = await _upload(FakeAsyncSession())
    Path(row.storage_path).unlink()
    staged = files.stage_bytes(root, str(row.id), b"hello")  # age 0: the row is the proof, not the clock
    counts = await AttachmentService().sweep_staging(FakeAsyncSession(results=[FakeResult([row])]))
    assert counts["published"] == 1 and _read(Path(row.storage_path)) == b"hello" and not staged.exists()


@pytest.mark.asyncio
async def test_the_sweep_locks_the_row_while_it_publishes(root):
    row = await _upload(FakeAsyncSession())
    Path(row.storage_path).unlink()
    files.stage_bytes(root, str(row.id), b"hello")
    session = FakeAsyncSession(results=[FakeResult([row])])
    await AttachmentService().sweep_staging(session)
    assert "FOR UPDATE" in str(session.statements[0]) and "SKIP LOCKED" not in str(session.statements[0])


def test_a_publish_that_lost_the_race_to_another_publisher_is_not_a_failure(root):
    dest = root / "t" / "a.txt"
    dest.parent.mkdir()
    _write(dest, b"done")
    files.publish_staged(root / files.STAGING_DIRNAME / "gone.part", dest)  # staged file already moved: no error
    with pytest.raises(FileNotFoundError):
        files.publish_staged(root / files.STAGING_DIRNAME / "gone.part", dest.parent / "other.txt")


@pytest.mark.asyncio
@pytest.mark.parametrize(("published", "key"), [(b"hello", "duplicate"), (b"DIFFERENT", "conflict")])
async def test_both_copies_existing_is_counted_and_neither_is_deleted(root, published, key):
    row = await _upload(FakeAsyncSession())
    _write(Path(row.storage_path), published)
    staged = files.stage_bytes(root, str(row.id), b"hello")
    counts = await AttachmentService().sweep_staging(FakeAsyncSession(results=[FakeResult([row])]))
    assert counts[key] == 1 and staged.exists() and _read(Path(row.storage_path)) == published


@pytest.mark.asyncio
async def test_the_sweep_never_reads_outside_the_staging_directory(root):
    (root / "evil").mkdir()
    victim = root / "evil" / f"{uuid.uuid4()}.part"
    _write(victim, b"x")
    _age(victim)
    link = root / files.STAGING_DIRNAME
    link.mkdir()
    (link / f"{uuid.uuid4()}.part").symlink_to(victim)
    await AttachmentService().sweep_staging(FakeAsyncSession(default_result=FakeResult([])))
    assert victim.exists()


def test_staging_is_fsynced_before_the_commit_and_the_directory_after_the_rename(root):
    with patch("llc.services.attachment_files.os.fsync") as fsync:
        staged = files.stage_bytes(root, str(uuid.uuid4()), b"x")
        assert fsync.call_count == 2  # the file, then its directory
        fsync.reset_mock()
        files.publish_staged(staged, root / "t" / "a.txt")
        assert fsync.call_count == 1


# --- wiring ------------------------------------------------------------------------------


def test_the_sweep_is_scheduled_with_an_env_backed_interval():
    """celery_app is stubbed under pytest (see celery_beat_registration_test.py), so read the source."""
    src = (Path(__file__).resolve().parents[2] / "celery_app.py").read_text(encoding="utf-8")
    entry = src[src.index('"llc-attachment-file-sweep"') :].split("},", 1)[0]
    assert "llc.scheduler.attachment_file_sweep.run_attachment_file_sweep" in entry
    assert "timedelta(seconds=LLC_ATTACHMENT_SWEEP_INTERVAL_SECONDS)" in entry


def test_the_task_is_registered_on_the_scheduler_package():
    import llc.scheduler as scheduler
    from llc.scheduler.attachment_file_sweep import run_attachment_file_sweep

    assert scheduler.run_attachment_file_sweep is run_attachment_file_sweep


def test_module_constants_agree_with_the_registry_defaults_and_floors():
    """Defaults live in code and in the registry; this ties the two homes together (#19756)."""
    import autobot_shared.env_registry_llc  # noqa: F401
    from autobot_shared import env_registry
    from llc import storage_root as sr

    pairs = {
        "AUTOBOT_LLC_ATTACHMENT_STAGING_MAX_AGE_SECONDS": (sr.LLC_ATTACHMENT_STAGING_MAX_AGE_SECONDS, 300),
        "AUTOBOT_LLC_ATTACHMENT_SWEEP_INTERVAL_SECONDS": (sr.LLC_ATTACHMENT_SWEEP_INTERVAL_SECONDS, 30),
        "AUTOBOT_LLC_ATTACHMENT_REMOVAL_MAX_ATTEMPTS": (sr.LLC_ATTACHMENT_REMOVAL_MAX_ATTEMPTS, 1),
        "AUTOBOT_LLC_ATTACHMENT_REMOVAL_RETRY_SECONDS": (sr.LLC_ATTACHMENT_REMOVAL_RETRY_SECONDS, 30),
    }
    for name, (value, floor) in pairs.items():
        spec = env_registry.REGISTRY[name]
        assert spec.range == (floor, None), name
        assert value == spec.default, name
