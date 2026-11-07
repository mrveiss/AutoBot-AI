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
import platform
import stat as stat_module
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from autobot_shared.ssot_config import config
from models.approval import ApprovalComment
from services.approval_execution import register_post_approval_action
from services.approval_four_eyes import is_self_approval  # the one four-eyes rule (#19997, #20030)
from services.audit.taxonomy import AuditAction
from services.audit_logger import AuditResult, audit_log

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
    #: (st_dev, st_ino) of the backend directory when planned; removal refuses a directory that is not that one.
    backend_id: tuple[int, int] | None = None

    @property
    def count(self) -> int:
        return 0 if self.refused else len(self.targets)


def _backend_dir(root: Path) -> Path:
    """Where the backend's ``.env`` lives. On a deployed host AUTOBOT_BASE_DIR already is that directory."""
    return root if root.name == BACKEND_DIR_NAME else root / BACKEND_DIR_NAME


def install_root() -> Path:
    """This node's install root, from the SSOT path config (never a literal)."""
    return Path(config.path.base_dir)


def node_identity() -> str:
    """Which installation this is. A proposal carries it, and only the same node may execute the approval."""
    return platform.node()


def _inside(path: Path, root: Path) -> bool:
    """Whether *path* resolves under *root* (both resolved, symlinks followed)."""
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


def _is_checkout(root: Path) -> bool:
    """A git checkout holds `.git` at its top; AUTOBOT_BASE_DIR may name the ``autobot-backend`` directory inside it."""
    if os.path.lexists(root / ".git"):
        return True
    return root.name == BACKEND_DIR_NAME and os.path.lexists(root.parent / ".git")


def plan_env_copies(root: Path | None = None) -> CleanupPlan:
    """Which ``.env.*~`` copies to remove: all but the newest. Reads names and mtimes only."""
    root = root or install_root()
    if _is_checkout(root):
        return CleanupPlan(refused="the install root is a checkout, so these are not deployed files")
    backend = _backend_dir(root)
    if backend.is_symlink() or not _inside(backend, root):
        return CleanupPlan(refused="the backend directory is a symlink or outside the install root")
    if not backend.is_dir():
        return CleanupPlan()
    stat = backend.stat()
    found = sorted(backend.glob(ENV_COPY_GLOB), key=lambda p: p.name)
    for path in found:
        if path.is_symlink() or not path.is_file() or not _inside(path, backend):
            return CleanupPlan(refused=f"{path.name} is a symlink, not a regular file, or outside the install root")
    ranked = sorted(found, key=lambda p: (p.stat().st_mtime, p.name))
    if len(ranked) < 2:
        return CleanupPlan(kept=ranked[0] if ranked else None, backend_id=(stat.st_dev, stat.st_ino))
    return CleanupPlan(targets=tuple(ranked[:-1]), kept=ranked[-1], backend_id=(stat.st_dev, stat.st_ino))


def _open_pinned_backend(backend: Path, expected: tuple[int, int] | None) -> int:
    """An fd on the backend directory itself: a symlink is refused (``O_NOFOLLOW``) and it must be the planned one."""
    fd = os.open(backend, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    stat = os.fstat(fd)
    if expected is None or (stat.st_dev, stat.st_ino) != expected:
        os.close(fd)
        raise ValueError("the backend directory changed after it was planned; nothing removed")
    return fd


def _remove_env_copies(plan: CleanupPlan, root: Path) -> int:
    """Unlink each target relative to the pinned directory fd, so a swapped path cannot redirect the removal."""
    fd = _open_pinned_backend(_backend_dir(root), plan.backend_id)
    removed = 0
    try:
        for path in plan.targets:
            info = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
            if not stat_module.S_ISREG(info.st_mode):
                raise ValueError(f"{path.name} changed to a symlink or left the install root; nothing further removed")
            os.unlink(path.name, dir_fd=fd)
            removed += 1
    finally:
        os.close(fd)
    return removed


async def _audit(
    approval: "Approval",
    action: AuditAction,
    result: AuditResult,
    **details: object,
) -> bool:
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


_AUDIT = AuditAction.CLEANUP_ENV_COPIES


async def _stop_without_removal(approval: "Approval", session: "AsyncSession", reason: str, own: bool) -> None:
    """A refused run removes nothing: record why, then raise so the approval shows the failure."""
    await _audit(approval, _AUDIT, "denied", reason=reason, self_approval=own)
    await _record(approval, session, f"Nothing removed: {reason}.")
    raise ValueError(reason)


async def _record_intent(approval: "Approval", session: "AsyncSession", names: list[str], own: bool) -> None:
    """The paper trail comes first: no committed entry means nothing is removed (#17038)."""
    if await _audit(approval, _AUDIT, "attempted", phase="intent", paths=names, self_approval=own):
        return
    await _record(approval, session, "Nothing removed: the audit entry could not be written.")
    raise ValueError("the audit entry could not be written, so nothing was removed")


async def _remove_audited(approval: "Approval", plan: CleanupPlan, root: Path, own: bool) -> int:
    try:
        return await asyncio.to_thread(_remove_env_copies, plan, root)
    except (OSError, ValueError) as exc:
        await _audit(approval, _AUDIT, "failed", error=type(exc).__name__, self_approval=own)
        raise


async def execute_env_copies_cleanup(approval: "Approval", session: "AsyncSession") -> None:
    """Remove all but the newest ``.env.*~`` copy once a human approved it: four eyes, re-plan, audit first."""
    own = await is_self_approval(approval, session, what="the .env.*~ cleanup")
    if (approval.context or {}).get("node") != node_identity():
        await _stop_without_removal(approval, session, "the approval was raised for another installation", own)
    root = install_root()
    plan = await asyncio.to_thread(plan_env_copies, root)
    if plan.refused:
        await _stop_without_removal(approval, session, plan.refused, own)
    if not plan.targets:
        await _audit(approval, _AUDIT, "success", removed=0, self_approval=own)
        await _record(approval, session, "Nothing to remove: no .env.*~ copies found.")
        return
    names = [str(p.relative_to(root)) for p in plan.targets]
    await _record_intent(approval, session, names, own)
    removed = await _remove_audited(approval, plan, root, own)
    await _audit(approval, _AUDIT, "success", phase="completion", removed=removed, paths=names, self_approval=own)
    suffix = " (self-approved by the only admin)." if own else "."
    await _record(approval, session, f"Removed {removed} .env.*~ copies: {', '.join(names)}{suffix}")


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
    "node_identity",
    "plan_env_copies",
    "register_install_cleanup_actions",
]
