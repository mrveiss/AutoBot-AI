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
between the previously-deployed commit and the new one names it, it is not
kept-on-disk host state (``services/host_state_filter.py``), and it stays
inside *deployed_dir* once symlinks resolve -- never by walking the deployed
tree and guessing. Undeployed history (the previous commit is unknown) means
no deletion: guessing a baseline risks deleting a file that was merely added
since (#16310, no-data-loss rule).

**Marker discipline (#16310 review, blocking).** ``.deployed_commit`` is
``_get_slm_deployed_commit()``'s C4 self-update skip-gate (#12202) -- this
module must never write it, or a deletion pass that runs before the SLM's
own content actually syncs makes the gate see "already current" and skip the
real sync entirely, deleting files with the new code never copied in. This
module owns a SEPARATE marker (``DELETION_MARKER``) per component. On a
component's first run under this feature (its own marker absent) the
existing ``.deployed_commit`` is read -- never written -- as the bootstrap
baseline, so already-known stale files are still caught once.

**Ordering (#16310 review, blocking).** ``remove_deleted_paths`` performs no
gating of its own: it trusts the caller to invoke it only once that
component's content sync has already succeeded, and to skip the call
entirely on a failed sync -- so a failed sync leaves both the tree and the
marker untouched by construction. See ``api/code_sync.py``'s
``_run_colocated_role_procedures`` and ``_sync_slm_from_code_source`` for the
two call sites that satisfy this.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from services.deployed_dir_resolver import get_live_dir
from services.drift_checker import get_default_source_dir
from services.git_subprocess import component_pathspec, run_git
from services.git_tracker import DEFAULT_REPO_PATH
from services.host_state_filter import kept_reason
from services.marker_io import read_marker, write_marker

# Plain stdlib logging, deliberately -- see services/git_subprocess.py's
# comment: get_logger() crashes at creation time under a MagicMock `config`,
# the precedent autobot_shared/user_management/password_epoch.py:50-58 sets.
logger = logging.getLogger(__name__)

#: This module's own marker -- distinct from ``.deployed_commit`` (#12202).
DELETION_MARKER = ".autobot_sync_deletions_commit"

#: Legacy marker read (never written) as a one-time bootstrap baseline.
_LEGACY_BOOTSTRAP_MARKER = ".deployed_commit"

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
    kept: list[str] = field(default_factory=list)  # host-state/ignored candidates skipped
    previous_commit: str | None = None
    new_commit: str | None = None
    skipped_reason: str | None = None

    def step_log_lines(self) -> list[str]:
        """Human-readable lines for the sync step log -- never silent."""
        lines: list[str] = []
        if self.skipped_reason:
            return [f"{self.component}: {self.skipped_reason}"]
        if self.removed:
            lines.append(f"{self.component}: {_removed_summary(self.removed, self.new_commit)}")
        if self.kept:
            lines.append(f"{self.component}: kept {len(self.kept)} host-state path(s): {', '.join(self.kept[:10])}")
        return lines


def _removed_summary(removed: list[str], new_commit: str | None) -> str:
    shown = ", ".join(removed[:10])
    more = f" (+{len(removed) - 10} more)" if len(removed) > 10 else ""
    short_commit = (new_commit or "")[:12]
    return f"removed {len(removed)} path(s) deleted from source at {short_commit}: {shown}{more}"


async def _read_previous_commit(deployed_dir: str) -> str | None:
    """The dedicated marker, or a read-only bootstrap from the legacy one."""
    own = await read_marker(deployed_dir, DELETION_MARKER)
    if own is not None:
        return own
    return await read_marker(deployed_dir, _LEGACY_BOOTSTRAP_MARKER)


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
        repo_path = line.split("\t")[1]  # for a rename (R###, old, new) this is the OLD path
        if not prefix or repo_path.startswith(prefix):
            removed.append(repo_path[len(prefix) :] if prefix else repo_path)
    return removed


def _is_contained(target: Path, deployed_root: Path) -> bool:
    """False when *target* resolves (through any symlink) outside *deployed_root*."""
    try:
        return target.resolve().is_relative_to(deployed_root.resolve())
    except OSError:
        return False


def _unlink_one(deployed_dir: str, rel: str) -> bool:
    """Remove one existing, contained file/symlink. Returns whether it was removed."""
    root = Path(deployed_dir)
    target = root / rel
    if not (target.is_file() or target.is_symlink()):
        return False  # already gone, or git reported a path that is now a directory
    if not _is_contained(target, root):
        logger.warning("sync_deletions: refusing %s -- resolves outside %s", target, root)
        return False
    try:
        target.unlink()
        return True
    except OSError as exc:
        logger.warning("sync_deletions: could not remove %s: %s", target, exc)
        return False


async def _partition_candidates(candidates: list[str], repo_root: str, pathspec: str) -> tuple[list[str], list[str]]:
    """Split *candidates* into (safe-to-delete, kept-as-host-state)."""
    to_delete: list[str] = []
    kept: list[str] = []
    for rel in candidates:
        reason = await kept_reason(rel, repo_root, f"{pathspec}/{rel}" if pathspec else rel)
        if reason is None:
            to_delete.append(rel)
        else:
            kept.append(rel)
            logger.info("sync_deletions: keeping %s (%s)", rel, reason)
    return to_delete, kept


async def _resolve_commit_range(deployed_dir: str, repo_root: str) -> tuple[str | None, str | None, str | None]:
    """Return (previous, new, skip_reason) -- skip_reason set means stop here."""
    previous = await _read_previous_commit(deployed_dir)
    if previous is None:
        return None, None, "previously-deployed commit unknown -- no deletion performed"
    head_output, rc = await run_git(repo_root, "rev-parse", "HEAD")
    new_commit = head_output.strip() or None
    if rc != 0 or not new_commit:
        return previous, None, "could not resolve current source commit -- no deletion performed"
    return previous, new_commit, None


async def _diff_deleted_paths(
    repo_root: str, source_dir: str, previous: str, new_commit: str
) -> tuple[list[str], str | None]:
    """Candidates ``--diff-filter=DR`` names between *previous* and *new_commit*."""
    pathspec = component_pathspec(repo_root, source_dir)
    diff_output, rc = await run_git(
        repo_root, "diff", "--name-status", "--diff-filter=DR", f"{previous}..{new_commit}", "--", pathspec
    )
    if rc != 0:
        return [], f"git diff {previous[:12]}..{new_commit[:12]} failed -- no deletion performed"
    return _parse_deleted_paths(diff_output, pathspec), None


async def remove_deleted_paths(
    component: str,
    source_dir: str,
    deployed_dir: str,
    repo_root: str = DEFAULT_REPO_PATH,
) -> ComponentDeletionResult:
    """Remove every path git proves was deleted/renamed since the last sync.

    Callers must invoke this only after confirming *this component's* content
    sync just succeeded (#16310 review) -- this function performs no such
    check itself, so a caller that skips it on failure leaves both the tree
    and the marker untouched by construction.
    """
    result = ComponentDeletionResult(component=component)
    previous, new_commit, skip = await _resolve_commit_range(deployed_dir, repo_root)
    result.previous_commit, result.new_commit = previous, new_commit
    if skip:
        result.skipped_reason = skip
        return result
    if previous == new_commit:
        return result

    candidates, skip = await _diff_deleted_paths(repo_root, source_dir, previous, new_commit)
    if skip:
        result.skipped_reason = skip
        return result

    pathspec = component_pathspec(repo_root, source_dir)
    to_delete, result.kept = await _partition_candidates(candidates, repo_root, pathspec)
    result.removed = [rel for rel in to_delete if _unlink_one(deployed_dir, rel)]
    await write_marker(deployed_dir, DELETION_MARKER, new_commit)
    return result


def _npu_workers_leftover_path(backend_deployed_dir: str) -> Path:
    """The nested duplicate left by the fixed cwd-relative default (#16310)."""
    return Path(backend_deployed_dir) / _NPU_WORKERS_NESTED_COMPONENT / _NPU_WORKERS_REL


def _files_are_byte_identical(a: Path, b: Path) -> bool:
    try:
        return a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def _prune_now_empty_parents(nested: Path) -> None:
    try:
        nested.parent.rmdir()  # best-effort: prune the now-empty nested config/ dir
        nested.parent.parent.rmdir()  # and the nested autobot-backend/ dir it sat in
    except OSError:
        pass  # non-empty or already gone -- the leftover file is removed either way


def remove_npu_workers_leftover(backend_deployed_dir: str) -> str | None:
    """Remove the nested npu_workers.yaml duplicate, only while byte-identical.

    Callers must invoke this only after a successful ``autobot-backend`` sync
    (same ordering rule as ``remove_deleted_paths``). Returns a step-log line,
    or None when there is nothing to do.
    """
    nested = _npu_workers_leftover_path(backend_deployed_dir)
    canonical = Path(backend_deployed_dir) / _NPU_WORKERS_REL
    if not nested.exists():
        return None
    if not _files_are_byte_identical(nested, canonical):
        logger.warning("sync_deletions: nested %s differs from canonical -- leaving both (#16310)", nested)
        return None
    try:
        nested.unlink()
    except OSError as exc:
        logger.warning("sync_deletions: could not remove %s: %s", nested, exc)
        return None
    _prune_now_empty_parents(nested)
    return f"{_NPU_WORKERS_NESTED_COMPONENT}: removed nested npu_workers.yaml duplicate (byte-identical, #16310)"


# Ansible role name -> drift_checker component name, for the co-located
# procedure hook (``apply_role_deletions``) only. Deliberately NOT
# ``role.source_paths``/``role.target_path``: those serve
# ``SyncOrchestrator``'s remote-node push, which lands "backend"'s contents
# straight under the deployed root -- a different convention than the ansible
# role's OWN deployed layout (``/opt/autobot/autobot-backend``), which is
# what ``get_live_dir``/``get_default_source_dir`` resolve (#16310 review).
# A role with no entry here (monitoring, redis, postgres, docker, ...) has no
# ALLOWED_COMPONENTS counterpart and is skipped.
_ROLE_TO_COMPONENT: dict[str, str] = {
    "backend": "autobot-backend",
    "celery": "autobot-backend",
    "scheduler": "autobot-backend",
    "frontend": "autobot-frontend",
    "slm-backend": "autobot-slm-backend",
    "slm-frontend": "autobot-slm-frontend",
    "autobot_shared": "autobot_shared",
    "ai-stack": "autobot-ai-stack",
    "chromadb": "autobot-ai-stack",
    "npu-worker": "autobot-npu-worker",
    "browser-service": "autobot-browser-worker",
    "slm-agent": "autobot-slm-agent",
}


def _role_component_dirs(role_name: str) -> tuple[str, str] | None:
    """(source_dir, deployed_dir) for *role_name*'s component, or None to skip."""
    component = _ROLE_TO_COMPONENT.get(role_name)
    if component is None:
        return None
    deployed_dir = get_live_dir(component)
    if not Path(deployed_dir).exists():
        return None  # not colocated on this host
    try:
        return get_default_source_dir(component), deployed_dir
    except ValueError:
        return None  # code_source layout unavailable -- leave the tree as-is


async def apply_role_deletions(role_name: str) -> list[str]:
    """Deletion pass for the component a co-located role name maps to.

    Callers must invoke this only after that role's ansible procedure just
    reported success (#16310 review) -- see ``api/code_sync.py``'s
    ``_run_colocated_role_procedures``. Returns step-log lines, empty when
    the role has no known component or nothing happened.
    """
    dirs = _role_component_dirs(role_name)
    if dirs is None:
        return []
    source_dir, deployed_dir = dirs
    component = _ROLE_TO_COMPONENT[role_name]
    result = await remove_deleted_paths(component, source_dir, deployed_dir)
    lines = result.step_log_lines()
    if component == _NPU_WORKERS_NESTED_COMPONENT:
        leftover = remove_npu_workers_leftover(deployed_dir)
        if leftover:
            lines.append(leftover)
    return lines
