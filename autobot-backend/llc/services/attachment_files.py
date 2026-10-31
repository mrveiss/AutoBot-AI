# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""File-side steps of attachment storage: staging, publishing, the staging sweep (#19756).

An upload is stage -> commit -> publish. The bytes are written (and fsynced) under
``<root>/.staging``, the row is committed, and only then is the file moved to its final path --
so a failed commit never leaves a file where a reader could find it, and a file at its final
path always has a row. The deletion outbox lives in :mod:`llc.services.attachment_outbox`.

**Nothing in here deletes stored data** (#17038). :func:`sweep_staging` reads only the staging
directory. A staged file whose row exists is committed content and is published, whatever its
age. One with no row, once older than the window, is *moved* to ``.staging/quarantine`` and
counted; nothing removes it from there.
"""

import asyncio
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
from llc.models.attachment import LLCWorkItemAttachment

logger = get_logger(__name__)

STAGING_DIRNAME = ".staging"
QUARANTINE_DIRNAME = "quarantine"
STAGED_SUFFIX = ".part"
_HASH_CHUNK = 1024 * 1024

_COUNT_KEYS = ("published", "quarantined", "waiting", "skipped", "failed", "duplicate", "conflict")


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def stage_bytes(root: Path, attachment_id: str, content: bytes) -> Path:
    """Write *content* to its staging path and fsync it, so the commit that follows is not ahead of the bytes."""
    staged = staging_path(root, attachment_id)
    staged.parent.mkdir(parents=True, exist_ok=True)
    with staged.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_dir(staged.parent)
    return staged


def publish(staged: Path, dest: Path) -> None:
    """Move a staged file to its final path, then fsync the directory that now holds it.

    ``os.replace`` is atomic on one filesystem. A staged file that is already gone while the
    destination exists was published by a concurrent publisher (the upload itself, or the
    sweep), which is the outcome wanted rather than a failure.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(staged, dest)
    except FileNotFoundError:
        if not dest.exists():
            raise
        return
    _fsync_dir(dest.parent)


def _staged_files(root: Path) -> list[Path]:
    directory = staging_dir(root)
    if not directory.is_dir():
        return []
    return [e for e in directory.iterdir() if not e.is_symlink() and e.is_file() and e.suffix == STAGED_SUFFIX]


def _quarantine_if_old(root: Path, staged: Path, max_age_seconds: int) -> bool:
    """Move *staged* into quarantine if it is still older than the window. Never removes it."""
    try:
        if staged.stat().st_mtime > time.time() - max_age_seconds:
            return False
        target_dir = staging_dir(root) / QUARANTINE_DIRNAME
        target_dir.mkdir(parents=True, exist_ok=True)
        os.replace(staged, target_dir / f"{staged.stem}.{int(time.time())}{STAGED_SUFFIX}")
    except FileNotFoundError:
        return False  # settled by someone else between listing and now
    _fsync_dir(target_dir)
    return True


def _compare_copies(staged: Path, dest: Path) -> tuple[str, str]:
    return file_sha256(staged), file_sha256(dest)


async def _both_copies_exist(row: LLCWorkItemAttachment, staged: Path, dest: Path) -> str:
    """A committed row with a staged file AND a published one: count it, never delete either."""
    staged_sha, dest_sha = await asyncio.to_thread(_compare_copies, staged, dest)
    if staged_sha == dest_sha:
        return "duplicate"
    logger.error(
        "#19756: attachment %s has differing staged (%s) and published (%s) copies; recorded sha256 is %s; "
        "both kept for a person to resolve",
        row.id,
        staged_sha,
        dest_sha,
        row.sha256,
    )
    return "conflict"


async def _publish_for_row(row: LLCWorkItemAttachment, staged: Path, dest: Path) -> str:
    if await asyncio.to_thread(dest.exists):
        return await _both_copies_exist(row, staged, dest)
    try:
        await asyncio.to_thread(publish, staged, dest)
    except OSError as exc:
        logger.error("#19756: publishing staged attachment %s to %s failed: %s", row.id, dest, exc)
        return "failed"
    return "published"


async def _settle(session: AsyncSession, root: Path, staged: Path, max_age_seconds: int, resolve_dest: Callable) -> str:
    try:
        attachment_id = uuid.UUID(staged.stem)
    except ValueError:
        logger.warning("#19756: staging file %s is not named for an attachment; left alone", staged.name)
        return "skipped"
    # A blocking row lock (not SKIP LOCKED: a skipped row would read as "no row"), held until
    # the commit below, so a concurrent delete of this row waits for the publish to finish.
    row = (
        await session.execute(
            sa.select(LLCWorkItemAttachment).where(LLCWorkItemAttachment.id == attachment_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is not None:
        return await _publish_for_row(row, staged, resolve_dest(row))
    if await asyncio.to_thread(_quarantine_if_old, root, staged, max_age_seconds):
        logger.warning("#19756: staged file %s has no attachment row; moved to quarantine, not deleted", staged.name)
        return "quarantined"
    return "waiting"


async def sweep_staging(
    session: AsyncSession, root: Path, max_age_seconds: int, resolve_dest: Callable[[LLCWorkItemAttachment], Path]
) -> dict[str, int]:
    """Settle the staging directory, touching nothing outside it.

    A staged file with a row is published at once (the row is proof, so age is irrelevant). One
    with no row waits out ``max_age_seconds`` and is then quarantined.
    """
    counts = dict.fromkeys(_COUNT_KEYS, 0)
    for staged in await asyncio.to_thread(_staged_files, root):
        counts[await _settle(session, root, staged, max_age_seconds, resolve_dest)] += 1
        await session.commit()
    return counts
