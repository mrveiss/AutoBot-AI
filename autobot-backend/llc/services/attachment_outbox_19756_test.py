# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Attachment delete goes through the deletion outbox (#19756)."""

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from llc.models.attachment import LLCWorkItemAttachment
from llc.models.attachment_deletion import LLCAttachmentFileDeletion
from llc.services import attachment_files as files
from llc.services import attachment_outbox as outbox
from llc.services.attachment_service import AttachmentNotFound, AttachmentService
from llc.services.attachment_test_support_19756 import (  # noqa: F401
    _COMPANY,
    _ITEM,
    _delete,
    _delete_session,
    _entry,
    _published,
    _read,
    _staged,
    _upload,
    _uploaded,
    _write,
    attachment_root,
)
from testkit.fake_async_session import FakeAsyncSession, FakeResult


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


@pytest.mark.asyncio
async def test_foreign_stuck_entries_are_counted_as_another_nodes(root):
    session = FakeAsyncSession(results=[FakeResult([0]), FakeResult([2])])
    assert await outbox.outbox_counts(session, "me") == {"stuck": 0, "other_root": 2}
    from sqlalchemy.dialects import postgresql

    other_sql = str(session.statements[1].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "root_id != 'me'" in other_sql and "stuck_at" not in other_sql


@pytest.mark.asyncio
async def test_a_publish_failure_then_a_delete_removes_the_staged_bytes(root):
    with patch("llc.services.attachment_files.os.replace", side_effect=OSError("disk full")):
        row = await _upload(FakeAsyncSession())
    staged = files.staging_path(root, str(row.id))
    assert staged.exists()

    session = _delete_session(row)
    await _delete(session, row)

    entries = [o for o in session.added if isinstance(o, LLCAttachmentFileDeletion)]
    assert {e.storage_path for e in entries} == {row.storage_path, str(staged)}
    assert not staged.exists() and all(e in session.deleted for e in entries)
    assert not (root / files.STAGING_DIRNAME / files.QUARANTINE_DIRNAME).exists()


@pytest.mark.asyncio
async def test_a_delete_with_nothing_staged_enqueues_only_the_published_file(root):
    row = await _uploaded(root)
    session = _delete_session(row)
    await _delete(session, row)
    assert len([o for o in session.added if isinstance(o, LLCAttachmentFileDeletion)]) == 1


@pytest.mark.asyncio
async def test_a_delete_that_won_the_publish_race_removes_the_staged_file_through_the_same_route(root):
    session = FakeAsyncSession(default_result=FakeResult([]))  # upload()'s row lock finds nothing: deleted first
    with pytest.raises(AttachmentNotFound):
        await AttachmentService().upload(
            session, company_id=_COMPANY, work_item_id=_ITEM, filename="a.txt", content_type="text/plain", content=b"x"
        )
    (staged,) = _staged(root)
    row = LLCWorkItemAttachment(
        id=uuid.UUID(staged.stem),
        company_id=uuid.UUID(_COMPANY),
        work_item_id=uuid.UUID(_ITEM),
        filename="a.txt",
        storage_path=str(root / _COMPANY / _ITEM / f"{staged.stem}.txt"),
    )
    await _delete(_delete_session(row), row)
    assert _staged(root) == [] and _published(root) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["other-id", "quarantine", "staging-other-name"])
async def test_a_forged_entry_cannot_reach_anything_else_under_staging(root, kind):
    mine = uuid.uuid4()
    staging = root / files.STAGING_DIRNAME
    victims = {
        "other-id": staging / f"{uuid.uuid4()}.part",
        "quarantine": staging / files.QUARANTINE_DIRNAME / f"{mine}.123.part",
        "staging-other-name": staging / "notes.txt",
    }
    victim = victims[kind]
    victim.parent.mkdir(parents=True, exist_ok=True)
    _write(victim, b"keep")
    entry = _entry(victim, root, attachment_id=mine)
    session = FakeAsyncSession(results=[FakeResult([entry])])
    assert await outbox.drain_removals(session, root, entry.root_id) == 0
    assert victim.exists() and entry not in session.deleted and "ValueError" in entry.last_error


@pytest.mark.asyncio
async def test_the_entrys_own_staged_file_is_removable_but_not_through_another_attachments_entry(root):
    mine, other = uuid.uuid4(), uuid.uuid4()
    staged = files.stage_bytes(root, str(mine), b"x")
    refused = _entry(staged, root, attachment_id=other)
    allowed = _entry(staged, root, attachment_id=mine)
    session = FakeAsyncSession(results=[FakeResult([refused])])
    assert await outbox.drain_removals(session, root, refused.root_id) == 0 and staged.exists()
    session = FakeAsyncSession(results=[FakeResult([allowed])])
    assert await outbox.drain_removals(session, root, allowed.root_id) == 1 and not staged.exists()
