# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: clear-text credentials left in stored connector records (#20701).

Endpoints (mounted under the connectors router, admin only):
    GET  /knowledge_base/connector_credentials/scan              read-only counts, never values
    POST /knowledge_base/connector_credentials/cleanup-requests  PROPOSE removing one record's copies

The POST creates a PENDING approval and returns; it rewrites nothing. The rewrite runs only from the
post-approval handler after an admin approves. Rotating a credential that sat in clear text is a human
decision and is not automated: the proposal names the connector so the reviewer can rotate it.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_connector_credentials import (
    ConnectorCredentialCleanupRequest,
    ConnectorCredentialCleanupResponse,
    ConnectorCredentialFindingResponse,
    ConnectorCredentialScanResponse,
)
from api.user_management.dependencies import get_db_session
from auth_middleware import check_admin_permission, get_current_user
from models.approval import Approval
from services.approval_gate_service import ApprovalGateService
from services.connector_credential_cleanup_action import ACTION as CONNECTOR_CREDENTIAL_STRIP
from services.connector_credential_cleanup_action import register_connector_credential_strip
from services.connector_credential_scan import CredentialFinding, CredentialScanReport, scan_connector_credentials
from services.kb_cleanup_proposals import cleanup_proposal, find_pending_proposal, record_cleanup_proposed

router = APIRouter(prefix="/knowledge_base/connector_credentials", dependencies=[Depends(check_admin_permission)])

# Registered at this router's import time so the handler exists before any approve() can reach it.
register_connector_credential_strip()


def _scan_response(report: CredentialScanReport) -> ConnectorCredentialScanResponse:
    return ConnectorCredentialScanResponse(
        scanned=report.scanned,
        affected=len(report.findings),
        with_store_copy_count=report.with_secret_copy,
        without_store_copy_count=report.without_secret_copy,
        findings=[
            ConnectorCredentialFindingResponse(
                connector_id=f.connector_id,
                connector_type=f.connector_type,
                fields=list(f.fields),
                has_secrets_store_copy=f.secret_backed,
            )
            for f in report.findings
        ],
        unscannable_ids=report.unscannable_ids,
    )


async def _removable_finding(connector_id: str) -> CredentialFinding:
    """The scan finding for *connector_id* that has a secrets-store copy; 409 when none can be proposed."""
    report = await scan_connector_credentials()
    finding = next((f for f in report.findings if f.connector_id == connector_id and f.secret_backed), None)
    if finding is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No removable clear-text credential copy on that connector")
    return finding


async def _create_proposal(service: ApprovalGateService, current_user: dict, finding: CredentialFinding) -> Approval:
    """Audit-log, then create, the pending proposal (the audit row names the approval it precedes)."""
    approval_id = uuid.uuid4()
    await record_cleanup_proposed(
        approval_id,
        current_user,
        operation="connector_credentials.strip_proposed",
        resource=f"connector:{finding.connector_id}",
    )
    return await service.create_approval(
        **cleanup_proposal(
            current_user,
            title=f"Remove stored credential copies: {finding.connector_type}/{finding.connector_id}",
            description=(
                f"The {finding.connector_type} connector record holds {', '.join(finding.fields)} in clear text "
                "alongside the secrets-store copy. Approving removes only the record's copy. The exposed "
                "credential is not rotated automatically: rotate it at the provider for this connector."
            ),
            context={"action": CONNECTOR_CREDENTIAL_STRIP, "connector_id": finding.connector_id},
            approval_id=approval_id,
        )
    )


@router.get("/scan", response_model=ConnectorCredentialScanResponse)
async def scan_stored_connector_credentials() -> ConnectorCredentialScanResponse:
    """Count connector records holding a value for a sensitive field of their auth schema (no values returned)."""
    return _scan_response(await scan_connector_credentials())


@router.post(
    "/cleanup-requests",
    response_model=ConnectorCredentialCleanupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def propose_connector_credential_cleanup(
    body: ConnectorCredentialCleanupRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ConnectorCredentialCleanupResponse:
    """Propose removing the clear-text copies from one connector record -- a request, not a rewrite.

    Only a record that holds a copy AND has a secrets-store copy can be proposed: removing the only copy
    would lose the credential. The handler re-checks both when the proposal is approved.
    """
    finding = await _removable_finding(body.connector_id)
    service = ApprovalGateService(session)
    approval = await find_pending_proposal(service, CONNECTOR_CREDENTIAL_STRIP, "connector_id", finding.connector_id)
    if approval is None:
        approval = await _create_proposal(service, current_user, finding)
    return ConnectorCredentialCleanupResponse(
        approval_id=str(approval.id),
        status=approval.status,
        action=CONNECTOR_CREDENTIAL_STRIP,
        connector_id=finding.connector_id,
    )
