# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Per-task git worktree workspace allocation for code-writing agents (GH#6471).

Allocates an isolated git worktree per task under .task-workspaces/task-{id}/
so concurrent agents never share working-tree state.  Subsequent heartbeats
on the same task resume into the existing worktree.

Key functions:
  allocate(task_id, agent_id)   – create or resume a worktree
  release(task_id)              – remove the worktree when a task closes
  cleanup_stale(max_age_days)   – Celery beat hook to evict aged workspaces
"""

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Allow deployment-specific override so production installs that deploy only
# autobot-backend/ to /opt/autobot/ can point at the real git repository root
# (GH#6471 blocker 3 — _REPO_ROOT resolves to non-git dir on Ansible targets).
_REPO_ROOT = Path(os.environ.get("AUTOBOT_WORKSPACE_REPO_ROOT") or Path(__file__).resolve().parent.parent.parent)
_WORKSPACE_BASE_NAME = ".task-workspaces"
_META_FILENAME = ".workspace-meta.json"
_ACTIVE_LOCK_FILENAME = ".active-lock"
_MAX_WORKTREES_PER_AGENT = 5

# task_id must be a safe identifier: UUID hex chars + hyphens, max 128 chars.
# Rejects path-traversal payloads like "../../etc/passwd" (GH#6471 blocker 2).
_SAFE_TASK_ID_RE = re.compile(r"^[0-9a-zA-Z_\-]{1,128}$")


@dataclass
class WorkspaceInfo:
    task_id: str
    agent_id: str
    worktree_path: str
    branch: str
    is_new: bool
    created_at: str  # ISO-8601 UTC


def _validate_task_id(task_id: str) -> None:
    """Reject task_ids that could be used for path traversal (GH#6471 blocker 2)."""
    if not _SAFE_TASK_ID_RE.match(task_id):
        raise ValueError(f"Invalid task_id {task_id!r}: must match [0-9a-zA-Z_-]{{1,128}}")


def allocate(
    task_id: str,
    agent_id: str,
    repo_root: Optional[Path] = None,
    max_per_agent: int = _MAX_WORKTREES_PER_AGENT,
) -> WorkspaceInfo:
    """
    Allocate or resume a worktree for task_id.

    Creates .task-workspaces/task-{task_id}/ on branch task-{task_id}.
    If the directory and metadata already exist the existing workspace is
    returned (resume path — idempotent).  Enforces max_per_agent by evicting
    the oldest worktree for this agent when the limit would be exceeded.

    Raises ValueError if task_id is not a safe identifier.
    """
    _validate_task_id(task_id)
    root = repo_root or _REPO_ROOT
    workspace_base = root / _WORKSPACE_BASE_NAME
    workspace_dir = workspace_base / f"task-{task_id}"
    branch = f"task-{task_id}"

    # Resume path — worktree already exists
    meta_file = workspace_dir / _META_FILENAME
    if workspace_dir.exists() and meta_file.exists():
        try:
            with meta_file.open() as fh:
                meta = json.load(fh)
            logger.info(
                "Resuming existing workspace for task=%s at %s",
                task_id,
                workspace_dir,
            )
            (workspace_dir / _ACTIVE_LOCK_FILENAME).touch()
            return WorkspaceInfo(
                task_id=task_id,
                agent_id=agent_id,
                worktree_path=str(workspace_dir),
                branch=branch,
                is_new=False,
                created_at=meta.get("created_at", ""),
            )
        except (json.JSONDecodeError, OSError):
            pass  # fall through to re-create below

    workspace_base.mkdir(parents=True, exist_ok=True)
    _enforce_limit(agent_id, max_per_agent, root)

    created_at = datetime.now(timezone.utc).isoformat()
    _git_add_worktree(root, workspace_dir, branch)

    meta = {
        "task_id": task_id,
        "agent_id": agent_id,
        "created_at": created_at,
        "branch": branch,
    }
    (workspace_dir / _META_FILENAME).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (workspace_dir / _ACTIVE_LOCK_FILENAME).touch()

    logger.info(
        "Allocated new workspace for task=%s agent=%s at %s",
        task_id,
        agent_id,
        workspace_dir,
    )
    return WorkspaceInfo(
        task_id=task_id,
        agent_id=agent_id,
        worktree_path=str(workspace_dir),
        branch=branch,
        is_new=True,
        created_at=created_at,
    )


def release(
    task_id: str,
    repo_root: Optional[Path] = None,
    keep_on_failure: bool = False,
) -> None:
    """
    Remove the worktree for task_id.

    Deletes the branch as well unless it has unpushed commits.  When
    keep_on_failure is True the worktree is left in place for inspection
    and only a warning is logged on error.

    Raises ValueError if task_id is not a safe identifier.
    """
    _validate_task_id(task_id)
    root = repo_root or _REPO_ROOT
    workspace_dir = root / _WORKSPACE_BASE_NAME / f"task-{task_id}"

    if not workspace_dir.exists():
        logger.debug("No workspace to release for task=%s", task_id)
        return

    branch = f"task-{task_id}"
    # Clear the active-lock before git removal so that if removal fails and
    # keep_on_failure is True the directory can still be evicted later.
    (workspace_dir / _ACTIVE_LOCK_FILENAME).unlink(missing_ok=True)
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(workspace_dir)],
            cwd=str(root),
            check=True,
            capture_output=True,
            text=True,
        )
        # Best-effort branch deletion — ignore failures (e.g. branch pushed / not found)
        subprocess.run(
            ["git", "branch", "-D", branch],
            cwd=str(root),
            check=False,
            capture_output=True,
        )
        logger.info("Released workspace for task=%s", task_id)
    except subprocess.CalledProcessError as exc:
        msg = f"Failed to remove worktree for task={task_id}: {exc.stderr}"
        if keep_on_failure:
            logger.warning(msg)
        else:
            logger.error(msg)
            raise


