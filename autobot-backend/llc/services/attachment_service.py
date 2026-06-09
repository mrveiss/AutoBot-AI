# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Attachment service: storage, text extraction, CRUD (GH#8253).

Storage backend is selected by the ``LLC_STORAGE_BACKEND`` env var:
  ``local_disk`` (default) — writes to ``LLC_STORAGE_PATH`` (default
    ``~/.autobot/llc/attachments/``).
  ``s3`` — uses ``LLC_S3_BUCKET`` / ``LLC_S3_ENDPOINT`` / standard
    AWS credential env vars (not yet implemented; raises NotImplementedError).

Text-extractable extensions: .txt .md .py .ts .js .json .yaml .yml .toml .csv
Binary files are stored without extraction (text_extracted remains False).
"""

import logging
import os
import uuid
from pathlib import Path
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.attachment import LLCWorkItemAttachment

logger = logging.getLogger(__name__)

# Configurable max upload size (bytes). Default 20 MB.
_DEFAULT_MAX_BYTES = 20 * 1024 * 1024
LLC_ATTACHMENT_MAX_BYTES = int(os.getenv("LLC_ATTACHMENT_MAX_BYTES", str(_DEFAULT_MAX_BYTES)))

# Text-extractable suffix set (lowercase).
_TEXT_SUFFIXES = {".txt", ".md", ".py", ".ts", ".js", ".json", ".yaml", ".yml", ".toml", ".csv"}

_STORAGE_BACKEND = os.getenv("LLC_STORAGE_BACKEND", "local_disk")
_LOCAL_STORAGE_PATH = Path(os.getenv("LLC_STORAGE_PATH", str(Path.home() / ".autobot" / "llc" / "attachments")))


class AttachmentTooLarge(Exception):
    pass


class AttachmentNotFound(Exception):
    pass


class StorageBackendNotImplemented(Exception):
    pass


def _resolve_storage_root() -> Path:
    root = _LOCAL_STORAGE_PATH
    root.mkdir(parents=True, exist_ok=True)
    return root


def _storage_path(company_id: str, work_item_id: str, attachment_id: str, filename: str) -> Path:
    ext = Path(filename).suffix
    root = _resolve_storage_root()
    return root / company_id / work_item_id / f"{attachment_id}{ext}"


def _extract_text(path: Path, filename: str) -> Optional[str]:
    """Read file content for text-extractable types; return None otherwise."""
    suffix = Path(filename).suffix.lower()
    if suffix not in _TEXT_SUFFIXES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Text extraction failed for %s: %s", path, exc)
        return None


def _write_local(content: bytes, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)


def _read_local(path: Path) -> bytes:
    if not path.exists():
        raise AttachmentNotFound(f"File not found: {path}")
    return path.read_bytes()


def _delete_local(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Failed to delete %s: %s", path, exc)


class AttachmentService:
    """CRUD + storage for work item file attachments."""

    async def upload(
        self,
        session: AsyncSession,
        *,
        company_id: str,
        work_item_id: str,
        filename: str,
        content_type: str,
        content: bytes,
        uploaded_by_agent_id: Optional[str] = None,
        uploaded_by_user_id: Optional[str] = None,
    ) -> LLCWorkItemAttachment:
        if len(content) > LLC_ATTACHMENT_MAX_BYTES:
            raise AttachmentTooLarge(f"Upload exceeds limit: {len(content)} > {LLC_ATTACHMENT_MAX_BYTES} bytes")
        if _STORAGE_BACKEND != "local_disk":
            raise StorageBackendNotImplemented(f"Backend '{_STORAGE_BACKEND}' not implemented")

        attachment_id = str(uuid.uuid4())
        dest = _storage_path(company_id, work_item_id, attachment_id, filename)
        _write_local(content, dest)

        extracted = _extract_text(dest, filename)

        row = LLCWorkItemAttachment(
            id=uuid.UUID(attachment_id),
            company_id=uuid.UUID(company_id),
            work_item_id=uuid.UUID(work_item_id),
            uploaded_by_agent_id=uuid.UUID(uploaded_by_agent_id) if uploaded_by_agent_id else None,
            uploaded_by_user_id=uuid.UUID(uploaded_by_user_id) if uploaded_by_user_id else None,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            storage_path=str(dest),
            text_extracted=extracted is not None,
            extracted_text=extracted,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    async def list_attachments(
        self,
        session: AsyncSession,
        *,
        work_item_id: str,
        company_id: str,
    ) -> list[LLCWorkItemAttachment]:
        result = await session.execute(
            sa.select(LLCWorkItemAttachment).where(
                LLCWorkItemAttachment.work_item_id == uuid.UUID(work_item_id),
                LLCWorkItemAttachment.company_id == uuid.UUID(company_id),
            )
        )
        return list(result.scalars().all())

    async def get(
        self,
        session: AsyncSession,
        *,
        attachment_id: str,
        work_item_id: str,
        company_id: str,
    ) -> LLCWorkItemAttachment:
        result = await session.execute(
            sa.select(LLCWorkItemAttachment).where(
                LLCWorkItemAttachment.id == uuid.UUID(attachment_id),
                LLCWorkItemAttachment.work_item_id == uuid.UUID(work_item_id),
                LLCWorkItemAttachment.company_id == uuid.UUID(company_id),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise AttachmentNotFound(attachment_id)
        return row

    async def download(
        self,
        session: AsyncSession,
        *,
        attachment_id: str,
        work_item_id: str,
        company_id: str,
    ) -> tuple[LLCWorkItemAttachment, bytes]:
        row = await self.get(
            session,
            attachment_id=attachment_id,
            work_item_id=work_item_id,
            company_id=company_id,
        )
        content = _read_local(Path(row.storage_path))
        return row, content

    async def get_text(
        self,
        session: AsyncSession,
        *,
        attachment_id: str,
        work_item_id: str,
        company_id: str,
    ) -> Optional[str]:
        row = await self.get(
            session,
            attachment_id=attachment_id,
            work_item_id=work_item_id,
            company_id=company_id,
        )
        return row.extracted_text

    async def delete(
        self,
        session: AsyncSession,
        *,
        attachment_id: str,
        work_item_id: str,
        company_id: str,
    ) -> None:
        row = await self.get(
            session,
            attachment_id=attachment_id,
            work_item_id=work_item_id,
            company_id=company_id,
        )
        _delete_local(Path(row.storage_path))
        await session.delete(row)
        await session.commit()
