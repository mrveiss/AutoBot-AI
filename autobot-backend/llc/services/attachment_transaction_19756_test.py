# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Attachment upload follows its database transaction (#19756): stage, commit, publish."""

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from llc.services.attachment_service import AttachmentNotFound, AttachmentService
from llc.services.attachment_test_support_19756 import (  # noqa: F401
    _COMPANY,
    _ITEM,
    _age,
    _published,
    _read,
    _staged,
    _upload,
    attachment_root,
)
from testkit.fake_async_session import FakeAsyncSession, FakeResult


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
    assert seen[0][0] == [] and len(seen[0][1]) == 1  # the first commit is the row; the second ends the publish lock
    assert [Path(row.storage_path)] == _published(root)
    assert _staged(root) == []


@pytest.mark.asyncio
async def test_upload_stores_the_sha256_of_the_content(root):
    row = await _upload(FakeAsyncSession(), content=b"\x00binary\xff", filename="blob.bin")
    assert row.sha256 == hashlib.sha256(b"\x00binary\xff").hexdigest()
    assert _read(Path(row.storage_path)) == b"\x00binary\xff"


@pytest.mark.asyncio
async def test_a_publish_failure_after_commit_is_loud_readable_and_repaired_by_the_sweep(root, caplog):
    session = FakeAsyncSession()
    with patch("llc.services.attachment_files.os.replace", side_effect=OSError("disk full")):
        row = await _upload(session)
    assert session.commits == 2 and not Path(row.storage_path).exists()
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
