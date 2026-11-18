# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The attachment staging sweep settles staged and quarantined files (#19756)."""

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from llc.services import attachment_files as files
from llc.services.attachment_service import AttachmentNotFound, AttachmentService
from llc.services.attachment_test_support_19756 import (  # noqa: F401
    _COMPANY,
    _ITEM,
    _age,
    _published,
    _raw_stage,
    _read,
    _stage,
    _staged,
    _upload,
    _write,
    attachment_root,
)
from testkit.fake_async_session import FakeAsyncSession, FakeResult


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


@pytest.mark.asyncio
async def test_an_io_error_on_one_staged_file_does_not_stop_the_files_after_it(root):
    first, second = uuid.uuid4(), uuid.uuid4()
    for attachment_id in (first, second):
        files.stage_bytes(root, str(attachment_id), b"x")
    outcomes = iter([OSError("unreadable"), "published"])

    async def settle(*_args, **_kw):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    session = FakeAsyncSession()
    with patch("llc.services.attachment_files._settle", settle):
        counts = await files.sweep_staging(session, root, 3600, lambda row: root)
    assert counts["failed"] == 1 and counts["published"] == 1 and session.rollbacks == 1


@pytest.mark.asyncio
async def test_a_quarantined_file_whose_row_was_committed_late_is_restored(root):
    """An upload that stalled past the window: the sweep quarantined its file, then the commit landed."""
    row = await _upload(FakeAsyncSession())
    Path(row.storage_path).unlink()
    staged = files.stage_bytes(root, str(row.id), b"hello")
    _age(staged)
    await AttachmentService().sweep_staging(FakeAsyncSession(default_result=FakeResult([])))  # no row yet: quarantined
    assert not Path(row.storage_path).exists() and not staged.exists()

    counts = await AttachmentService().sweep_staging(FakeAsyncSession(default_result=FakeResult([row])))
    assert counts["restored"] == 1 and _read(Path(row.storage_path)) == b"hello"


@pytest.mark.asyncio
async def test_a_quarantined_file_with_no_row_stays_quarantined(root):
    staged = files.stage_bytes(root, str(uuid.uuid4()), b"x")
    _age(staged)
    session = FakeAsyncSession(default_result=FakeResult([]))
    await AttachmentService().sweep_staging(session)
    counts = await AttachmentService().sweep_staging(session)
    assert (
        counts["restored"] == 0 and len(list((root / files.STAGING_DIRNAME / files.QUARANTINE_DIRNAME).iterdir())) == 1
    )


@pytest.mark.asyncio
async def test_a_delete_that_won_the_race_stops_the_publish_from_recreating_the_file(root):
    """The row is gone by the time upload() locks it, so the staged file must not reach the final path."""
    session = FakeAsyncSession(default_result=FakeResult([]))  # the lock finds no row
    with pytest.raises(AttachmentNotFound):
        await AttachmentService().upload(
            session, company_id=_COMPANY, work_item_id=_ITEM, filename="a.txt", content_type="text/plain", content=b"x"
        )
    assert _published(root) == [] and len(_staged(root)) == 1
    assert "FOR UPDATE" in str(session.statements[0])
