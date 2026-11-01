# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Two install cleanups that run only after a human approves them (#20567, #17038).

* ``.env.*~`` copies: one is left beside the backend's ``.env`` for every old render. The newest
  (by mtime) stays, the rest go.
* ``<install root>/autobot-infrastructure``: a stale directory beside the install (#20520). It must be
  the deployed copy, so one holding ``.git`` is a checkout and is refused.

Only THIS node's files are handled: the install root is this process's own (``config.path.base_dir``),
and no other fleet node is reached. Paths are computed here, at execution, from that root; the request
and the approval's context carry only the action name, never a path. The plan is computed again when the
approval is executed. A symlink, or a path resolving outside the install root, is refused and nothing is
removed. A file's contents are never opened, read or logged: the audit entry names counts and paths.
Blocking file I/O runs in a worker thread, off the event loop.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from autobot_shared.ssot_config import config
from models.approval import ApprovalComment
from services.approval_execution import register_post_approval_action
from services.audit.taxonomy import AuditAction
from services.audit_logger import audit_log

# Four eyes is shared with the column drop (#19997); PRs #20445/#20496 move it to a common helper.
# Until they land this module imports the one copy instead of writing a third.
from services.org_tier_column_action import _is_self_approval

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

ENV_COPIES_ACTION = "env_backup_copies_cleanup"
INFRA_DIR_ACTION = "stale_infrastructure_dir_removal"
#: The production module that PROPOSES these actions (#17315).
PROPOSED_BY = "api.admin_cleanup_proposals"

#: Beside the backend's own ``.env``: Ansible renders it into ``<install root>/autobot-backend``.
BACKEND_DIR_NAME = "autobot-backend"
ENV_COPY_GLOB = ".env.*~"
INFRA_DIR_NAME = "autobot-infrastructure"


@dataclass(frozen=True)
class CleanupPlan:
    """What an action would do right now. ``refused`` set means nothing may be removed."""

    targets: tuple[Path, ...] = ()
    kept: Path | None = None
    refused: str | None = None
    file_count: int = field(default=0)

    @property
    def count(self) -> int:
        return 0 if self.refused else len(self.targets)


def install_root() -> Path:
    """This node's install root, from the SSOT path config (never a literal)."""
    return Path(config.path.base_dir)


def _inside(path: Path, root: Path) -> bool:
    """Whether *path* resolves under *root* (both resolved, symlinks followed)."""
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


def plan_env_copies(root: Path | None = None) -> CleanupPlan:
    """Which ``.env.*~`` copies to remove: all but the newest. Reads names and mtimes only."""
    root = root or install_root()
    if os.path.lexists(root / ".git"):
        return CleanupPlan(refused="the install root is a checkout, so these are not deployed files")
    backend = root / BACKEND_DIR_NAME
    if backend.is_symlink() or not _inside(backend, root):
        return CleanupPlan(refused="the backend directory is a symlink or outside the install root")
    if not backend.is_dir():
        return CleanupPlan()
    found = sorted(backend.glob(ENV_COPY_GLOB), key=lambda p: p.name)
    for path in found:
        if path.is_symlink() or not path.is_file() or not _inside(path, backend):
            return CleanupPlan(refused=f"{path.name} is a symlink, not a regular file, or outside the install root")
    ranked = sorted(found, key=lambda p: (p.stat().st_mtime, p.name))
    if len(ranked) < 2:
        return CleanupPlan(kept=ranked[0] if ranked else None)
    return CleanupPlan(targets=tuple(ranked[:-1]), kept=ranked[-1])


def _tree_file_count(path: Path) -> int:
    return sum(len(files) for _, _, files in os.walk(path, followlinks=False))


def plan_infrastructure_dir(root: Path | None = None) -> CleanupPlan:
    """Whether ``<install root>/autobot-infrastructure`` may be removed. A checkout (``.git``) is refused."""
    root = root or install_root()
    target = root / INFRA_DIR_NAME
    if not os.path.lexists(target):
        return CleanupPlan()
    if os.path.lexists(root / ".git"):
        return CleanupPlan(refused="the install root is a checkout, so this is tracked source, not a deployed copy")
    if target.is_symlink() or not target.is_dir():
        return CleanupPlan(refused=f"{INFRA_DIR_NAME} is a symlink or not a directory")
    if not _inside(target, root) or target.resolve() == root.resolve():
        return CleanupPlan(refused=f"{INFRA_DIR_NAME} resolves outside the install root")
    # Role manifests are read from code_source; with no copy there, nothing replaces this one (#20520).
    if not (root / "code_source" / INFRA_DIR_NAME).is_dir():
        return CleanupPlan(refused=f"code_source has no {INFRA_DIR_NAME}, so this may be the only copy")
    if os.path.lexists(target / ".git"):
        return CleanupPlan(refused=f"{INFRA_DIR_NAME} holds .git: it is a checkout, not the deployed copy")
    return CleanupPlan(targets=(target,), file_count=_tree_file_count(target))


def _remove_env_copies(plan: CleanupPlan, root: Path) -> int:
    backend = root / BACKEND_DIR_NAME
    removed = 0
    for path in plan.targets:
        if path.is_symlink() or not _inside(path, backend):
            raise ValueError(f"{path.name} changed to a symlink or left the install root; nothing further removed")
        path.unlink()
        removed += 1
    return removed


def _remove_infrastructure_dir(plan: CleanupPlan, root: Path) -> int:
    target = plan.targets[0]
    if target.is_symlink() or not _inside(target, root):
        raise ValueError(f"{INFRA_DIR_NAME} changed to a symlink or left the install root; nothing removed")
    shutil.rmtree(target)
    return plan.file_count


async def _audit(approval: "Approval", action: AuditAction, result: str, **details: object) -> bool:
    """Whether the entry was written. Durable, as the entry before a removal must not be lost (#17038)."""
    return await audit_log(
        action.value,
        result=result,
        user_id=approval.decided_by_user,
        resource=action.value,
        durable=True,
        details={"approval_id": str(approval.id), **details},
    )


async def _record(approval: "Approval", session: "AsyncSession", body: str) -> None:
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()


async def _execute(approval, session, *, audit_action, planner, remover, noun: str) -> None:  # noqa: ANN001
    """Shared approved-execution path: four eyes, re-plan, refuse or remove, audit, leave a comment."""
    self_approval = await _is_self_approval(approval, session)
    root = install_root()
    plan = await asyncio.to_thread(planner, root)
    if plan.refused:
        await _audit(approval, audit_action, "denied", reason=plan.refused, self_approval=self_approval)
        await _record(approval, session, f"Nothing removed: {plan.refused}.")
        raise ValueError(plan.refused)
    if not plan.targets:
        await _audit(approval, audit_action, "success", removed=0, self_approval=self_approval)
        await _record(approval, session, f"Nothing to remove: no {noun} found.")
        return
    # The paper trail comes first: no committed entry means nothing is removed (#17038).
    names = [str(p.relative_to(root)) for p in plan.targets]
    if not await _audit(approval, audit_action, "success", phase="intent", paths=names, self_approval=self_approval):
        await _record(approval, session, "Nothing removed: the audit entry could not be written.")
        raise ValueError("the audit entry could not be written, so nothing was removed")
    try:
        removed = await asyncio.to_thread(remover, plan, root)
    except (OSError, ValueError) as exc:
        await _audit(approval, audit_action, "failed", error=type(exc).__name__, self_approval=self_approval)
        raise
    await _audit(
        approval, audit_action, "success", phase="completion", removed=removed, paths=names, self_approval=self_approval
    )
    suffix = " (self-approved by the only admin)." if self_approval else "."
    await _record(approval, session, f"Removed {removed} {noun}: {', '.join(names)}{suffix}")


async def execute_env_copies_cleanup(approval: "Approval", session: "AsyncSession") -> None:
    """Remove all but the newest ``.env.*~`` copy once a human approved it."""
    await _execute(
        approval,
        session,
        audit_action=AuditAction.CLEANUP_ENV_COPIES,
        planner=plan_env_copies,
        remover=_remove_env_copies,
        noun=".env.*~ copies",
    )


async def execute_infrastructure_dir_removal(approval: "Approval", session: "AsyncSession") -> None:
    """Remove the stale ``autobot-infrastructure`` directory once a human approved it."""
    await _execute(
        approval,
        session,
        audit_action=AuditAction.CLEANUP_INFRASTRUCTURE_DIR,
        planner=plan_infrastructure_dir,
        remover=_remove_infrastructure_dir,
        noun="files from the stale autobot-infrastructure directory",
    )


def register_install_cleanup_actions() -> None:
    """Idempotent: re-registering replaces the same key with an equal handler."""
    register_post_approval_action(
        ENV_COPIES_ACTION, execute_env_copies_cleanup, proposed_by=PROPOSED_BY, server_only=True
    )
    register_post_approval_action(
        INFRA_DIR_ACTION, execute_infrastructure_dir_removal, proposed_by=PROPOSED_BY, server_only=True
    )


__all__ = [
    "ENV_COPIES_ACTION",
    "INFRA_DIR_ACTION",
    "PROPOSED_BY",
    "CleanupPlan",
    "execute_env_copies_cleanup",
    "execute_infrastructure_dir_removal",
    "install_root",
    "plan_env_copies",
    "plan_infrastructure_dir",
    "register_install_cleanup_actions",
]
