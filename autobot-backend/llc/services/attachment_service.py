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

import asyncio
import os
import uuid
from pathlib import Path
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import validate_path
from llc.models.attachment import LLCWorkItemAttachment
from llc.services import attachment_files as files
from llc.services import attachment_outbox as outbox
from llc.storage_root import LLC_ATTACHMENT_STAGING_MAX_AGE_SECONDS, llc_local_storage_root

logger = get_logger(__name__)

# Configurable max upload size (bytes). Default 20 MB.
_DEFAULT_MAX_BYTES = 20 * 1024 * 1024
LLC_ATTACHMENT_MAX_BYTES = env_int("LLC_ATTACHMENT_MAX_BYTES", _DEFAULT_MAX_BYTES)

# Text-extractable suffix set (lowercase).
_TEXT_SUFFIXES = {".txt", ".md", ".py", ".ts", ".js", ".json", ".yaml", ".yml", ".toml", ".csv"}

_STORAGE_BACKEND = os.getenv("LLC_STORAGE_BACKEND", "local_disk")
#: #17302: one definition of the root, shared with `kb/artifact_ingestor.py`.
_LOCAL_STORAGE_PATH = llc_local_storage_root()


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


#: Upper bound on the extension copied from an uploaded filename (#17300).
_MAX_SUFFIX_LEN = 16


def _storage_path(company_id: str, work_item_id: str, attachment_id: str, filename: str) -> Path:
    """Where an attachment lives on disk, with every id proven to be a UUID first.

    #17300: this built `root / company_id / ...` from an unvalidated query
    parameter. `pathlib` discards everything left of an absolute segment, so
    `company_id="/tmp/evil"` did not traverse out of the root -- it *replaced*
    the root, which made this an arbitrary-write primitive rather than a
    traversal bug. The format check existed, in `upload()`, and ran three lines
    after the bytes had already been written.

    Parsing each id here is the real fix: a value that is not a UUID cannot
    become a path segment at all. The containment assertion below is
    deliberately redundant -- it states the property a reader can check without
    first reasoning about what `uuid.UUID` rejects.

    Raises:
        ValueError: if any id is not a UUID, or the result escapes the root.
    """
    safe = [str(uuid.UUID(str(part))) for part in (company_id, work_item_id, attachment_id)]
    # `Path(filename).suffix` is taken from the final name component, so it can
    # never contain a separator -- but it is attacker-supplied, so it is bounded
    # rather than trusted.
    ext = Path(filename).suffix[:_MAX_SUFFIX_LEN]
    root = _resolve_storage_root().resolve()
    # Confined to the TENANT directory, not the shared root (#17408 review).
    # `validate_path(..., allowed_roots=(root,))` was not enough: an extension
    # of fullwidth confusables normalises to `/../../..` and walks back to the
    # root itself, which `is_relative_to(root)` accepts. The file then lands at
    # `<root>/x` instead of `<root>/<company>/<item>/<attachment><ext>` --
    # outside its tenant's directory while still technically "in the root".
    #
    # The test that was supposed to cover this used FIVE confusable groups,
    # which climb ABOVE the root and are refused; the reviewer used three,
    # which stop exactly on it. The assertion passed for the wrong reason and
    # the defect sat one repetition away from it.
    tenant_dir = (root / safe[0] / safe[1]).resolve()
    candidate = tenant_dir / f"{safe[2]}{ext}"
    # #17300 AC3: containment goes through the house validator rather than a
    # local `is_relative_to`. The property is identical -- `validate_path`
    # resolves both sides and refuses anything not under `root` -- but routing
    # it here means this call site inherits `_canonicalize`'s
    # decode-before-resolve and the known-bypass coverage instead of a reader
    # having to re-derive that the UUID parse above makes the segments inert.
    # It raises ValueError on escape, which is the contract this function
    # already documented.
    dest = validate_path(str(candidate), allowed_roots=(str(tenant_dir),))
    # A direct child, not merely "somewhere under". Depth-1 traversal resolves
    # to the tenant directory ITSELF, which `allowed_roots` accepts -- a
    # directory is not a file path, and writing to it fails at a later and
    # less obvious point than refusing it here.
    #
    # This check is the load-bearing one, and `allowed_roots=(tenant_dir,)`
    # above is defence in depth rather than an independent guarantee: a
    # direct child of `tenant_dir` is necessarily inside it, so the narrower
    # `allowed_roots` cannot refuse anything this does not. Stated because a
    # mutation proves it -- widening `allowed_roots` back to the storage root
    # leaves every test passing. Kept anyway, so that removing either one
    # leaves a containment check standing.
    if dest.parent != tenant_dir:
        raise ValueError(f"attachment path is not a direct child of its work-item directory: {dest}")
    return dest


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


def _read_local(path: Path, staged: Optional[Path] = None) -> bytes:
    """Read the published file; fall back to the staged copy of a committed-but-unpublished upload."""
    if path.exists():
        return path.read_bytes()
    if staged is not None and staged.exists():
        logger.warning("#19756: %s is not published yet; serving its staged copy %s", path, staged)
        return staged.read_bytes()
    raise AttachmentNotFound(f"File not found: {path}")


def _dest_for_row(row: LLCWorkItemAttachment) -> Path:
    """The final path re-derived from the row's ids, so a stored string is never trusted as a destination."""
    return _storage_path(str(row.company_id), str(row.work_item_id), str(row.id), row.filename)


