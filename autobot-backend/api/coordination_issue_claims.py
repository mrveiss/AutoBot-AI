# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue claims through AutoBot's API: the one door developer sessions use (#18811, parent #17098).

Delegates to ``autobot_shared.coordination.issue_claims`` -- no claim logic lives here.

**The holder is bound to the authenticated principal.** A claim is stored with
``agent_id = "<username>/<owner>"``: the username comes from the verified credential, the
``owner`` (session name) from the client. A caller therefore can only ever write, renew or
release a holder that starts with their own username, so another user's claim is neither
overwritten nor released from here -- the endpoint cannot be used to override a claim, which
is the reason ``/coordination/claims`` is read-only. A release aimed at any claim that is not the caller's own is
409 naming the holder, and leaves the claim in place.

**Install-wide, not tenant-scoped.** These are session coordination, so there is deliberately
no ``company_scope`` / ``X-Organization-Id`` dependency. The one gate is ``claims_principal``
(``coordination_issue_claims_credential``): the issue-claims client credential when presented,
else the canonical ``auth_middleware.get_current_user``. This router is mounted on its own
(``core_routers``), not under ``api.coordination``'s gated router, because that router's gate
would refuse the credential before this one could read it.

**Who may write.** The internal-key principal (``service: true``) shares one key and has no
human identity to bind a holder to, so it may read (who, list) but its writes are 403. With
auth disabled every caller is the synthetic ``admin``, so a write could claim or release under
any owner: writes are 403 then too.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.coordination_issue_claims_credential import claims_principal
from api.schemas_issue_claims import IssueClaimListResponse, IssueClaimRequest, IssueClaimResponse
from autobot_shared.coordination import issue_claims as ic
from autobot_shared.coordination.work_claims import HolderError, ScopeError
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Registered AFTER ``coordination_issue_claims_credential.router`` (core_routers), so
# ``/issue-claims/credentials`` is never read as an issue ``{number}``.
router = APIRouter(prefix="/issue-claims", tags=["issue-claims"], dependencies=[Depends(claims_principal)])

#: Separates the principal from the session name inside the stored ``agent_id``.
HOLDER_SEP = "/"


def holder_id(principal: str, owner: str) -> str:
    """The stored ``agent_id`` for *owner* acting as *principal*."""
    return f"{principal}{HOLDER_SEP}{owner.strip()}"


def _writer(user: dict = Depends(claims_principal)) -> str:
    """The principal a write is bound to; service, auth-disabled and unbindable names are refused."""
    name = str(user.get("username") or "")
    if user.get("service") or user.get("auth_disabled") or not name or HOLDER_SEP in name:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A claim needs an authenticated user identity")
    return name


def _check(number: int, owner: str | None = None, ttl_s: int | None = None) -> None:
    reason = ic.invalid_request_reason(number, owner, ttl_s)
    if owner is not None and HOLDER_SEP in owner:
        reason = reason or f"owner must not contain {HOLDER_SEP!r}"
    if reason:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, reason)


async def _run(call) -> tuple[int, dict[str, Any]]:
    """Run a registry call; an unreadable registry is 503 (fail closed), a bad identity 400."""
    try:
        return await call
    except (HolderError, ScopeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ic.UNREADABLE_ERRORS as exc:
        logger.error("issue claim registry unreadable (%s)", type(exc).__name__)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "registry-unreadable") from exc


@router.post("/{number}", response_model=IssueClaimResponse, response_model_exclude_none=True)
async def claim(number: int, req: IssueClaimRequest, who: str = Depends(_writer)) -> dict[str, Any]:
    """Claim or renew issue *number*; another holder is 409 naming them."""
    _check(number, req.owner, req.ttl_s)
    code, body = await _run(ic.claim_issue(number, holder_id(who, req.owner), req.note, req.ttl_s))
    if code == ic.EXIT_HELD:
        raise HTTPException(status.HTTP_409_CONFLICT, body)
    return body


@router.delete("/{number}", response_model=IssueClaimResponse, response_model_exclude_none=True)
async def release(number: int, owner: str = Query(...), who: str = Depends(_writer)) -> dict[str, Any]:
    """Release the caller's own claim; anyone else's is refused and stays held."""
    _check(number, owner)
    code, body = await _run(ic.release_issue(number, holder_id(who, owner)))
    if code == ic.EXIT_HELD:
        raise HTTPException(status.HTTP_409_CONFLICT, body)
    return body


@router.get("/{number}", response_model=IssueClaimResponse, response_model_exclude_none=True)
async def who_holds(number: int) -> dict[str, Any]:
    """Who holds issue *number*; ``held: false`` only after the registry was actually read."""
    _check(number)
    return (await _run(ic.who_issue(number)))[1]


@router.get("", response_model=IssueClaimListResponse)
async def list_all() -> dict[str, Any]:
    """Every live issue claim, install-wide."""
    return (await _run(ic.list_issue_claims()))[1]
