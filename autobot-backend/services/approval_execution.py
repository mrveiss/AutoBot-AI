# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Post-approval execution registry (#17038, #17039, #17043).

An approval gate only decides yes/no; it has no idea what "yes" should DO.
An owning service that wants its own action gated -- propose it, execute
only once a human approves -- registers a handler here, keyed by
``Approval.context["action"]``, the same way ``services.orphan_storage``
lets a data-owning module register its own detector (#17038's "detection
lives with the owner of the data", extended to execution). Nothing in the
approval-gate layer needs to know what any action does; it only dispatches.

A handler failure is reported, never left to crash the approve() response and
never allowed to undo the approval decision itself -- the human's "yes"
already happened and stays recorded; whether the resulting action succeeded
is a separate fact the handler itself is responsible for recording (#17038
rule 3, paper trail).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable

from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

logger = get_logger(__name__)

PostApprovalAction = Callable[["Approval", "AsyncSession"], Awaitable[None]]

_REGISTRY: dict[str, PostApprovalAction] = {}


def register_post_approval_action(action: str, handler: PostApprovalAction) -> None:
    """Register *handler* to run when an approved gate's context names *action*."""
    _REGISTRY[action] = handler


async def run_post_approval_actions(approval: "Approval", session: "AsyncSession") -> None:
    """Dispatch on ``approval.context["action"]``; a no-op for anything unregistered.

    Called only after the transition to APPROVED already committed -- see
    ``ApprovalGateService.approve()`` -- so a handler failure here can never
    prevent or roll back the approval decision itself.
    """
    action = (approval.context or {}).get("action")
    if not action:
        return
    handler = _REGISTRY.get(action)
    if handler is None:
        return
    try:
        await handler(approval, session)
    except Exception:
        logger.exception("Post-approval action %r failed for approval %s", action, approval.id)
