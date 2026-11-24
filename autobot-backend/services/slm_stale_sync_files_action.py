# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Remove a node's stale code-sync files only after a human approves the proposal (#22033, #17038).

The SLM proposes through ``api.internal_slm_stale_file_proposals`` after an admin asks it to. The files live
on the node, so an approved proposal calls the SLM's internal route; the SLM lists afresh, claims the
approval (verified as a human's, spent once) and removes only the approved files that are still byte-identical
to what git tracked. A rejected proposal runs nothing, so every file stays. Every step writes a durable audit
row, the intent row BEFORE the call: no row, no removal.
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import TYPE_CHECKING, Any

import aiohttp

from autobot_shared import node_proxy
from autobot_shared.http_egress_guard import assert_egress_policy
from autobot_shared.logging_manager import get_logger
from autobot_shared.slm_credential_actions import APPROVAL_QUERY, slm_direct_url
from autobot_shared.slm_stale_file_actions import (
    RESULT_REMOVED,
    SSH_TIMEOUT_SECONDS,
    STALE_SYNC_FILES_CLEANUP,
    removal_path,
)
from models.approval import ApprovalComment
from services.approval_execution import register_post_approval_action, verified_decider
from services.audit.taxonomy import AuditAction
from services.audit_logger import audit_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

logger = get_logger(__name__)

#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "api.internal_slm_stale_file_proposals"


async def _remove_in_slm(node_id: str, approval_id: str) -> dict[str, Any]:
    """Ask the SLM to remove the approved files; it re-verifies *approval_id* with this backend first."""
    if not node_proxy.internal_api_key():
        raise RuntimeError("the internal service key is not configured")
    url = f"{slm_direct_url()}{removal_path(node_id)}"
    await assert_egress_policy(url)  # #17576
    timeout = aiohttp.ClientTimeout(total=max(node_proxy.node_timeout(), SSH_TIMEOUT_SECONDS * 2))
    async with aiohttp.ClientSession(headers=node_proxy.internal_headers()) as http:
        async with http.post(
            url, params={APPROVAL_QUERY: approval_id}, timeout=timeout, allow_redirects=False
        ) as response:
            if response.status != 200:
                raise RuntimeError(f"the SLM answered HTTP {response.status}")
            return dict(await response.json())


async def _audit(approval: "Approval", result: str, **details: object) -> bool:
    """Whether the entry was written. Durable: the entry before a removal must not be lost (#17038)."""
    return await audit_log(
        AuditAction.CODE_SYNC_STALE_FILES_CLEANUP,
        result=result,
        durable=True,
        user_id=approval.decided_by_user,
        resource=f"node:{(approval.context or {}).get('node_id')}",
        details={
            "approval_id": str(approval.id),
            "credential_kind": STALE_SYNC_FILES_CLEANUP.credential_kind,
            **details,
        },
    )


def _summary(report: dict[str, Any]) -> Counter:
    """Per-result counts of the SLM's removal report."""
    return Counter(str(item.get("result")) for item in report.get("results", []))


async def execute_stale_sync_files_cleanup(approval: "Approval", session: "AsyncSession") -> None:
    """Remove the files an approved gate named; the SLM does the removal, this records it."""
    node_id = str((approval.context or {}).get("node_id") or "")
    if not node_id or not isinstance(verified_decider(approval), uuid.UUID):
        await _audit(approval, "denied", reason="no node id or no verified human decider")
        raise ValueError("the removal needs a node id and a verified human decider")
    # The paper trail comes first: no committed entry means nothing is removed (#17038).
    if not await _audit(approval, "success", phase="intent"):
        raise ValueError("the audit entry could not be written, so nothing was removed")
    try:
        report = await _remove_in_slm(node_id, str(approval.id))
    except Exception as exc:
        await _audit(approval, "failed", phase="completion", error=type(exc).__name__)
        raise
    counts = _summary(report)
    body = "Stale code-sync files: " + (", ".join(f"{n} {name}" for name, n in sorted(counts.items())) or "none listed")
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()
    await _audit(approval, "success", phase="completion", removed=counts[RESULT_REMOVED], results=dict(counts))


def register_stale_sync_files_action() -> None:
    """Idempotent: re-registering just replaces the same key with an equal handler."""
    register_post_approval_action(
        STALE_SYNC_FILES_CLEANUP.name,
        execute_stale_sync_files_cleanup,
        proposed_by=PROPOSED_BY,
        server_only=True,
        admin_only=True,
    )


__all__ = ["PROPOSED_BY", "execute_stale_sync_files_cleanup", "register_stale_sync_files_action"]
