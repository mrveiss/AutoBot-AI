# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The contract between the SLM and the backend for removing stale files left under the old code-sync targets (#22033).

Before #22030 the code-sync rsynced four roles into the install root itself and the agent into the agent
directory; each now has its own directory, so the old copies stay behind. They are removed only after a human
approves a proposal in the backend's one approval queue (#17038):

1. an admin asks the SLM to propose for a node; the SLM lists the files read-only and POSTs ``PROPOSAL_PATH``
   (one proposal per old sync location per node, at most ``MAX_FILES_PER_PROPOSAL`` files);
2. a human approves it in the Approvals inbox, whose description lists every file (path, size, age);
3. the backend's ``server_only`` executor calls the SLM's ``REMOVAL_PATH_TEMPLATE`` route;
4. the SLM lists afresh, claims the approval at ``CLAIM_PATH_TEMPLATE`` (verified as a human's, spent once) and removes
   only the approved files that are still stale.

The claim is the generic ``slm_credential_claim`` one, driven by :data:`STALE_SYNC_FILES_CLEANUP`.
Both services read the names and the paths from here, so the two ends cannot drift.
"""

from __future__ import annotations

from autobot_shared.env_utils import env_float_clamped, env_int_clamped
from autobot_shared.slm_credential_actions import SlmApprovalAction

STALE_SYNC_FILES_CLEANUP = SlmApprovalAction(
    name="slm_node_stale_sync_files_cleanup",
    credential_kind="stale_sync_files",  # nosec B106  # pragma: allowlist secret -- a kind label, not a credential
    proposer_prefix="slm-code-sync",
)

#: The most files one proposal lists; the cap counts items and never shortens a path (#22033, owner D5).
MAX_FILES_PER_PROPOSAL = env_int_clamped("SLM_STALE_SYNC_FILES_MAX_PER_PROPOSAL", 200, 1, 1000)

#: Seconds one listing or removal over ssh may run; the backend waits for twice that (a listing and a removal).
SSH_TIMEOUT_SECONDS = env_float_clamped(
    "SLM_STALE_SYNC_FILES_SSH_TIMEOUT_SECONDS", 120.0, 5.0, 900.0, positive_finite=True
)

#: The ``context`` key naming the one old sync location of one node a proposal covers (``<node>:<old target>``).
LOCATION_KEY = "location"

#: The backend path a proposal is POSTed to (internal key only).
PROPOSAL_PATH = "/api/internal/slm/stale-file-proposals"
#: The backend path that verifies and spends an approval, before any file is removed (internal key only).
CLAIM_PATH_TEMPLATE = "/api/internal/slm/stale-file-approvals/{approval_id}/claim"
#: The SLM path the backend POSTs to once approved (internal key only); the approval id is the query parameter.
REMOVAL_PATH_TEMPLATE = "/api/internal/nodes/{node_id}/stale-sync-files/removal"

#: ``result`` of one file in a removal report; only ``removed`` means the file is gone, and ``failed`` -- an
#: unlink or a read that failed, or a path the node did not answer for -- makes the whole removal a failure.
RESULT_REMOVED = "removed"
RESULT_FAILED = "failed"
RESULTS = frozenset({RESULT_REMOVED, "refused", "changed", "absent", "no_longer_stale", RESULT_FAILED})


def api_relative(path: str) -> str:
    """*path* without its ``/api/`` prefix, the form ``call_main_backend`` takes."""
    return path.removeprefix("/api/")


def location(node_id: str, old_target: str) -> str:
    """The key of one old sync location on one node: at most one proposal is pending for it."""
    return f"{node_id}:{old_target}"
