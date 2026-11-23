# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Remove exactly the drift-confirmed ``removed_from_source`` files (#22082).

The File Drift Check (``services/full_tree_drift.py``) proves, from git history,
which deployed files were deleted from source. The only native removal path
before this module was ``POST /code-sync/drift/resolve`` -- a delete-style rsync
of the WHOLE component that cannot tell debris from host state (it would also
delete a host-generated ``package-lock.json``) and that rejects the ``plugins``
component outright.

This module is the ONE narrow operation: the candidate set IS the
``removed_from_source`` verdicts ``compute_full_tree_drift`` returns -- there is
no second classifier here, so every protection that verdict already applies
(``host_state_filter.kept_reason``, the artifact/build-bundle pruning, the
host-generated paths, the git-ignored check) applies unchanged. ``host_state``,
``build_bundle`` and ``modified`` files are never candidates.

Two steps, both stateless:

* :func:`plan_prune` -- the preview: exactly what would be removed.
* :func:`apply_prune` -- removes only the paths the caller confirmed AND that are
  STILL ``removed_from_source`` when it runs. A path that stopped being eligible
  between preview and confirm is refused, never removed.

Never deletes a directory, never follows a symlinked parent out of the deployed
tree, and never raises for one bad path -- each outcome is reported per path.
"""

from __future__ import annotations

import asyncio
import os
import stat
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

import services.full_tree_drift as _ftd
from autobot_shared.logging_manager import get_logger
from services.drift_checker import VISIBILITY_COMPONENTS
from services.full_tree_drift import (
    VERDICT_REMOVED_FROM_SOURCE,
    ComponentDrift,
    compute_full_tree_drift,
)
from services.git_tracker import DEFAULT_REPO_PATH

logger = get_logger(__name__)

_ABSENT = "already absent"


@dataclass
class PrunePlan:
    """What a prune would remove for one component, or why it cannot say."""

    component: str
    files: list[tuple[str, str | None]] = field(default_factory=list)  # (path, removing commit)
    deployed_dir: str = ""  # the tree the verdicts describe, from the classifier's own resolver
    error: str | None = None


@dataclass
class PruneResult:
    """Per-path outcome of a confirmed prune."""

    component: str
    removed: list[str] = field(default_factory=list)
    refused: dict[str, str] = field(default_factory=dict)  # path -> why it was left alone
    failed: dict[str, str] = field(default_factory=dict)  # path -> OS error


def is_prunable_component(component: str) -> bool:
    """Every drift-check component, including the read-only extras such as ``plugins``."""
    return canonical_component(component) is not None


def canonical_component(component: str) -> str | None:
    """The drift-check component name equal to *component*, taken from the trusted set.

    Returns the allowlist's own element, never the caller's string, so everything
    that builds a filesystem path from the result holds a value the request cannot
    shape. ``None`` when *component* names no drift-check component.
    """
    return next((known for known in sorted(VISIBILITY_COMPONENTS) if known == component), None)


def _plan_from_drift(drift: ComponentDrift) -> PrunePlan:
    if drift.skipped:
        return PrunePlan(component=drift.component, error="component is not deployed on this host")
    if drift.error:
        return PrunePlan(component=drift.component, error=drift.error)
    files = [(v.path, v.detail) for v in drift.drifted if v.verdict == VERDICT_REMOVED_FROM_SOURCE]
    return PrunePlan(component=drift.component, files=files)


async def plan_prune(component: str, repo_root: str = DEFAULT_REPO_PATH) -> PrunePlan:
    """The preview: every ``removed_from_source`` file of *component*, nothing else."""
    plan = _plan_from_drift(await compute_full_tree_drift(component, repo_root))
    plan.deployed_dir = _ftd.get_live_dir(component)  # the same call the classifier walked
    return plan


def _open_parent(deployed_dir: str, rel_path: str) -> tuple[int, str] | str:
    """(fd of the file's parent directory, file name), or the reason it cannot be opened.

    The walk opens every directory with ``O_NOFOLLOW`` relative to the previous fd, so a
    symlinked component -- or one swapped in after the verdict -- is refused, and the fd
    that is unlinked against is the one that was checked (no path re-resolution, no TOCTOU).
    """
    pure = Path(rel_path)
    if not rel_path or pure.is_absolute() or ".." in pure.parts:
        return "path resolves outside the deployed tree"
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(os.path.realpath(deployed_dir), flags)
    try:
        for part in pure.parent.parts:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
    except OSError:
        os.close(fd)
        return "path resolves outside the deployed tree"
    return fd, pure.name


def _unlink_at(fd: int, name: str) -> tuple[bool, str]:
    try:
        if stat.S_ISDIR(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
            return False, "is a directory"
        os.unlink(name, dir_fd=fd)
    except FileNotFoundError:
        return False, _ABSENT
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc.strerror or exc}"
    return True, ""


def _unlink_one(deployed_dir: str, rel_path: str) -> tuple[bool, str]:
    """Unlink one file. Returns (removed, reason) -- reason is empty on success."""
    try:
        opened = _open_parent(deployed_dir, rel_path)
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc.strerror or exc}"
    if isinstance(opened, str):
        return False, opened
    fd, name = opened
    try:
        return _unlink_at(fd, name)
    finally:
        os.close(fd)


def _remove_confirmed(plan: PrunePlan, deployed_dir: str, confirmed: list[str]) -> PruneResult:
    result = PruneResult(component=plan.component)
    eligible = {path for path, _ in plan.files}
    for rel_path in dict.fromkeys(confirmed):
        if rel_path not in eligible:
            result.refused[rel_path] = "not removed_from_source (left untouched)"
            continue
        removed, reason = _unlink_one(deployed_dir, rel_path)
        if removed:
            result.removed.append(rel_path)
        elif reason == _ABSENT:
            result.refused[rel_path] = reason
        else:
            result.failed[rel_path] = reason
    return result


async def apply_prune(
    component: str,
    confirmed: list[str],
    repo_root: str = DEFAULT_REPO_PATH,
    before_delete: Callable[[], Awaitable[None]] | None = None,
) -> PruneResult:
    """Remove the *confirmed* paths that are still ``removed_from_source`` now.

    The eligible set is re-derived from git at call time, never trusted from the
    caller's preview. *before_delete* runs after that derivation and immediately
    before the first unlink, so a safety check (a deploy started meanwhile) is
    taken at the last moment; if it raises, nothing is removed.
    """
    plan = await plan_prune(component, repo_root)
    if plan.error:
        return PruneResult(component=component, refused={p: plan.error for p in confirmed})
    if before_delete is not None:
        await before_delete()
    result = await asyncio.to_thread(_remove_confirmed, plan, plan.deployed_dir, confirmed)
    logger.warning(
        "drift prune: %s removed=%d refused=%d failed=%d",
        component,
        len(result.removed),
        len(result.refused),
        len(result.failed),
    )
    return result
