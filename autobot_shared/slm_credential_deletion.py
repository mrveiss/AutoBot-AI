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

import ipaddress

#: The ``context["action"]`` an approval names to route to the executor.
ACTION = "slm_node_ssh_password_delete"
#: The credential kind a proposal names (never the value).
CREDENTIAL_KIND = "ssh_password"  # nosec B105  # pragma: allowlist secret -- a kind label, not a password
#: The backend path the SLM POSTs a proposal to (internal key only).
PROPOSAL_PATH = "/api/internal/slm/ssh-password-deletion-proposals"
#: The SLM path template the backend DELETEs through once approved (internal key only).
DELETE_PATH_TEMPLATE = "/api/internal/nodes/{node_id}/ssh-password"  # nosec B105  # pragma: allowlist secret
#: The backend path the SLM POSTs to, before deleting, to verify and consume an approval (internal key only).
CLAIM_PATH_TEMPLATE = "/api/internal/slm/ssh-password-deletion-approvals/{approval_id}/claim"
#: The SLM's 404 detail for a node it does not know; any other 404 means the call reached the wrong place.
NODE_NOT_FOUND_DETAIL = "Node not found"
#: Query parameter that carries the approval id on the SLM delete route.
APPROVAL_QUERY = "approval_id"


class PlainHttpToRemoteSlmError(ValueError):
    """The internal key would cross the network in clear text to a non-loopback SLM (#20899, option A)."""


#: The user-facing refusal when SLM and backend run on different machines without SLM TLS (#20899).
SPLIT_DEPLOYMENT_MESSAGE = (
    "Stored SSH password deletion is unavailable when the SLM and the backend run on different machines "
    "without TLS on the SLM: the internal key would be sent unencrypted. Enable SLM TLS or run both on one machine."
)


def is_loopback_host(host: str) -> bool:
    """Whether *host* is a literal loopback address or ``localhost``; any other name or address is remote."""
    if host.strip().lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip().strip("[]")).is_loopback
    except ValueError:
        return False


def is_split_without_tls() -> bool:
    """Whether the SLM is on a non-loopback host with TLS off, so the flow cannot run safely (#20899)."""
    from autobot_shared.ssot_config import config  # noqa: PLC0415  (this module is imported by the SLM too)

    return not config.tls.slm_tls_enabled and not is_loopback_host(config.vm.slm)


def slm_direct_url() -> str:
    """The SLM's own uvicorn URL, scheme and port from the SSOT TLS config, never the nginx edge ``SLM_URL`` names.

    The edge denies ``/api/internal/`` (#20046), and uvicorn has no ``/slm`` prefix, so the backend's call
    to the SLM's internal route goes here directly. Raises ``PlainHttpToRemoteSlmError`` rather than return
    a plain-http URL for a non-loopback SLM: the internal key is never sent in clear text over the network.
    """
    from autobot_shared.ssot_config import config  # noqa: PLC0415

    if config.tls.slm_tls_enabled:
        return f"https://{config.vm.slm}:{config.tls.slm_tls_port}"
    if not is_loopback_host(config.vm.slm):
        raise PlainHttpToRemoteSlmError(SPLIT_DEPLOYMENT_MESSAGE)
    return f"http://{config.vm.slm}:{config.port.slm}"


def claim_path(approval_id: str) -> str:
    """The backend path that verifies and consumes *approval_id*."""
    return CLAIM_PATH_TEMPLATE.format(approval_id=approval_id)


def proposer_id(node_id: str) -> str:
    """The ``requested_by_agent`` of a node's proposal; with the action it makes the pending one findable."""
    return f"slm-enrollment:{node_id}"


def delete_path(node_id: str) -> str:
    """The SLM path that deletes *node_id*'s stored SSH password fields."""
    return DELETE_PATH_TEMPLATE.format(node_id=node_id)
