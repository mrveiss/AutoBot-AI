# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The contract between the SLM and the backend for a stored credential an agent may only PROPOSE to change.

One table, one proposal route, one claim (#17038, #20046, #20750). The SLM, or the updater it runs,
proposes a change to the backend's one approval queue; a human approves or rejects it there; the side
that applies the change first claims the approval, which verifies a human decided it and spends it
once. Each action differs only in what it changes and how it is applied:

- ``SSH_PASSWORD_DELETE`` (#20046): the backend's executor asks the SLM to delete a node's stored SSH
  password, and the SLM claims before it deletes.
- ``INTERNAL_KEY_REALIGN`` (#20750): an update re-renders the backend's AUTOBOT_INTERNAL_API_KEY to
  the SLM's. The two keys differ in this case, so neither service can call the other with its own
  key; the updater proposes, claims and reports with the backend's CURRENT key, and applies the
  change itself at the node's next update.

Both services read the route paths and the action names from here, so the two ends cannot drift.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CredentialAction:
    """One kind of credential change: what an approval names, and who proposed it."""

    #: The ``context["action"]`` an approval names to route to its executor.
    name: str
    #: The credential kind a proposal names (never the value).
    credential_kind: str
    #: ``requested_by_agent`` is ``<prefix>:<node_id>``; with the action it makes a node's proposal findable.
    proposer_prefix: str

    def proposer_id(self, node_id: str) -> str:
        return f"{self.proposer_prefix}:{node_id}"


SSH_PASSWORD_DELETE = CredentialAction(
    name="slm_node_ssh_password_delete",
    credential_kind="ssh_password",  # nosec B106  # pragma: allowlist secret -- a kind label, not a password
    proposer_prefix="slm-enrollment",
)
INTERNAL_KEY_REALIGN = CredentialAction(
    name="slm_backend_internal_key_realign",
    credential_kind="internal_api_key",  # nosec B106  # pragma: allowlist secret -- a kind label, not a key
    proposer_prefix="slm-update",
)
#: Every action, by its approval ``context["action"]`` name.
ACTIONS = {action.name: action for action in (SSH_PASSWORD_DELETE, INTERNAL_KEY_REALIGN)}

#: The backend path a proposal is POSTed to (internal key only).
PROPOSAL_PATH = "/api/internal/slm/credential-proposals"
#: The backend path that verifies and spends an approval, before the change is applied (internal key only).
CLAIM_PATH_TEMPLATE = "/api/internal/slm/credential-approvals/{approval_id}/claim"
#: The backend path the applying side reports the outcome to, for the audit trail (internal key only).
OUTCOME_PATH_TEMPLATE = "/api/internal/slm/credential-approvals/{approval_id}/outcome"

# --- SSH_PASSWORD_DELETE's apply step: the backend calls the SLM -------------------------------------
#: The SLM path template the backend DELETEs through once approved (internal key only).
DELETE_PATH_TEMPLATE = "/api/internal/nodes/{node_id}/ssh-password"  # nosec B105  # pragma: allowlist secret
#: The SLM's 404 detail for a node it does not know; any other 404 means the call reached the wrong place.
NODE_NOT_FOUND_DETAIL = "Node not found"
#: Query parameter that carries the approval id on the SLM delete route.
APPROVAL_QUERY = "approval_id"


def claim_path(approval_id: str) -> str:
    """The backend path that verifies and spends *approval_id*."""
    return CLAIM_PATH_TEMPLATE.format(approval_id=approval_id)


def outcome_path(approval_id: str) -> str:
    """The backend path that records how applying *approval_id* went."""
    return OUTCOME_PATH_TEMPLATE.format(approval_id=approval_id)


def delete_path(node_id: str) -> str:
    """The SLM path that deletes *node_id*'s stored SSH password fields."""
    return DELETE_PATH_TEMPLATE.format(node_id=node_id)
