# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A durable paper trail for restoring or deleting a knowledge backup (#19721, #17038).

The intent entry is committed before the file or the facts change, and no entry means the action does not
run. It says the action was ordered, not that it worked: a second entry records how it ended.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable
from typing import Any

from services.audit.taxonomy import AuditAction
from services.audit_logger import audit_log


async def audit_backup_action(action: AuditAction, actor: str, filename: str) -> bool:
    """Whether the intent entry for *action* on the backup *filename* was committed."""
    return await audit_log(action.value, user_id=actor, resource=filename, durable=True, details={"phase": "intent"})


async def _audit_outcome(action: AuditAction, actor: str, filename: str, succeeded: bool) -> None:
    """Record how the action ended. It has already happened, so a lost entry cannot change the answer."""
    await audit_log(
        action.value,
        "success" if succeeded else "failed",
        user_id=actor,
        resource=filename,
        durable=True,
        details={"phase": "completion"},
    )


async def run_audited(action: AuditAction, actor: str, filename: str, work: Awaitable[Any]) -> Any:
    """Await *work* and record how it ended: a raise or a result counting errors is a failure."""
    try:
        result = await work
    except Exception:
        await _audit_outcome(action, actor, filename, succeeded=False)
        raise
    await _audit_outcome(action, actor, filename, succeeded=not (isinstance(result, dict) and result.get("errors")))
    return result


def resolve_backup_name(backup_dir: str, name: str) -> str | None:
    """The path of a backup named by its bare filename, inside *backup_dir*, or None.

    Issue #19721: the name the list returns is what comes back, and it resolves against the backup
    directory rather than the process's cwd. Issue #9670: anything else is refused, ``../`` and
    absolute paths included. A symlink is refused wherever it points: the entry would name one
    file and the action would reach another.
    """
    if not name or name in (".", "..") or os.path.basename(name) != name or "\\" in name or "\x00" in name:
        return None
    allowed_root = os.path.realpath(backup_dir)
    candidate = os.path.join(allowed_root, name)
    if os.path.islink(candidate):
        return None
    resolved = os.path.realpath(candidate)
    return resolved if resolved.startswith(allowed_root + os.sep) else None
