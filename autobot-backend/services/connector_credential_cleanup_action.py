# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Removes clear-text credential copies from a connector record, only behind an approved request (#20701).

A proposal is an ordinary approval-gate request (``destructive_action``) whose ``context`` names this action
and the connector. Approving it runs :func:`execute_connector_credential_strip`, which re-checks at THIS point
that the record still holds the values and that the secrets store holds the same credential. Rotating the
exposed credential is NOT automated: the proposal text names the connector to rotate and a human does it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.approval_execution import register_post_approval_action
from services.connector_credential_scan import strip_sensitive_fields
from services.kb_cleanup_proposals import record_cleanup_outcome, require_context

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "connector_credential_strip"
#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "api.admin_connector_credentials"


async def execute_connector_credential_strip(approval: "Approval", session: "AsyncSession") -> None:
    """Strip the clear-text copies from the connector the approved gate named, and record what happened."""
    (connector_id,) = require_context(approval, "connector_id")
    done, reason = await strip_sensitive_fields(connector_id)
    await record_cleanup_outcome(
        approval,
        session,
        operation="connector_credentials.strip",
        done=done,
        resource=f"connector:{connector_id}",
        summary="Connector credential cleanup",
        reason=reason,
    )


def register_connector_credential_strip() -> None:
    """Idempotent. Server-only and admin-decided: this approves rewriting stored credential data."""
    register_post_approval_action(
        ACTION, execute_connector_credential_strip, proposed_by=PROPOSED_BY, server_only=True, admin_only=True
    )


__all__ = ["ACTION", "PROPOSED_BY", "execute_connector_credential_strip", "register_connector_credential_strip"]
