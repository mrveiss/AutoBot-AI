# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request and response models for the issue-claims endpoints (#18811).

A companion ``schemas_<domain>.py``: the no-local-schemas hook (#6056) rejects a router
that defines its own ``BaseModel``. The bounds mirror ``issue_claims`` (``TTL_MIN_S`` /
``TTL_MAX_S``) so a request the registry would refuse is refused as 422 at the edge too.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from autobot_shared.coordination.issue_claims import TTL_MAX_S, TTL_MIN_S


class IssueClaimRequest(BaseModel):
    """Body of ``POST /coordination/issue-claims/{number}``."""

    owner: str = Field(..., min_length=1, max_length=128, description="Session name; bound to the caller")
    note: str = Field("", max_length=512)
    ttl_s: Optional[int] = Field(None, ge=TTL_MIN_S, le=TTL_MAX_S)


class IssueClaimResponse(BaseModel):
    """One answer shape for claim, release and who; the CLI prints it as JSON."""

    held: bool
    granted: Optional[bool] = None
    released: Optional[bool] = None
    holder: Optional[dict[str, Any]] = None
    message: Optional[str] = None


class IssueClaimListResponse(BaseModel):
    """Body of ``GET /coordination/issue-claims``."""

    claims: list[dict[str, Any]]


class ClaimsCredentialResponse(BaseModel):
    """Body of ``POST /coordination/issue-claims/credentials``: the credential, returned this once."""

    credential: str = Field(..., description="<secret_id>.<verifier>; keep it in the kernel keyring, never on disk")
    secret_id: str
    username: str


class ClaimsCredentialRevokedResponse(BaseModel):
    """Body of ``DELETE /coordination/issue-claims/credentials``."""

    revoked: bool
    secret_id: str
