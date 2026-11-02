# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Remove old ``.env.*~`` copies, only after a human approves it (#20567, #17038).

One copy is left beside the backend's ``.env`` for every old render. The newest (by mtime) stays, the
rest go. (The stale ``autobot-infrastructure`` directory is a separate follow-up, #20578.)

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
from dataclasses import dataclass
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
#: The production module that PROPOSES these actions (#17315).
PROPOSED_BY = "api.admin_cleanup_proposals"

#: Beside the backend's own ``.env``: Ansible renders it into ``<install root>/autobot-backend``.
BACKEND_DIR_NAME = "autobot-backend"
ENV_COPY_GLOB = ".env.*~"


@dataclass(frozen=True)
class CleanupPlan:
    """What an action would do right now. ``refused`` set means nothing may be removed."""

    targets: tuple[Path, ...] = ()
    kept: Path | None = None
    refused: str | None = None

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


def _remove_env_copies(plan: CleanupPlan, root: Path) -> int:
    backend = root / BACKEND_DIR_NAME
    removed = 0
    for path in plan.targets:
        if path.is_symlink() or not _inside(path, backend):
            raise ValueError(f"{path.name} changed to a symlink or left the install root; nothing further removed")
        path.unlink()
        removed += 1
    return removed


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


async def execute_env_copies_cleanup(approval: "Approval", session: "AsyncSession") -> None:
    """Remove all but the newest ``.env.*~`` copy once a human approved it: four eyes, re-plan, audit first."""
    audit_action, planner, remover, noun = (
        AuditAction.CLEANUP_ENV_COPIES,
        plan_env_copies,
        _remove_env_copies,
        ".env.*~ copies",
    )
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


def register_install_cleanup_actions() -> None:
    """Idempotent: re-registering replaces the same key with an equal handler."""
    register_post_approval_action(
        ENV_COPIES_ACTION, execute_env_copies_cleanup, proposed_by=PROPOSED_BY, server_only=True
    )


__all__ = [
    "ENV_COPIES_ACTION",
    "PROPOSED_BY",
    "CleanupPlan",
    "execute_env_copies_cleanup",
    "install_root",
    "plan_env_copies",
    "register_install_cleanup_actions",
]
