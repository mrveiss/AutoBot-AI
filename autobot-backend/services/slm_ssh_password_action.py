# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Delete a node's stored SSH password in the SLM only after a human approves it (#20046, #17038).

The SLM proposes through ``api.internal_slm_credential_proposals`` after a proven enrollment. The password
lives in the SLM's database, so an approved proposal calls the SLM's internal route to delete it. A
rejected proposal runs nothing, so the password stays. The audit entry records the node and the credential
kind, never a value.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import aiohttp

from autobot_shared import node_proxy
from autobot_shared.logging_manager import get_logger
from autobot_shared.slm_credential_deletion import ACTION, CREDENTIAL_KIND, delete_path
from autobot_shared.slm_rest_url import rest_url
from autobot_shared.ssot_config import config
from autobot_shared.tls import get_internal_tls_context
from models.approval import ApprovalComment
from services.approval_execution import register_post_approval_action, verified_decider
from services.audit_logger import audit_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

logger = get_logger(__name__)

#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "api.internal_slm_credential_proposals"
_AUDIT_ACTION = "node.ssh_password.delete"  # an AuditAction member (services/audit/taxonomy.py)


async def _delete_in_slm(node_id: str) -> bool | None:
    """Ask the SLM to delete the node's stored password; True if removed, False if none, None if no such node."""
    slm_url = config.slm_url.rstrip("/")
    if not slm_url or not node_proxy.internal_api_key():
        raise RuntimeError("the SLM URL or the internal service key is not configured")
    url = rest_url(slm_url, delete_path(node_id))
    connector = aiohttp.TCPConnector(ssl=get_internal_tls_context())
    timeout = aiohttp.ClientTimeout(total=node_proxy.node_timeout())
    async with aiohttp.ClientSession(headers=node_proxy.internal_headers(), connector=connector) as http:
        async with http.delete(url, timeout=timeout) as response:
            if response.status == 404:
                return None
            if response.status != 200:
                raise RuntimeError(f"the SLM answered HTTP {response.status}")
            return bool((await response.json()).get("deleted"))


async def _audit(approval: "Approval", result: str, **details: object) -> None:
    await audit_log(
        _AUDIT_ACTION,
        result=result,
        user_id=approval.decided_by_user,
        resource=f"node:{(approval.context or {}).get('node_id')}",
        details={"approval_id": str(approval.id), "credential_kind": CREDENTIAL_KIND, **details},
    )


async def execute_ssh_password_delete(approval: "Approval", session: "AsyncSession") -> None:
    """Delete the password an approved gate named; the SLM does the deletion, this records it."""
    node_id = str((approval.context or {}).get("node_id") or "")
    decider = verified_decider(approval)
    if not node_id or not isinstance(decider, uuid.UUID):
        await _audit(approval, "denied", reason="no node id or no verified human decider")
        raise ValueError("the deletion needs a node id and a verified human decider")
    try:
        removed = await _delete_in_slm(node_id)
    except Exception as exc:
        await _audit(approval, "failed", error=type(exc).__name__)
        raise
    body = {
        True: "Stored SSH password deleted.",
        False: "The node held no stored SSH password.",
        None: "The node no longer exists.",
    }
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body[removed]))
    await session.commit()
    await _audit(approval, "success", removed=removed)


def register_ssh_password_action() -> None:
    """Idempotent: re-registering just replaces the same key with an equal handler."""
    register_post_approval_action(ACTION, execute_ssh_password_delete, proposed_by=PROPOSED_BY, server_only=True)


__all__ = ["ACTION", "PROPOSED_BY", "execute_ssh_password_delete", "register_ssh_password_action"]
