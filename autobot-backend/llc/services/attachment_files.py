# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""File-side steps of attachment storage: staging, publishing, the deletion outbox (#19756).

An upload is stage -> commit -> publish. The bytes are written under ``<root>/.staging``, the
row is committed, and only then is the file moved to its final path -- so a failed commit never
leaves a file where a reader could find it, and a file at its final path always has a row.

A delete is the reverse: the removal is recorded in ``llc_attachment_file_deletions`` in the
same transaction as the row delete, and :func:`drain_removals` retries until the file is gone.

Nothing here decides *what* to delete. The outbox lists only files whose row a caller deleted
(#17038: no retention policy changes), and :func:`sweep_staging` reads only the staging
directory. Every path is validated against the storage root before it is touched.
"""

import hashlib
import os
import time
import uuid
from pathlib import Path
from typing import Callable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import validate_path
from autobot_shared.time_utils import now_utc
from llc.models.attachment import LLCWorkItemAttachment
from llc.models.attachment_deletion import LLCAttachmentFileDeletion

logger = get_logger(__name__)

STAGING_DIRNAME = ".staging"
STAGED_SUFFIX = ".part"
#: Outbox entries handled per drain, so one beat tick has a bounded amount of work.
MAX_REMOVALS_PER_DRAIN = 100


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def staging_dir(root: Path) -> Path:
    return root.resolve() / STAGING_DIRNAME


def staging_path(root: Path, attachment_id: str) -> Path:
    """Where an upload waits before its row is committed; a direct child of the staging dir."""
    directory = staging_dir(root)
    candidate = directory / f"{uuid.UUID(str(attachment_id))}{STAGED_SUFFIX}"
    staged = validate_path(str(candidate), allowed_roots=(str(directory),))
    if staged.parent != directory:
        raise ValueError(f"staging path is not a direct child of the staging directory: {staged}")
    return staged


def stage_bytes(root: Path, attachment_id: str, content: bytes) -> Path:
    staged = staging_path(root, attachment_id)
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(content)
    return staged


def publish(staged: Path, dest: Path) -> None:
    """Move a staged file to its final path. ``os.replace`` is atomic on one filesystem."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged, dest)


def removal_target(root: Path, storage_path: str) -> Path:
    """The file an outbox entry may remove: inside the root, and neither the root nor staging."""
    resolved_root = root.resolve()
    target = validate_path(storage_path, allowed_roots=(str(resolved_root),))
    if target == resolved_root or target.is_relative_to(staging_dir(root)):
        raise ValueError(f"outbox path is not an attachment file: {target}")
    return target


def enqueue_removal(session: AsyncSession, row: LLCWorkItemAttachment) -> LLCAttachmentFileDeletion:
    """Record the owed removal in the caller's transaction; it commits or rolls back with the row delete."""
    entry = LLCAttachmentFileDeletion(
        id=uuid.uuid4(), attachment_id=row.id, company_id=row.company_id, storage_path=row.storage_path
    )
    session.add(entry)
    return entry


def _attempt_removal(root: Path, entry: LLCAttachmentFileDeletion) -> bool:
    entry.attempts = (entry.attempts or 0) + 1
    entry.last_attempt_at = now_utc()
    try:
        removal_target(root, entry.storage_path).unlink(missing_ok=True)
    except (OSError, ValueError) as exc:
        entry.last_error = f"{type(exc).__name__}: {exc}"
        logger.error("#19756: attachment file removal %s failed (attempt %s): %s", entry.id, entry.attempts, exc)
        return False
    return True


async def drain_removals(session: AsyncSession, root: Path, entries: list[LLCAttachmentFileDeletion]) -> int:
    """Remove each entry's file; a cleared entry is deleted, a failed one keeps its error and stays."""
    cleared = 0
    for entry in entries:
        if _attempt_removal(root, entry):
            await session.delete(entry)
            cleared += 1
    await session.commit()
    return cleared


async def pending_removals(session: AsyncSession) -> list[LLCAttachmentFileDeletion]:
    result = await session.execute(
        sa.select(LLCAttachmentFileDeletion)
        .order_by(LLCAttachmentFileDeletion.created_at)
        .limit(MAX_REMOVALS_PER_DRAIN)
    )
    return list(result.scalars().all())


def _stale_staged_files(root: Path, max_age_seconds: int) -> list[Path]:
    directory = staging_dir(root)
    if not directory.is_dir():
        return []
    cutoff = time.time() - max_age_seconds
    found = []
    for entry in directory.iterdir():
        if entry.is_symlink() or not entry.is_file() or entry.suffix != STAGED_SUFFIX:
            continue
        if entry.stat().st_mtime <= cutoff:
            found.append(entry)
    return found


async def _resolve_staged(session: AsyncSession, staged: Path, resolve_dest: Callable) -> str:
    try:
        attachment_id = uuid.UUID(staged.stem)
    except ValueError:
        logger.warning("#19756: staging file %s is not named for an attachment; left alone", staged.name)
        return "skipped"
    row = (
        await session.execute(sa.select(LLCWorkItemAttachment).where(LLCWorkItemAttachment.id == attachment_id))
    ).scalar_one_or_none()
    if row is None:
        staged.unlink(missing_ok=True)
        return "discarded"
    dest = resolve_dest(row)
    if dest.exists():
        logger.warning("#19756: staged %s and published %s both exist; left alone", staged.name, dest)
        return "skipped"
    try:
        publish(staged, dest)
    except OSError as exc:
        logger.error("#19756: publishing staged attachment %s to %s failed: %s", attachment_id, dest, exc)
        return "failed"
    return "published"


async def sweep_staging(
    session: AsyncSession, root: Path, max_age_seconds: int, resolve_dest: Callable[[LLCWorkItemAttachment], Path]
) -> dict[str, int]:
    """Settle staging files older than the window, touching nothing outside the staging directory.

    A staged file whose row exists is a committed upload whose publish did not happen: it is
    published, never deleted. One with no row is the remains of an upload that did not commit.
    """
    counts = {"published": 0, "discarded": 0, "skipped": 0, "failed": 0}
    for staged in _stale_staged_files(root, max_age_seconds):
        counts[await _resolve_staged(session, staged, resolve_dest)] += 1
    return counts
