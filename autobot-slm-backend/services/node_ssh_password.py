# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A node's stored SSH password: propose its deletion, and delete it once a human approved (#20046, #17038).

Enrollment keeps the encrypted password (#19483). After a proven enrollment this proposes its deletion to
the backend's approval queue; the backend calls ``delete_stored_password`` through the internal route only
after a human approved. Nothing else in the SLM deletes it. Enrollment never depends on the backend being
up (ADR-012): a failed proposal is logged and enrollment carries on.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared import node_proxy
from autobot_shared.slm_credential_deletion import ACTION, CREDENTIAL_KIND, PROPOSAL_PATH
from config import settings
from models.database import Node

logger = logging.getLogger(__name__)

#: The ``extra_data`` keys that hold the password and the flag describing it.
_PASSWORD_KEYS = ("ssh_password", "ssh_password_encrypted")  # nosec B105  # pragma: allowlist secret


def has_stored_password(node: Node) -> bool:
    """Whether *node* holds an SSH password; reads the key's presence, never the value."""
    return bool((node.extra_data or {}).get("ssh_password"))


async def propose_password_deletion(node: Node) -> bool:
    """Ask the backend's approval queue to propose deleting *node*'s stored password; never raises.

    Returns True when the backend accepted it (a repeat for a node with a pending proposal is accepted
    and creates no second one). A node with no stored password proposes nothing. Not retried by a timer:
    a later enrollment of the node proposes again, and the backend de-duplicates.
    """
    if not has_stored_password(node):
        return False
    base_url = node_proxy.resolve_node_url(settings.authority_base_url)
    if not base_url or not node_proxy.internal_api_key():
        logger.warning("Deletion of node %s's stored SSH password not proposed: backend URL or key unset", node.node_id)
        return False
    body: dict[str, Any] = {"node_id": node.node_id, "credential_kind": CREDENTIAL_KIND}
    try:
        async with node_proxy.node_client() as client:
            response = await client.post(f"{base_url}{PROPOSAL_PATH}", json=body, headers=node_proxy.internal_headers())
        response.raise_for_status()
    except httpx.HTTPError as exc:
        if isinstance(exc, httpx.HTTPStatusError):
            reason = f"backend answered HTTP {exc.response.status_code}"
        else:
            reason = node_proxy.classify_transport_error(exc).reason
        logger.error(
            "Deletion of node %s's stored SSH password not proposed (%s); a later enrollment proposes again",
            node.node_id,
            reason,
        )
        return False
    logger.info("Proposed %s for node %s: the stored SSH password awaits a human decision", ACTION, node.node_id)
    return True


async def delete_stored_password(db: AsyncSession, node_id: str) -> bool | None:
    """Delete only *node_id*'s stored SSH password fields; True if any were removed, None if no such node."""
    node = (await db.execute(select(Node).where(Node.node_id == node_id))).scalar_one_or_none()
    if node is None:
        return None
    extra = dict(node.extra_data or {})
    removed = [extra.pop(key, None) is not None for key in _PASSWORD_KEYS]
    if any(removed):
        node.extra_data = extra  # reassigned: an in-place edit of a JSON column is not tracked
        await db.commit()
    logger.info("Stored SSH password of node %s deleted after approval: %s", node_id, any(removed))
    return any(removed)