def _new_row(
    *,
    attachment_id: str,
    company_id: str,
    work_item_id: str,
    agent_id: Optional[uuid.UUID],
    user_id: Optional[uuid.UUID],
    filename: str,
    content_type: str,
    content: bytes,
    dest: Path,
    sha256: str,
    extracted: Optional[str],
) -> LLCWorkItemAttachment:
    return LLCWorkItemAttachment(
        id=uuid.UUID(attachment_id),
        company_id=uuid.UUID(company_id),
        work_item_id=uuid.UUID(work_item_id),
        uploaded_by_agent_id=agent_id,
        uploaded_by_user_id=user_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(content),
        sha256=sha256,
        storage_path=str(dest),
        text_extracted=extracted is not None,
        extracted_text=extracted,
    )


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
        # EVERY id is parsed before anything reaches the filesystem (#17300): a malformed one
        # raised after the write and left an orphaned file, repeatably -- a disk filler.
        uploaded_by_agent_uuid = uuid.UUID(uploaded_by_agent_id) if uploaded_by_agent_id else None
        uploaded_by_user_uuid = uuid.UUID(uploaded_by_user_id) if uploaded_by_user_id else None
        dest = _storage_path(company_id, work_item_id, attachment_id, filename)
        # Stage -> commit -> publish (#19756). Nothing reaches `dest` until the row is durable.
        staged = await asyncio.to_thread(files.stage_bytes, _resolve_storage_root(), attachment_id, content)
        row = _new_row(
            attachment_id=attachment_id,
            company_id=company_id,
            work_item_id=work_item_id,
            agent_id=uploaded_by_agent_uuid,
            user_id=uploaded_by_user_uuid,
            filename=filename,
            content_type=content_type,
            content=content,
            dest=dest,
            sha256=await asyncio.to_thread(files.sha256_hex, content),
            extracted=await asyncio.to_thread(_extract_text, staged, filename),
        )
        session.add(row)
        await self._commit_staged(session, staged)
        if not await self._publish_committed(session, staged, dest, attachment_id):
            raise AttachmentNotFound(attachment_id)
        await session.refresh(row)
        return row

    @staticmethod
    async def _commit_staged(session: AsyncSession, staged: Path) -> None:
        """Commit the row. On failure the staged file is kept, not unlinked.

        A commit that raises is not proof the row is absent (the connection can drop after the
        server committed), and unlinking would then destroy the only copy of committed content.
        The staging sweep settles it by asking whether the row exists.
        """
        try:
            await session.commit()
        except Exception:
            logger.error("#19756: attachment commit failed; staged file %s kept for the staging sweep", staged)
            raise

    @staticmethod
    async def _publish_committed(session: AsyncSession, staged: Path, dest: Path, attachment_id: str) -> bool:
        """Move the file into place while holding the row's lock; False if the row is already gone.

        The lock serialises the move with a concurrent delete: a delete that won leaves no row,
        and publishing then would recreate a file nothing refers to. In that case the staged
        copy is left for the sweep, which quarantines it.

        A failed move leaves a committed row whose file is still staged. That is not hidden: it
        is logged at error, readers are served from the staged copy (`_read_local`), and the
        staging sweep retries the move.
        """
        try:
            if await files.lock_attachment_row(session, uuid.UUID(attachment_id)) is None:
                logger.warning("#19756: attachment %s was deleted before publish; staged copy left", attachment_id)
                return False
            await asyncio.to_thread(files.publish_staged, staged, dest)
        except OSError as exc:
            logger.error(
                "#19756: attachment %s committed but publishing %s failed: %s; the staging sweep will retry",
                attachment_id,
                dest,
                exc,
            )
        finally:
            await session.commit()  # releases the row lock
        return True

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
        staged = files.staging_path(_resolve_storage_root(), str(row.id))
        content = await asyncio.to_thread(_read_local, Path(row.storage_path), staged)
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
        # The removal is recorded in this transaction (#19756); the unlink happens after it commits.
        root = _resolve_storage_root()
        entry_id = outbox.enqueue_removal(session, row, outbox.storage_root_id(root)).id
        await session.delete(row)
        await session.commit()
        await self._drain_after_delete(session, root, entry_id)

    @staticmethod
    async def _drain_after_delete(session: AsyncSession, root: Path, entry_id: uuid.UUID) -> None:
        """Best-effort unlink right after the delete committed.

        The row delete is already durable, so a failure here must not turn the request into a 500:
        it is logged and the entry stays in the outbox for the sweep.
        """
        try:
            await outbox.drain_removals(session, root, outbox.storage_root_id(root), only_id=entry_id)
        except Exception:
            logger.exception(
                "#19756: immediate file removal for outbox entry %s failed; the sweep will retry", entry_id
            )
            await session.rollback()

    async def drain_removals(self, session: AsyncSession) -> dict[str, int]:
        """Drain this node's outbox; returns {removed, stuck, other_root}."""
        root = _resolve_storage_root()
        root_id = outbox.storage_root_id(root)
        removed = await outbox.drain_removals(session, root, root_id)
        return {"removed": removed, **await outbox.outbox_counts(session, root_id)}

    async def sweep_staging(self, session: AsyncSession) -> dict[str, int]:
        """Publish committed-but-unpublished uploads; quarantine (never delete) stale uncommitted ones."""
        return await files.sweep_staging(
            session, _resolve_storage_root(), LLC_ATTACHMENT_STAGING_MAX_AGE_SECONDS, _dest_for_row
        )
