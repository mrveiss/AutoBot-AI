# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Deletion outbox for attachment files (#19756).

A delete records the owed file removal in ``llc_attachment_file_deletions`` in the same
transaction as the row delete; :func:`drain_removals` retries until the file is gone.

Safety properties, each of which has a test:

* **Only requested deletes.** Entries are written by ``AttachmentService.delete`` from the row
  a caller deleted; nothing else writes them (#17038).
* **Contained.** The path is validated against the storage root at drain time, so a legacy or
  tampered entry cannot reach outside it.
* **Owned.** An entry carries the storage identity of the node that wrote it, and only a node
  with that identity drains it. On another node a missing file proves nothing, so the entry is
  skipped, never cleared.
* **No starvation.** Entries are claimed oldest-attempt first with a retry gap; after
  ``AUTOBOT_LLC_ATTACHMENT_REMOVAL_MAX_ATTEMPTS`` failures an entry is marked stuck, kept, skipped
  and counted.
* **No double drain.** Claims use ``FOR UPDATE SKIP LOCKED``; a lost race simply drains nothing.
"""

import asyncio
import hashlib
import socket
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import validate_path
from autobot_shared.time_utils import now_utc
from llc.models.attachment import LLCWorkItemAttachment
from llc.models.attachment_deletion import LLCAttachmentFileDeletion as Entry
from llc.services.attachment_files import staging_dir
from llc.storage_root import (
    LLC_ATTACHMENT_REMOVAL_MAX_ATTEMPTS,
    LLC_ATTACHMENT_REMOVAL_RETRY_SECONDS,
    LLC_ATTACHMENT_ROOT_ID_OVERRIDE,
)

logger = get_logger(__name__)

#: Entries claimed per drain, so one beat tick has a bounded amount of work.
MAX_REMOVALS_PER_DRAIN = 100


def storage_root_id(root: Path) -> str:
    """The identity of the storage this node owns: the override, else a digest of host and root."""
    if LLC_ATTACHMENT_ROOT_ID_OVERRIDE:
        return LLC_ATTACHMENT_ROOT_ID_OVERRIDE
    return hashlib.sha256(f"{socket.gethostname()}\0{root.resolve()}".encode()).hexdigest()[:32]


def removal_target(root: Path, storage_path: str) -> Path:
    """The file an outbox entry may remove: inside the root, and neither the root nor staging."""
    resolved_root = root.resolve()
    target = validate_path(storage_path, allowed_roots=(str(resolved_root),))
    if target == resolved_root or target.is_relative_to(staging_dir(root)):
        raise ValueError(f"outbox path is not an attachment file: {target}")
    return target


def enqueue_removal(session: AsyncSession, row: LLCWorkItemAttachment, root_id: str) -> Entry:
    """Record the owed removal in the caller's transaction; it commits or rolls back with the row delete."""
    entry = Entry(
        id=uuid.uuid4(),
        attachment_id=row.id,
        company_id=row.company_id,
        storage_path=row.storage_path,
        root_id=root_id,
    )
    session.add(entry)
    return entry


def claim_statement(root_id: str, only_id: Optional[uuid.UUID] = None) -> sa.Select:
    """Entries this node may drain now, oldest attempt first, locked against a concurrent drain."""
    query = sa.select(Entry).where(Entry.root_id == root_id, Entry.stuck_at.is_(None))
    if only_id is not None:
        query = query.where(Entry.id == only_id)
    else:
        retry_before = now_utc() - timedelta(seconds=LLC_ATTACHMENT_REMOVAL_RETRY_SECONDS)
        query = query.where(sa.or_(Entry.last_attempt_at.is_(None), Entry.last_attempt_at <= retry_before))
    return (
        query.order_by(Entry.last_attempt_at.asc().nulls_first(), Entry.created_at)
        .limit(MAX_REMOVALS_PER_DRAIN)
        .with_for_update(skip_locked=True)
    )


def _unlink(root: Path, storage_path: str) -> None:
    """Remove the file; a file already gone under a present directory counts as removed.

    A missing root or parent directory is a failure, not success: an unmounted volume looks the
    same as "nothing there", and clearing the entry would leave the real file with no retry.
    """
    target = removal_target(root, storage_path)
    if not root.is_dir():
        raise FileNotFoundError(f"storage root is not present: {root}")
    if not target.parent.is_dir():
        raise FileNotFoundError(f"parent directory of the attachment file is not present: {target.parent}")
    target.unlink(missing_ok=True)


def _record_failure(entry: Entry, exc: Exception) -> None:
    entry.last_error = f"{type(exc).__name__}: {exc}"
    logger.error("#19756: attachment file removal %s failed (attempt %s): %s", entry.id, entry.attempts, exc)
    if entry.attempts >= LLC_ATTACHMENT_REMOVAL_MAX_ATTEMPTS:
        entry.stuck_at = now_utc()
        logger.error(
            "#19756: attachment file removal %s is stuck after %s attempts; kept for a person", entry.id, entry.attempts
        )


async def _attempt(session: AsyncSession, root: Path, entry: Entry) -> bool:
    entry.attempts = (entry.attempts or 0) + 1
    entry.last_attempt_at = now_utc()
    try:
        await asyncio.to_thread(_unlink, root, entry.storage_path)
    except (OSError, ValueError) as exc:
        _record_failure(entry, exc)
        return False
    await session.delete(entry)
    return True


async def drain_removals(session: AsyncSession, root: Path, root_id: str, only_id: Optional[uuid.UUID] = None) -> int:
    """Claim and drain this node's entries; returns how many files are now gone.

    A cleared entry is deleted; a failed one keeps its error and, after enough failures, is marked
    stuck. Entries another worker holds are not seen (SKIP LOCKED), so a lost race returns 0.
    """
    entries = list((await session.execute(claim_statement(root_id, only_id))).scalars().all())
    cleared = 0
    for entry in entries:
        cleared += await _attempt(session, root, entry)
    await session.commit()
    return cleared


async def outbox_counts(session: AsyncSession, root_id: str) -> dict[str, int]:
    """Entries needing a person (stuck) and entries belonging to another node's storage."""
    stuck = await session.scalar(
        sa.select(sa.func.count()).select_from(Entry).where(Entry.root_id == root_id, Entry.stuck_at.is_not(None))
    )
    other = await session.scalar(
        sa.select(sa.func.count()).select_from(Entry).where(Entry.root_id != root_id, Entry.stuck_at.is_(None))
    )
    return {"stuck": int(stuck or 0), "other_root": int(other or 0)}
