# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The first orphan-storage detector (#17038, #17039): code-source clones.

A directory under ``CODE_SOURCES_BASE`` with no matching ``CodeSource``
record -- the #17036 orphan (``f5673506...``, a 290 MB clone from a failed
delete) is exactly this. ``register()`` adds it to ``services.orphan_storage``
-- called once by whatever imports this module for real use
(``api/admin_orphan_storage.py``), never as an import-time side effect, so a
test that imports this module for its functions doesn't also mutate the
shared registry.

Not the same case as ``source_service.delete_source_and_cleanup``: that
function deletes a *known* source's clone alongside its record. An orphan
has no record to delete -- there is nothing here but a stray directory to
remove, scoped to ``CODE_SOURCES_BASE`` the same way the known-source delete
path is.
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from autobot_shared.logging_manager import get_logger

from .source_paths import CODE_SOURCES_BASE
from .source_storage import RegistryUnavailable, registered_source_ids

logger = get_logger(__name__)

PROVIDER = "code_source_clone"


def _dir_size_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _resolved_clone_dir(candidate_id: str) -> Path | None:
    """The candidate's directory, or None if *candidate_id* escapes the base."""
    if not candidate_id or "/" in candidate_id or "\\" in candidate_id or candidate_id in {".", ".."}:
        return None
    clone_dir = (CODE_SOURCES_BASE / candidate_id).resolve()
    if not clone_dir.is_relative_to(CODE_SOURCES_BASE.resolve()):
        return None
    return clone_dir


async def _list_candidates():
    from services.orphan_storage import OrphanCandidate, orphan_grace_period_hours

    if not CODE_SOURCES_BASE.is_dir():
        return []
    # Raises RegistryUnavailable on an outage -- propagated to
    # list_all_candidates(), which records this provider as unavailable
    # rather than reading the outage as "zero known ids" (#17039 review).
    # Membership-only (no per-id fetch), so one record's own fetch failing
    # can never drop its id and falsely orphan its directory.
    known_ids = await registered_source_ids()
    grace_seconds = orphan_grace_period_hours() * 3600
    now = time.time()
    candidates = []
    for entry in CODE_SOURCES_BASE.iterdir():
        if not entry.is_dir() or entry.name in known_ids:
            continue
        age_seconds = now - entry.stat().st_mtime
        if age_seconds < grace_seconds:
            continue
        candidates.append(
            OrphanCandidate(
                provider=PROVIDER,
                id=entry.name,
                location=f"code-sources/{entry.name}",
                size_bytes=_dir_size_bytes(entry),
                modified_at=datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc).isoformat(),
                reason="no matching code-source record",
            )
        )
    return candidates


async def _delete(candidate_id: str):
    from services.orphan_storage import DeleteResult, orphan_grace_period_hours, safe_error_reason

    clone_dir = _resolved_clone_dir(candidate_id)
    if clone_dir is None:
        return DeleteResult(deleted=False, reason="invalid candidate id")
    if not clone_dir.is_dir():
        return DeleteResult(deleted=False, reason="candidate no longer exists")
    # Re-check at delete time (#17039 AC): a record may have reappeared, or
    # the directory may no longer be past the grace period. Never trust a
    # stale list_candidates() result for something this destructive.
    try:
        still_orphaned = candidate_id not in await registered_source_ids()
    except RegistryUnavailable as exc:
        return DeleteResult(deleted=False, reason=f"source registry unreachable: {safe_error_reason(exc)}")
    if not still_orphaned:
        return DeleteResult(deleted=False, reason="a source record now references this directory")
    grace_seconds = orphan_grace_period_hours() * 3600
    age_seconds = time.time() - clone_dir.stat().st_mtime
    if age_seconds < grace_seconds:
        return DeleteResult(deleted=False, reason="no longer past the grace period")
    try:
        shutil.rmtree(clone_dir)
    except OSError as exc:
        logger.error("Failed to remove orphan clone dir for %s: %s", candidate_id, exc)
        return DeleteResult(deleted=False, reason=f"removal failed: {safe_error_reason(exc)}")
    logger.info("Removed orphan code-source clone %s", candidate_id)
    return DeleteResult(deleted=True)


def register() -> None:
    """Register this detector. Called once at app startup, idempotent."""
    from services.orphan_storage import OrphanDetector, register_detector

    register_detector(OrphanDetector(provider=PROVIDER, list_candidates=_list_candidates, delete=_delete))
