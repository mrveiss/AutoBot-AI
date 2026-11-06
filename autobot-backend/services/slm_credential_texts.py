# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What each SLM credential-action proposal tells the person deciding it, and its audit trail (#20046, #20750).

A proposal is approved in the Approvals inbox by someone who has to know what the change does, when it
happens and what depends on the credential. So each action's text names all three; none names a value.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from autobot_shared.slm_credential_actions import INTERNAL_KEY_REALIGN, SSH_PASSWORD_DELETE, CredentialAction
from services.audit.taxonomy import AuditAction
from services.audit_logger import audit_log

if TYPE_CHECKING:
    from models.approval import Approval

_REALIGN_DESCRIPTION = (
    "The backend's AUTOBOT_INTERNAL_API_KEY on node {node} differs from the SLM's, so the backend refuses "
    "every call the SLM makes with its key. Approving re-aligns the backend's key to the SLM's.\n\n"
    "When: at this node's NEXT update through the builtin updater. Nothing changes when you approve; the "
    "update applies it, restarts the backend and its celery workers, then checks the backend accepts the "
    "new key and records the result here.\n\n"
    "Fixed by it (they send the SLM's key and fail today): the System vault (SSO and LLM secrets, the VNC "
    "password registration), and the SLM's voice, personality and memory proxies.\n\n"
    "Still on the old key until then, and changed by it: the backend and its celery workers, which load "
    "the same env file. The SLM agent role falls back to the backend's env file only when the SLM's own "
    "secrets file has no key, so an agent installed that way keeps the old key until its next deploy.\n\n"
    "Rejecting keeps the backend's current key; the mismatch stays and is reported on every update (#20750)."
)

_SSH_DESCRIPTION = (
    "Node {node} enrolled and now uses key authentication, so its stored SSH password is no longer "
    "needed. Approving deletes the stored password for good; rejecting keeps it."
)

_TEXTS = {
    SSH_PASSWORD_DELETE.name: ("Delete the stored SSH password of node {node}", _SSH_DESCRIPTION),
    INTERNAL_KEY_REALIGN.name: ("Re-align node {node}'s backend internal API key to the SLM's", _REALIGN_DESCRIPTION),
}

_REALIGN_AUDIT = {
    "proposed": AuditAction.INTERNAL_KEY_REALIGN_PROPOSED,
    "claimed": AuditAction.INTERNAL_KEY_REALIGN_CLAIMED,
    "applied": AuditAction.INTERNAL_KEY_REALIGN_APPLIED,
    "apply_failed": AuditAction.INTERNAL_KEY_REALIGN_APPLY_FAILED,
}


def proposal_text(action: CredentialAction, node_id: str) -> tuple[str, str]:
    """The approval's title and description for *action* on *node_id*."""
    title, description = _TEXTS[action.name]
    return title.format(node=node_id), description.format(node=node_id)


async def _write_step(
    step: str, approval_id: object, node_id: object, user_id: object, result: str, detail: str
) -> bool:
    details = {"approval_id": str(approval_id), "credential_kind": INTERNAL_KEY_REALIGN.credential_kind}
    if detail:
        details["detail"] = detail
    return await audit_log(
        _REALIGN_AUDIT[step].value,
        result=result,
        durable=True,
        user_id=user_id,
        resource=f"node:{node_id}",
        details=details,
    )


async def record_realign_step(step: str, approval: "Approval", result: str, detail: str = "") -> bool:
    """One durable audit entry per realign step: proposed, claimed, applied, apply-failed. Never a key value."""
    node_id = (approval.context or {}).get("node_id")
    user_id = approval.decided_by_user or approval.requested_by_agent
    return await _write_step(step, approval.id, node_id, user_id, result, detail)


async def record_realign_proposal(approval_id: uuid.UUID, node_id: str, proposer: str) -> bool:
    """The "proposed" row, written BEFORE the approval exists, so it names the id the approval will take."""
    return await _write_step("proposed", approval_id, node_id, proposer, "success", "")
