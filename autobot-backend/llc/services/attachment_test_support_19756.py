# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared helpers for the attachment transaction tests (#19756)."""

import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from llc.models.attachment import LLCWorkItemAttachment
from llc.models.attachment_deletion import LLCAttachmentFileDeletion
from llc.services import attachment_files as files
from llc.services import attachment_outbox as outbox
from llc.services.attachment_service import AttachmentService
from testkit.fake_async_session import FakeAsyncSession, FakeResult

_COMPANY = str(uuid.uuid4())
_ITEM = str(uuid.uuid4())


@pytest.fixture(name="root")
def attachment_root(tmp_path: Path):
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


def _answer_with_added_rows(session) -> None:
    """Let the row lock that upload() takes on publish see the row it just added."""
    if session.default_result is None:
        session.default_result = lambda _stmt: [o for o in session.added if isinstance(o, LLCWorkItemAttachment)]


async def _upload(session, content: bytes = b"hello", filename: str = "notes.txt") -> LLCWorkItemAttachment:
    _answer_with_added_rows(session)
    return await AttachmentService().upload(
        session, company_id=_COMPANY, work_item_id=_ITEM, filename=filename, content_type="text/plain", content=content
    )


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
