# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Path and rsync-argument helpers for component sync (#18052 extraction).

Lifted verbatim from ``api/code_sync.py``, which carried 168 top-level
definitions in 6,025 lines and sat exactly at its frozen size ceiling, so no
call site could be added to it without making room first.

These six were chosen because the dependency graph says they are separable, not
because their names grouped well. The obvious candidate -- the fleet/node
subsystem, 36 definitions and 1,122 lines -- is entangled: it calls 21 symbols
from the rest of the module and 17 of its own are called from outside, so
extracting it would mean circular imports or dragging half the file along.
These six call nothing in ``code_sync`` and read no module state beyond
``logger`` and two constants, which move with them.

They live in ``api/`` rather than ``services/`` deliberately. ``conftest.py``
AST-derives every ``services.*`` module ``code_sync`` imports and replaces it
with a MagicMock, so a pure helper moved to ``services/`` comes back as a mock
and every test exercising it through ``code_sync`` fails. The repo already
learned this: #16640 put role procedures in ``api/_colocated_role_procedures.py``
and #16310 put the full-tree surface in ``api/full_tree_drift.py``.

``code_sync`` re-exports them, so callers and tests reaching for
``api.code_sync._rsync_exclude_args`` keep working unchanged.
"""

from __future__ import annotations

import asyncio
import getpass
import logging
import shutil
from pathlib import Path
from typing import List

from services.deploy_artifacts import rsync_artifact_excludes, rsync_host_state_args
from services.deployed_dir_resolver import get_release_component_dir
from services.drift_checker import deploy_only_entries, owned_subtrees

# stdlib logging, matching `code_sync` and `_colocated_role_procedures`: the
# test harness mocks the config `get_logger` reads, so calling it at import
# time raises `TypeError: '>' not supported between MagicMock and int` from
# RotatingFileHandler. CLAUDE.md allows stdlib logging for exactly this.
logger = logging.getLogger(__name__)

#: How many blocked deletions to name in a preview before truncating.
_BLOCKED_DELETION_PREVIEW: int = 20

#: rsync's itemised marker for a deletion in `--delete` dry-run output.
_RSYNC_DELETE_MARKER: str = "*deleting"

#: Seconds to wait for `chown -R` over a built dist tree. Both of these were
#: bare literals inside `code_sync`, where the hardcoded-value baseline already
#: covered them by path; moving the code un-baselines them, which is the guard
#: working -- the numbers are now named where a reader meets them.
_CHOWN_TIMEOUT_S: float = 30.0

#: Seconds to wait for a snapshot restore rsync. Longer than the chown because
#: it copies a whole component tree rather than adjusting metadata.
_SNAPSHOT_RESTORE_TIMEOUT_S: float = 120.0


def _with_blocked_paths(message: str, blocked: List[str]) -> str:
    """Append the would-be-deleted paths to a refusal message (#13851).

    The async job row carries only a message, so the paths at stake must travel
    inside it or the operator polling job status is told a resolve refused
    without being told what it was protecting.
    """
    if not blocked:
        return message
    shown = blocked[:_BLOCKED_DELETION_PREVIEW]
    suffix = f" (+{len(blocked) - len(shown)} more)" if len(blocked) > len(shown) else ""
    return f"{message} Paths: {', '.join(shown)}{suffix}"


def _rsync_exclude_args(excludes: List[str], component: str | None = None) -> List[str]:
    """Build --exclude args from caller excludes, canonical build/deploy
    artifacts, protected runtime paths, and other components' subtrees.

    Canonical artifact excludes (#11459) are injected here — the single rsync
    chokepoint — so every sync ignores exactly what the drift checker skips
    (shared source: services/deploy_artifacts.py). This keeps rsync and drift in
    lockstep: previously ``*.egg-info`` etc. were drift-skipped (#11440) but
    still deleted-and-resynced, churning the deployed tree. Protected paths
    (#9970) must survive every delete-style sync.

    #13851: when *component* is given, subtrees owned by ANOTHER component and
    the component's deploy-only entries are excluded too, anchored at the
    transfer root so a same-named directory deeper in the tree is unaffected.
    Defence in depth: the backend's delete-style resolve would have removed 34
    files under ``autobot-backend/plugins`` — perfectly in sync with their
    real source (the ``plugins`` component), invisible to a walk that only
    knows about ``code_source/autobot-backend``.

    Subtrees get a trailing slash (they are directories); deploy-only entries do
    not, because the set holds files (``config/npu_workers.yaml``), symlinks
    (``autobot_shared``) and rendered artifacts (``npu-worker.py``) alike, and
    an anchored pattern without a trailing slash matches all three.
    """
    foreign: List[str] = []
    if component is not None:
        foreign = [f"/{sub}/" for sub in sorted(owned_subtrees(component))]
        foreign += [f"/{path}" for path in sorted(deploy_only_entries(component))]
    merged = list(dict.fromkeys([*excludes, *rsync_artifact_excludes(), *foreign]))
    # Host-state args go FIRST: they carry `--include` entries, and rsync applies
    # the first matching rule (#14231). Dedup spans the whole list, not just
    # `merged` -- a caller passing `.env` would otherwise emit it twice.
    return list(dict.fromkeys([*rsync_host_state_args(), *(f"--exclude={exc}" for exc in merged)]))


def _parse_rsync_deletions(output: str) -> List[str]:
    """Extract the paths a `--dry-run --delete` rsync reported it would remove.

    rsync prints ``*deleting`` followed by column padding and the path. Only the
    leading padding is stripped: a trailing space is a legal filename character
    and removing it would misreport the path. Note that a removed directory is
    itemized once per level, so the list can be longer than the file count —
    which is the safe direction for a guard.
    """
    deletions: List[str] = []
    for line in output.splitlines():
        if line.startswith(_RSYNC_DELETE_MARKER):
            path = line[len(_RSYNC_DELETE_MARKER) :].lstrip(" ")
            if path:
                deletions.append(path)
    return deletions


async def _ensure_dist_writable(frontend_dir: str, steps: List[str]) -> None:
    """Chown dist/ to the running service user so vite's emptyOutDir can rimraf it (#11364).

    Root-owned files (from a prior Ansible build) cause EACCES; chown normalises
    ownership without destroying the live bundle.  Service user = getpass.getuser()
    (never hardcoded). Failure is non-fatal — step recorded, build still attempted.
    """
    dist_dir = Path(frontend_dir) / "dist"
    if not dist_dir.exists():
        steps.append("dist: no dist/ directory — ownership check skipped")
        return
    service_user = getpass.getuser()
    owner_spec = f"{service_user}:{service_user}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "chown",
            "-R",
            owner_spec,
            str(dist_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        _, _ = await asyncio.wait_for(proc.communicate(), timeout=_CHOWN_TIMEOUT_S)
        if proc.returncode == 0:
            logger.info("dist: chown -R %s %s ok", owner_spec, dist_dir)
            steps.append("dist: normalized ownership")
        else:
            logger.warning("dist: chown -R %s %s rc=%d", owner_spec, dist_dir, proc.returncode)
            steps.append(f"dist: chown failed (rc={proc.returncode}) — attempting build anyway")
    except Exception as exc:
        logger.warning("dist: chown error for %s: %s", dist_dir, exc)
        steps.append(f"dist: chown error: {exc} — attempting build anyway")


def _prune_old_snapshots(snap_base: Path, component: str, max_keep: int) -> None:
    """Remove oldest snapshot dirs for *component* beyond *max_keep* (#11404)."""
    prefix = f"{component}_"
    dirs = sorted(
        (d for d in snap_base.iterdir() if d.is_dir() and d.name.startswith(prefix)),
        key=lambda d: d.stat().st_mtime,
    )
    for old in dirs[:-max_keep] if max_keep > 0 else dirs:
        try:
            shutil.rmtree(old, ignore_errors=True)
            logger.info("snapshot prune: removed %s", old)
        except OSError as exc:
            logger.warning("snapshot prune: failed to remove %s: %s", old, exc)


async def _restore_component_snapshot(component: str, snapshot: str, steps: List[str]) -> bool:
    """Rsync *snapshot* back over the deployed dir for *component* (#11404).

    Split out of _rollback_component (#15323) so the caller can restart
    UNCONDITIONALLY afterwards — this only reports whether the revert itself
    landed, it never decides whether to restart.

    Returns True on a clean rsync (rc=0); False on a failed/timed-out/errored
    restore, each case logged and recorded in *steps*.
    """
    deployed_dir = get_release_component_dir(component)
    steps.append(f"rollback: restoring {component} from {snapshot}")
    try:
        proc = await asyncio.create_subprocess_exec(
            "rsync",
            "-a",
            "--delete",
            f"{snapshot}/",
            f"{deployed_dir}/",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_SNAPSHOT_RESTORE_TIMEOUT_S)
        out = stdout.decode(errors="replace") if stdout else ""
        if proc.returncode == 0:
            steps.append(f"rollback: restored from {snapshot}")
            logger.info("rollback: %s restored from %s", component, snapshot)
            return True
        steps.append(f"rollback: rsync restore failed (rc={proc.returncode}): {out[:200]}")
        logger.error("rollback: rsync restore failed for %s: %s", component, out[-300:])
        return False
    except asyncio.TimeoutError:
        steps.append(f"rollback: rsync restore timed out after {_SNAPSHOT_RESTORE_TIMEOUT_S:g}s")
        logger.error("rollback: rsync restore timed out for %s", component)
        return False
    except Exception as exc:
        steps.append(f"rollback: rsync restore error: {exc}")
        logger.error("rollback: rsync restore error for %s: %s", component, exc)
        return False
