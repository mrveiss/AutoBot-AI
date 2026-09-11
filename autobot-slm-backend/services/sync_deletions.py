# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Git-aware deletion for the builtin updater (#16310).

A normal code-sync never deletes: ``_rsync_component_local``'s rsync excludes
protect host state, but nothing removes a file that was tracked, then deleted
from source -- it just piles up on every host forever, indistinguishable from
a manual patch. Only a drift *resolve* deletes, and it is all-or-nothing
(``_resolve_deletion_guard`` refuses the whole sync rather than removing one
file), so it cannot surgically clean up a source-side deletion either.

This module closes that gap with a THIRD kind of deletion: git-proven. A file
is removed from the deployed tree only when ``git diff --diff-filter=DR``
between the previously-deployed commit and the new one names it -- never by
walking the deployed tree and guessing. Undeployed history (the previous
commit is unknown) means no deletion: guessing a baseline risks deleting a
file that was merely added since (#16310, no-data-loss rule).

Reuses the ``.deployed_commit`` marker convention (#15557,
``services/deploy_artifacts.py``'s ``HOST_STATE_EXCLUDES``) per component
rather than only for the SLM's own self-deploy: every component this module
touches gets its own marker in its own deployed directory.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from services.deployed_dir_resolver import get_live_dir
from services.drift_checker import ALLOWED_COMPONENTS, get_default_source_dir
from services.git_subprocess import component_pathspec, run_git
from services.git_tracker import DEFAULT_REPO_PATH

logger = logging.getLogger(__name__)

#: Marker convention shared with the SLM's own self-deploy marker (#15557).
DEPLOYED_COMMIT_MARKER = ".deployed_commit"

# The one-off leftover from the fixed cwd-relative NPUWorkerManager default
# (2026-07-30, see tests/test_npu_config_path_not_cwd_relative.py): a NESTED
# duplicate this bug wrote at autobot-backend/autobot-backend/config/, byte
# for byte identical to the canonical file it was meant to update. Removed
# only while that identity still holds (#16310) -- never unconditionally.
_NPU_WORKERS_REL = Path("config") / "npu_workers.yaml"
_NPU_WORKERS_NESTED_COMPONENT = "autobot-backend"


@dataclass
class ComponentDeletionResult:
    """Outcome of one component's git-aware deletion pass."""

    component: str
    removed: list[str] = field(default_factory=list)
    previous_commit: str | None = None
    new_commit: str | None = None
    skipped_reason: str | None = None

    def step_log_lines(self) -> list[str]:
        """Human-readable lines for the sync step log -- never silent."""
        if self.skipped_reason:
            return [f"{self.component}: {self.skipped_reason}"]
        if not self.removed:
            return []
        shown = ", ".join(self.removed[:10])
        more = f" (+{len(self.removed) - 10} more)" if len(self.removed) > 10 else ""
        short_commit = (self.new_commit or "")[:12]
        summary = f"removed {len(self.removed)} path(s) deleted from source at {short_commit}: {shown}{more}"
        return [f"{self.component}: {summary}"]


def _read_marker(deployed_dir: str) -> str | None:
    marker = Path(deployed_dir) / DEPLOYED_COMMIT_MARKER
    try:
        text = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _write_marker(deployed_dir: str, commit: str) -> None:
    marker = Path(deployed_dir) / DEPLOYED_COMMIT_MARKER
    try:
        marker.write_text(f"{commit}\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("sync_deletions: could not write %s: %s", marker, exc)


async def _read_previous_commit(deployed_dir: str) -> str | None:
    return await asyncio.to_thread(_read_marker, deployed_dir)


async def _write_deployed_commit(deployed_dir: str, commit: str) -> None:
    await asyncio.to_thread(_write_marker, deployed_dir, commit)


def _parse_deleted_paths(output: str, pathspec: str) -> list[str]:
    """Component-relative paths a ``--diff-filter=DR`` name-status diff reports.

    A rename reports OLD-tab-NEW; the OLD path is what the deployed tree must
    drop. ``--diff-filter=DR`` combined with the ``-- pathspec`` scoping means
    every line here is already inside *pathspec* -- no further filtering
    needed, only stripping the prefix down to a deployed-relative path.
    """
    prefix = f"{pathspec}/" if pathspec else ""
    removed: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        repo_path = parts[1]  # for a rename (R###, old, new) this is the OLD path
        if not prefix or repo_path.startswith(prefix):
            removed.append(repo_path[len(prefix) :] if prefix else repo_path)
    return removed


def _unlink_paths(deployed_dir: str, rel_paths: list[str]) -> list[str]:
    """Remove each existing file/symlink in *rel_paths*; return what was removed."""
    removed: list[str] = []
    for rel in rel_paths:
        target = Path(deployed_dir) / rel
        if not (target.is_file() or target.is_symlink()):
            continue  # already gone, or git reported a path that is now a directory
        try:
            target.unlink()
            removed.append(rel)
        except OSError as exc:
            logger.warning("sync_deletions: could not remove %s: %s", target, exc)
    return removed


async def remove_deleted_paths(
    component: str,
    source_dir: str,
    deployed_dir: str,
    repo_root: str = DEFAULT_REPO_PATH,
) -> ComponentDeletionResult:
    """Remove every path git proves was deleted/renamed away since the last sync.

    Reads/writes the per-component ``.deployed_commit`` marker. Does nothing
    (and says why) when the previous commit is unknown -- there is no safe
    baseline to diff against (#16310).
    """
    result = ComponentDeletionResult(component=component)
    previous = await _read_previous_commit(deployed_dir)
    if previous is None:
        result.skipped_reason = "previously-deployed commit unknown -- no deletion performed"
        return result

    head_output, rc = await run_git(repo_root, "rev-parse", "HEAD")
    new_commit = head_output.strip() or None
    if rc != 0 or not new_commit:
        result.skipped_reason = "could not resolve current source commit -- no deletion performed"
        return result
    result.previous_commit = previous
    result.new_commit = new_commit
    if previous == new_commit:
        return result

    pathspec = component_pathspec(repo_root, source_dir)
    diff_output, rc = await run_git(
        repo_root, "diff", "--name-status", "--diff-filter=DR", f"{previous}..{new_commit}", "--", pathspec
    )
    if rc != 0:
        result.skipped_reason = f"git diff {previous[:12]}..{new_commit[:12]} failed -- no deletion performed"
        return result

    candidates = _parse_deleted_paths(diff_output, pathspec)
    result.removed = await asyncio.to_thread(_unlink_paths, deployed_dir, candidates)
    await _write_deployed_commit(deployed_dir, new_commit)
    return result


def _npu_workers_leftover_path(backend_deployed_dir: str) -> Path:
    """The nested duplicate left by the fixed cwd-relative default (#16310)."""
    return Path(backend_deployed_dir) / _NPU_WORKERS_NESTED_COMPONENT / _NPU_WORKERS_REL


def _files_are_byte_identical(a: Path, b: Path) -> bool:
    try:
        return a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def _remove_npu_workers_leftover(backend_deployed_dir: str) -> str | None:
    """Remove the nested npu_workers.yaml duplicate, only while byte-identical.

    Returns a step-log line, or None when there is nothing to do.
    """
    nested = _npu_workers_leftover_path(backend_deployed_dir)
    canonical = Path(backend_deployed_dir) / _NPU_WORKERS_REL
    if not nested.exists():
        return None
    if not _files_are_byte_identical(nested, canonical):
        logger.warning(
            "sync_deletions: nested %s differs from canonical %s -- leaving both (#16310)", nested, canonical
        )
        return None
    try:
        nested.unlink()
        nested.parent.rmdir()  # best-effort: prune the now-empty nested config/ dir
        nested.parent.parent.rmdir()  # and the nested autobot-backend/ dir it sat in
    except OSError:
        pass  # non-empty or already gone -- the leftover file is removed either way
    return f"{_NPU_WORKERS_NESTED_COMPONENT}: removed nested npu_workers.yaml duplicate (byte-identical, #16310)"


async def cleanup_colocated_components(
    components: frozenset[str] | None = None,
    log: Callable[[str], None] | None = None,
) -> list[str]:
    """Run the git-aware deletion pass for every colocated component.

    Iterates the resolve-capable component set (autobot_shared and every
    backend/frontend/worker with a verified source/deployed mapping); a
    component not deployed on THIS host (no deployed directory) is skipped,
    not treated as an error. Returns step-log lines for every component that
    had something to report -- removed paths or a reason nothing happened --
    and, when *log* is given, also hands each line to it as it is produced so
    a caller can fold them straight into its own step log (#16310) without
    keeping a second copy of the loop.
    """
    lines: list[str] = []
    for component in sorted(components if components is not None else ALLOWED_COMPONENTS):
        deployed_dir = get_live_dir(component)
        if not Path(deployed_dir).exists():
            continue  # not colocated on this host -- nothing to clean up here
        try:
            source_dir = get_default_source_dir(component)
        except ValueError:
            continue  # code_source layout unavailable -- leave the tree as-is
        result = await remove_deleted_paths(component, source_dir, deployed_dir)
        component_lines = result.step_log_lines()
        if component == _NPU_WORKERS_NESTED_COMPONENT:
            leftover_line = await asyncio.to_thread(_remove_npu_workers_leftover, deployed_dir)
            if leftover_line:
                component_lines.append(leftover_line)
        if log is not None:
            for line in component_lines:
                log(line)
        lines.extend(component_lines)
    return lines
