# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The contract between the SLM and the backend for a stored SSH password's deletion (#20046, #17038).

The SLM proposes the deletion to the backend's one approval queue; once a human approves it, the backend
asks the SLM to delete the password. Both services read their route paths and the action name from here,
so the two ends cannot drift apart.
"""

from __future__ import annotations

#: The ``context["action"]`` an approval names to route to the executor.
ACTION = "slm_node_ssh_password_delete"
#: The credential kind a proposal names (never the value).
CREDENTIAL_KIND = "ssh_password"  # nosec B105  # pragma: allowlist secret -- a kind label, not a password
#: The backend path the SLM POSTs a proposal to (internal key only).
PROPOSAL_PATH = "/api/internal/slm/ssh-password-deletion-proposals"
#: The SLM path template the backend DELETEs through once approved (internal key only).
DELETE_PATH_TEMPLATE = "/api/internal/nodes/{node_id}/ssh-password"  # nosec B105  # pragma: allowlist secret


def proposer_id(node_id: str) -> str:
    """The ``requested_by_agent`` of a node's proposal; with the action it makes the pending one findable."""
    return f"slm-enrollment:{node_id}"


def delete_path(node_id: str) -> str:
    """The SLM path that deletes *node_id*'s stored SSH password fields."""
    return DELETE_PATH_TEMPLATE.format(node_id=node_id)
