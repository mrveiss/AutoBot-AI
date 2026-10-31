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


async def _uploaded(root: Path) -> LLCWorkItemAttachment:
    return await _upload(FakeAsyncSession())


@pytest.mark.asyncio
async def test_delete_records_the_removal_in_the_same_transaction_and_unlinks_after_commit(root):
    row = await _uploaded(root)
    path = Path(row.storage_path)
    on_disk_at_commit: list[bool] = []

    def at_commit(_n: int):
        on_disk_at_commit.append(path.exists())

    session = FakeAsyncSession(results=[FakeResult([row])], commit_error=at_commit)
    await AttachmentService().delete(session, attachment_id=str(row.id), work_item_id=_ITEM, company_id=_COMPANY)

    assert on_disk_at_commit[0] is True  # the commit that deletes the row runs BEFORE the unlink
    entries = [o for o in session.added if isinstance(o, LLCAttachmentFileDeletion)]
    assert len(entries) == 1 and entries[0].storage_path == str(path) and entries[0].attachment_id == row.id
    assert row in session.deleted and entries[0] in session.deleted  # cleared once the file was gone
    assert not path.exists()


@pytest.mark.asyncio
async def test_a_failed_delete_commit_leaves_the_file_and_unlinks_nothing(root):
    row = await _uploaded(root)
    session = FakeAsyncSession(results=[FakeResult([row])], commit_error=RuntimeError("commit failed"))
    with pytest.raises(RuntimeError):
        await AttachmentService().delete(session, attachment_id=str(row.id), work_item_id=_ITEM, company_id=_COMPANY)
    assert Path(row.storage_path).exists()


@pytest.mark.asyncio
async def test_a_forced_unlink_failure_leaves_an_outbox_row_that_a_retry_clears(root):
    row = await _uploaded(root)
    path = Path(row.storage_path)
    session = FakeAsyncSession(results=[FakeResult([row])])
    with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
        await AttachmentService().delete(session, attachment_id=str(row.id), work_item_id=_ITEM, company_id=_COMPANY)
    entry = next(o for o in session.added if isinstance(o, LLCAttachmentFileDeletion))
    assert entry not in session.deleted and path.exists()
    assert entry.attempts == 1 and "PermissionError" in entry.last_error

    retry = FakeAsyncSession(results=[FakeResult([entry])])
    assert await AttachmentService().drain_removals(retry) == 1
    assert not path.exists() and entry in retry.deleted and entry.attempts == 2


# --- the outbox is bounded by the storage root --------------------------------------------


@pytest.mark.asyncio
async def test_an_outbox_path_outside_the_root_is_refused_and_recorded(root, tmp_path_factory):
    outside = tmp_path_factory.mktemp("elsewhere") / "keep.txt"
    _write(outside, b"keep")
    entry = LLCAttachmentFileDeletion(
        id=uuid.uuid4(), attachment_id=uuid.uuid4(), company_id=uuid.uuid4(), storage_path=str(outside)
    )
    session = FakeAsyncSession(results=[FakeResult([entry])])
    assert await AttachmentService().drain_removals(session) == 0
    assert _read(outside) == b"keep" and entry not in session.deleted
    assert "ValueError" in entry.last_error


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["root", "staging"])
async def test_an_outbox_path_naming_the_root_or_staging_is_refused(root, target):
    victim = root / files.STAGING_DIRNAME / f"{uuid.uuid4()}.part" if target == "staging" else root
    victim.parent.mkdir(parents=True, exist_ok=True)
    if target == "staging":
        _write(victim, b"staged")
    entry = LLCAttachmentFileDeletion(
        id=uuid.uuid4(), attachment_id=uuid.uuid4(), company_id=uuid.uuid4(), storage_path=str(victim)
    )
    assert await AttachmentService().drain_removals(FakeAsyncSession(results=[FakeResult([entry])])) == 0
    assert victim.exists() and entry.last_error


# --- the staging sweep -------------------------------------------------------------------


def _age(path: Path, seconds: int = 7200) -> None:
    old = path.stat().st_mtime - seconds
    os.utime(path, (old, old))


def _stage(root: Path, name: str | None = None, age: int = 7200) -> Path:
    attachment_id = name or str(uuid.uuid4())
    staged = files.stage_bytes(root, attachment_id, b"x") if name is None else _raw_stage(root, name)
    _age(staged, age)
    return staged


def _raw_stage(root: Path, name: str) -> Path:
    path = root / files.STAGING_DIRNAME / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


@pytest.mark.asyncio
async def test_the_sweep_unlinks_an_old_staged_file_with_no_row_and_nothing_else(root):
    orphan = _stage(root)
    young = _stage(root, age=0)
    stray = _raw_stage(root, "notes.txt")  # not named for an attachment
    _age(stray)
    tenant = root / _COMPANY / _ITEM
    tenant.mkdir(parents=True)
    published = tenant / f"{uuid.uuid4()}.txt"
    _write(published, b"live")
    _age(published)

    session = FakeAsyncSession(default_result=FakeResult([]))
    counts = await AttachmentService().sweep_staging(session)

    assert counts == {"published": 0, "discarded": 1, "skipped": 0, "failed": 0}
    assert not orphan.exists() and young.exists() and stray.exists() and published.exists()


@pytest.mark.asyncio
async def test_the_sweep_never_reads_outside_the_staging_directory(root):
    (root / "evil").mkdir()
    victim = root / "evil" / f"{uuid.uuid4()}.part"
    _write(victim, b"x")
    _age(victim)
    link = root / files.STAGING_DIRNAME
    link.mkdir()
    (link / f"{uuid.uuid4()}.part").symlink_to(victim)
    session = FakeAsyncSession(default_result=FakeResult([]))
    await AttachmentService().sweep_staging(session)
    assert victim.exists()


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
