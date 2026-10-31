# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: preview and PROPOSE stripping legacy OAuth app credentials from user bundles (#13630).

Endpoints:
    GET  /api/admin/oauth-bundle-strip           dry run -- counts per provider, no values, writes nothing
    POST /api/admin/oauth-bundle-strip/requests  PROPOSE the strip -- creates a PENDING approval

Neither route rewrites a credential. The POST only creates an approval-gate
request (#17038): nothing runs until a human approves it in the Approvals inbox,
and it is never auto-approved. The executor lives in
``services.oauth_bundle_strip_action``.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_oauth_bundle_strip import (
    OAuthBundleStripPreviewResponse,
    OAuthBundleStripRequest,
    OAuthBundleStripRequestResponse,
)
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from auth_rbac import require_role
from models.approval import ApprovalType
from services import oauth_bundle_strip
from services.approval_gate_service import ApprovalGateService
from services.oauth_bundle_strip_action import ACTION as OAUTH_BUNDLE_STRIP
from services.oauth_bundle_strip_action import register_strip_action
from services.secrets_service import get_secrets_service

router = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin", "superadmin"))])

# Registered at this router's import time so the executor exists before any approve().
register_strip_action()


@router.get("/oauth-bundle-strip", response_model=OAuthBundleStripPreviewResponse)
async def preview_oauth_bundle_strip(current_user: dict = Depends(get_current_user)):
    """Dry run: how many bundles per provider would be stripped, skipped or are already clean."""
    report = await oauth_bundle_strip.preview(get_secrets_service(), current_user.get("username") or "admin")
    return OAuthBundleStripPreviewResponse(outcomes=report.summary(), bundle_ids=report.secret_ids)


@router.post(
    "/oauth-bundle-strip/requests",
    response_model=OAuthBundleStripRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def propose_oauth_bundle_strip(
    body: OAuthBundleStripRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OAuthBundleStripRequestResponse:
    """Propose the strip -- a request, not an execution. ``backup_reference`` is required."""
    approval = await ApprovalGateService(session).create_approval(
        title="Strip legacy OAuth app credentials from stored user bundles",
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description=body.reason or "Proposed from the OAuth bundle strip admin view (#13630).",
        requested_by_agent=current_user.get("username"),
        context={"action": OAUTH_BUNDLE_STRIP, "backup_reference": body.backup_reference},
    )
    return OAuthBundleStripRequestResponse(
        approval_id=str(approval.id), status=approval.status, action=OAUTH_BUNDLE_STRIP
    )
