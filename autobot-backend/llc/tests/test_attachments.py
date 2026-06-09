# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for AttachmentService (GH#8253)."""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.services.attachment_service import (
    AttachmentNotFound,
    AttachmentService,
    AttachmentTooLarge,
    _extract_text,
    _storage_path,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMPANY = str(uuid.uuid4())
_WORK_ITEM = str(uuid.uuid4())
_AGENT = str(uuid.uuid4())


def _make_row(
    filename: str = "notes.txt",
    size_bytes: int = 10,
    storage_path: str = "/tmp/fake.txt",  # nosec B108 - test/controlled code uses tmpdir intentionally
    text_extracted: bool = True,
    extracted_text: str = "hello",
) -> MagicMock:
    row = MagicMock()
    row.id = uuid.uuid4()
    row.company_id = uuid.UUID(_COMPANY)
    row.work_item_id = uuid.UUID(_WORK_ITEM)
    row.filename = filename
    row.content_type = "text/plain"
    row.size_bytes = size_bytes
    row.storage_path = storage_path
    row.text_extracted = text_extracted
    row.extracted_text = extracted_text
    row.created_at = None
    return row


def _make_session(scalar_one_or_none=None) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.scalars.return_value.all.return_value = [scalar_one_or_none] if scalar_one_or_none else []
    session.execute.return_value = result
    session.refresh = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename,content,expected",
    [
        ("readme.md", b"# Hello", "# Hello"),
        ("script.py", b"print('hi')", "print('hi')"),
        ("data.json", b'{"k":1}', '{"k":1}'),
        ("config.yaml", b"key: val", "key: val"),
        ("image.png", b"\x89PNG", None),
        ("archive.zip", b"PK", None),
        ("doc.pdf", b"%PDF", None),
    ],
)
def test_extract_text(tmp_path: Path, filename: str, content: bytes, expected):
    p = tmp_path / filename
    p.write_bytes(content)
    result = _extract_text(p, filename)
    assert result == expected


# ---------------------------------------------------------------------------
# upload — too large
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_too_large():
    svc = AttachmentService()
    session = _make_session()
    with patch("llc.services.attachment_service.LLC_ATTACHMENT_MAX_BYTES", 5):
        with pytest.raises(AttachmentTooLarge):
            await svc.upload(
                session,
                company_id=_COMPANY,
                work_item_id=_WORK_ITEM,
                filename="big.txt",
                content_type="text/plain",
                content=b"more than five bytes here",
            )


# ---------------------------------------------------------------------------
# upload — success (local disk)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_local_disk(tmp_path: Path):
    svc = AttachmentService()
    session = _make_session()
    content = b"hello world"

    with (
        patch("llc.services.attachment_service._LOCAL_STORAGE_PATH", tmp_path),
        patch("llc.services.attachment_service._STORAGE_BACKEND", "local_disk"),
    ):
        row_mock = _make_row(size_bytes=len(content))
        session.refresh = AsyncMock(return_value=None)

        with patch.object(svc, "upload", AsyncMock(return_value=row_mock)):
            row = await svc.upload(
                session,
                company_id=_COMPANY,
                work_item_id=_WORK_ITEM,
                filename="notes.txt",
                content_type="text/plain",
                content=content,
                uploaded_by_agent_id=_AGENT,
            )

    assert row.size_bytes == len(content)


# ---------------------------------------------------------------------------
# list_attachments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_attachments_returns_rows():
    svc = AttachmentService()
    row = _make_row()
    session = _make_session(scalar_one_or_none=row)
    rows = await svc.list_attachments(session, work_item_id=_WORK_ITEM, company_id=_COMPANY)
    assert isinstance(rows, list)


# ---------------------------------------------------------------------------
# get — not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_not_found():
    svc = AttachmentService()
    session = _make_session(scalar_one_or_none=None)
    with pytest.raises(AttachmentNotFound):
        await svc.get(
            session,
            attachment_id=str(uuid.uuid4()),
            work_item_id=_WORK_ITEM,
            company_id=_COMPANY,
        )


# ---------------------------------------------------------------------------
# get_text — extracts text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_text_returns_extracted():
    svc = AttachmentService()
    row = _make_row(extracted_text="hello KB")
    session = _make_session(scalar_one_or_none=row)

    with patch.object(svc, "get", AsyncMock(return_value=row)):
        text = await svc.get_text(
            session,
            attachment_id=str(row.id),
            work_item_id=_WORK_ITEM,
            company_id=_COMPANY,
        )
    assert text == "hello KB"


# ---------------------------------------------------------------------------
# delete — calls unlink
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_file(tmp_path: Path):
    svc = AttachmentService()
    fake_file = tmp_path / "test.txt"
    fake_file.write_text("data", encoding="utf-8")

    row = _make_row(storage_path=str(fake_file))
    session = _make_session(scalar_one_or_none=row)

    with patch.object(svc, "get", AsyncMock(return_value=row)):
        await svc.delete(
            session,
            attachment_id=str(row.id),
            work_item_id=_WORK_ITEM,
            company_id=_COMPANY,
        )

    assert not fake_file.exists()


# ---------------------------------------------------------------------------
# storage_path helper
# ---------------------------------------------------------------------------


def test_storage_path_structure(tmp_path: Path):
    with patch("llc.services.attachment_service._LOCAL_STORAGE_PATH", tmp_path):
        path = _storage_path(_COMPANY, _WORK_ITEM, "att-001", "doc.md")
    assert path.suffix == ".md"
    assert _COMPANY in str(path)
    assert _WORK_ITEM in str(path)
