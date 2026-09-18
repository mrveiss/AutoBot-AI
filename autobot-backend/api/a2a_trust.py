# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A2A trust administration: observe peers' trust, and re-grant it after the #16950 re-key.

The three read routes moved here unchanged from ``api/a2a.py`` (#16950), joined by
the two the re-key needs:

- ``POST /trust/grant``: an admin sets a (credential, peer id) pair's level.
- ``GET /trust-legacy``: the pre-#16950 header-only records, read-only, so an admin
  can see whom to re-grant.

Mounted under the same ``/a2a`` prefix, admin-gated at the router like ``api/a2a.py``.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from a2a.peer_identity import credential_subject, peer_trust_key
from a2a.trust_score import get_trust_manager
from api.schemas_a2a_trust import A2ATrustGrantRequest
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter(dependencies=[Depends(check_admin_permission)])


@router.post("/trust/grant", summary="Grant trust to a (credential, peer id) pair", tags=["a2a"])
@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="grant_trust", error_code_prefix="A2A")
async def grant_trust(body: A2ATrustGrantRequest, current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Set a pair's trust level (#16950). Audited with the acting admin, the pair and the level.

    The re-key starts every pair at UNTRUSTED, which cannot submit tasks, so this is
    the only way back in. The level holds as a floor until a threat event or an
    integrity violation revokes it.
    """
    actor = credential_subject(current_user)
    record = get_trust_manager().grant(peer_trust_key(body.subject, body.peer_id), body.level, actor=actor)
    return record.to_dict()


@router.get("/trust-legacy", summary="List pre-#16950 header-only trust records", tags=["a2a"])
@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="list_legacy_trust", error_code_prefix="A2A")
async def list_legacy_trust() -> List[Dict[str, Any]]:
    """The header-only records kept from before the re-key: never read for access, only to guide re-grants."""
    return get_trust_manager().list_legacy_peers()




@router.get(
    "/trust",
    summary="List all peer trust records",
    tags=["a2a"],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_trust_records",
    error_code_prefix="A2A",
)
async def list_trust_records() -> List[Dict[str, Any]]:
    """
    Return trust records for all known federated peers.

    Issue #7358 phase 2: Provides operator visibility into federation health.
    Records are sourced from Redis and include the current score, level,
    and counters accumulated from live task outcomes.
    """
    records = get_trust_manager().list_peers()
    return [r.to_dict() for r in records]


@router.get(
    "/trust/{peer_id:path}",
    summary="Get trust record for a specific peer",
    tags=["a2a"],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_trust_record",
    error_code_prefix="A2A",
)
async def get_trust_record(peer_id: str) -> Dict[str, Any]:
    """
    Return the full trust record for a specific federated peer.

    Issue #7358 phase 2: If the peer has no prior interaction history,
    returns a default UNTRUSTED record (score 0.0, zero counters).
    """
    record = get_trust_manager().get_record(peer_id)
    return record.to_dict()


@router.get(
    "/trust/{peer_id:path}/audit",
    summary="Get trust level audit log for a peer",
    tags=["a2a"],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_trust_audit",
    error_code_prefix="A2A",
)
async def get_trust_audit(peer_id: str) -> Dict[str, Any]:
    """
    Return the level-change audit trail for a federated peer.

    Issue #7358 phase 2: Each entry records the old/new trust level, the
    score at the time of the change, and the reason (score_update,
    threat_event, integrity_violation).  Returns the 100 most recent entries.
    """
    audit = get_trust_manager().get_audit_log(peer_id)
    return {"peer_id": peer_id, "audit": audit}