def cleanup_stale(
    max_age_days: int = 7,
    repo_root: Optional[Path] = None,
) -> list[str]:
    """
    Remove task worktrees older than max_age_days.

    Reads each .workspace-meta.json to determine age; falls back to directory
    mtime when metadata is absent or corrupt.  Returns list of cleaned task IDs.
    """
    root = repo_root or _REPO_ROOT
    workspace_base = root / _WORKSPACE_BASE_NAME
    if not workspace_base.exists():
        return []

    cutoff = datetime.now(timezone.utc).timestamp() - max_age_days * 86_400
    cleaned: list[str] = []

    for entry in workspace_base.iterdir():
        if not entry.is_dir() or not entry.name.startswith("task-"):
            continue

        age_ts: float | None = None
        meta_file = entry / _META_FILENAME
        if meta_file.exists():
            try:
                with meta_file.open() as fh:
                    meta = json.load(fh)
                age_ts = datetime.fromisoformat(meta["created_at"]).timestamp()
            except (json.JSONDecodeError, KeyError, ValueError):
                pass

        if age_ts is None:
            age_ts = entry.stat().st_mtime

        if age_ts > cutoff:
            continue  # too young

        if (entry / _ACTIVE_LOCK_FILENAME).exists():
            logger.debug("Skipping locked workspace task=%s during stale cleanup", entry.name[len("task-") :])
            continue

        task_id = entry.name[len("task-") :]
        try:
            release(task_id, root, keep_on_failure=True)
            cleaned.append(task_id)
        except Exception as exc:
            logger.warning("Stale cleanup failed for task=%s: %s", task_id, exc)

    logger.info("Stale workspace cleanup: removed %d worktrees", len(cleaned))
    return cleaned


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _git_add_worktree(root: Path, workspace_dir: Path, branch: str) -> None:
    """Run git worktree add, handling pre-existing branch/directory gracefully."""
    try:
        subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(workspace_dir)],
            cwd=str(root),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        # Branch already exists from a previous partial allocation — reuse it
        if "already exists" in stderr:
            try:
                subprocess.run(
                    ["git", "worktree", "add", str(workspace_dir), branch],
                    cwd=str(root),
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as exc2:
                stderr2 = exc2.stderr or ""
                # Worktree dir is already registered in git — treat as resumed
                if "already checked out" in stderr2 and workspace_dir.exists():
                    logger.info(
                        "Worktree for branch=%s already registered at %s — resuming",
                        branch,
                        workspace_dir,
                    )
                else:
                    logger.error("git worktree add failed for branch=%s: %s", branch, stderr2)
                    raise
        else:
            logger.error("git worktree add failed for branch=%s: %s", branch, stderr)
            raise


def _enforce_limit(agent_id: str, max_per_agent: int, root: Path) -> None:
    """Evict oldest worktree(s) for agent_id if the per-agent limit would be exceeded.

    All worktrees count toward the limit, but only unlocked ones are eviction
    candidates.  Worktrees with an active-lock file are in use by a running
    subprocess and must never be evicted (GH#6471 follow-up: MVA-1154).
    """
    workspace_base = root / _WORKSPACE_BASE_NAME
    total_count = 0
    eviction_candidates: list[tuple[float, str]] = []

    for entry in workspace_base.iterdir():
        if not entry.is_dir() or not entry.name.startswith("task-"):
            continue
        meta_file = entry / _META_FILENAME
        if not meta_file.exists():
            continue
        try:
            with meta_file.open() as fh:
                meta = json.load(fh)
            if meta.get("agent_id") != agent_id:
                continue
            total_count += 1
            if (entry / _ACTIVE_LOCK_FILENAME).exists():
                continue  # count but do not add to eviction candidates
            ts = datetime.fromisoformat(meta["created_at"]).timestamp()
            task_id = entry.name[len("task-") :]
            eviction_candidates.append((ts, task_id))
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    overage = total_count - max_per_agent + 1
    if overage <= 0:
        return

    eviction_candidates.sort()  # oldest first
    for _, oldest_task_id in eviction_candidates[:overage]:
        logger.info(
            "Evicting oldest workspace task=%s for agent=%s (limit=%d)",
            oldest_task_id,
            agent_id,
            max_per_agent,
        )
        try:
            release(oldest_task_id, root)
        except Exception as exc:
            logger.warning("Eviction failed for task=%s: %s", oldest_task_id, exc)
