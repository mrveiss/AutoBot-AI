# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An approved re-alignment of the backend's internal API key applies at the node's next update (#20750, #17038).

Unlike #20046's SSH-password deletion, this executor cannot call the SLM: the two services' internal keys
DIFFER in exactly this case, so each refuses the other. The updater holds the backend's current key, so
the updater applies it: at the node's next builtin update it claims this approval, re-renders the key,
restarts the backend and celery, checks the new key works and reports the outcome. Approving therefore
changes nothing here; it records on the approval that the change waits for that update.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autobot_shared.slm_credential_actions import INTERNAL_KEY_REALIGN
from models.approval import ApprovalComment
from services.approval_execution import register_post_approval_action

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "api.internal_slm_credential_proposals"


async def execute_internal_key_realign(approval: "Approval", session: "AsyncSession") -> None:
    """Record that the approved realign waits for the node's next update; the updater applies and reports it."""
    node_id = str((approval.context or {}).get("node_id") or "")
    body = (
        f"Approved. Node {node_id}'s backend key is re-aligned at its next update through the builtin "
        "updater, which restarts the backend and celery and records the result here."
    )
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()


def register_internal_key_realign_action() -> None:
    """Idempotent: re-registering just replaces the same key with an equal handler."""
    register_post_approval_action(
        INTERNAL_KEY_REALIGN.name, execute_internal_key_realign, proposed_by=PROPOSED_BY, server_only=True
    )


__all__ = ["PROPOSED_BY", "execute_internal_key_realign", "register_internal_key_realign_action"]
