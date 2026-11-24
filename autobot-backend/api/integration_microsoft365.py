# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Microsoft 365 Integration API Endpoints (Issue #13710)

FastAPI router for the Outlook mail surface of ``Microsoft365Integration``:
connection test, list/search messages, list folders and send mail.

This is the COMPANY MAILBOX: one shared, service-owned credential (owner
``system``, connector id ``microsoft365``), connected once by an administrator
through the ``microsoft-mail`` OAuth provider. Every call is admin-only and
reads and sends as that mailbox. The credential is never taken from the
request: a fresh access token is obtained from ``ConnectorCredentialStore``
(which refreshes and rotates it) per call and is not persisted here. The
router does NOT feed the knowledge base (that is #13712).
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.schemas_microsoft365 import SendEmailRequest
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from integrations.base import IntegrationConfig, IntegrationHealth
from integrations.microsoft365_integration import Microsoft365Integration
from knowledge.connectors import oauth_flow
from knowledge.connectors.credential_store import get_credential_store
from services.credential_read import find_connector_secret_id
from services.gateway.egress_governor import egress_governor

logger = get_logger(__name__)

#: The company mailbox's credential: the service owner and fixed connector id declared by the
#: ``microsoft-mail`` OAuth provider, the one definition.
_MAILBOX_PROVIDER = oauth_flow.get_provider("microsoft-mail")
MAILBOX_OWNER_ID = _MAILBOX_PROVIDER.service_owner_id
MAILBOX_CONNECTOR_ID = _MAILBOX_PROVIDER.service_connector_id
_EGRESS_PLATFORM = "microsoft365"

router = APIRouter(
    tags=["integrations-microsoft365"],
    dependencies=[Depends(check_admin_permission)],
)


@router.post(
    "/test-connection",
    response_model=IntegrationHealth,
    summary="Test Microsoft 365 connection",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_connection",
    error_code_prefix="INTEGRATION_MICROSOFT365",
)
async def test_connection() -> IntegrationHealth:
    """Test the connection using the token held in the secrets store."""
    integration = await _create_integration()
    try:
        return await integration.test_connection()
    except Exception as exc:
        logger.exception("Failed to test Microsoft 365 connection")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


@router.get(
    "/messages",
    response_model=Dict[str, Any],
    summary="List Outlook messages",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_messages",
    error_code_prefix="INTEGRATION_MICROSOFT365",
)
async def list_messages(
    folder_id: str = "inbox",
    limit: int = Query(50, ge=1, le=1000),
) -> Dict[str, Any]:
    """List messages from the inbox or a specific folder."""
    return await _run_action("list_messages", {"folder_id": folder_id, "limit": limit})


@router.get(
    "/messages/search",
    response_model=Dict[str, Any],
    summary="Search Outlook messages",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_messages",
    error_code_prefix="INTEGRATION_MICROSOFT365",
)
async def search_messages(
    query: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=1000),
) -> Dict[str, Any]:
    """Search messages with a Graph ``$search`` query."""
    return await _run_action("search_messages", {"query": query, "limit": limit})


@router.get(
    "/folders",
    response_model=Dict[str, Any],
    summary="List Outlook mail folders",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_folders",
    error_code_prefix="INTEGRATION_MICROSOFT365",
)
async def list_folders() -> Dict[str, Any]:
    """List all mail folders."""
    return await _run_action("list_folders", {})


@router.post(
    "/messages",
    response_model=Dict[str, Any],
    summary="Send an Outlook message",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="send_email",
    error_code_prefix="INTEGRATION_MICROSOFT365",
)
async def send_email(message: SendEmailRequest) -> Dict[str, Any]:
    """Send a message, after the egress governance gate (#14270)."""
    verdict = await egress_governor.gate(
        platform=_EGRESS_PLATFORM, channel_id="outlook", subject="Microsoft 365 mail send"
    )
    if not verdict.allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Outbound send denied by egress policy")
    params = message.model_dump(exclude_none=True)
    return await _run_action("send_email", params)


async def _load_token() -> str:
    """A fresh access token for the company mailbox, refreshed by the credential store."""
    try:
        secret_id = await find_connector_secret_id(MAILBOX_CONNECTOR_ID)
        if secret_id is None:
            raise LookupError("mailbox not connected")
        return await get_credential_store().get_access_token(secret_id, MAILBOX_OWNER_ID)
    except (LookupError, PermissionError) as exc:
        logger.warning("Microsoft 365 mailbox credential unavailable: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Microsoft 365 mailbox is not connected",
        ) from exc
    except Exception as exc:
        logger.warning("Microsoft 365 token resolution failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


async def _create_integration() -> Microsoft365Integration:
    """Build the integration from the stored token (Issue #13710)."""
    config = IntegrationConfig(
        name="microsoft365_api",
        provider="microsoft365",
        token=await _load_token(),
    )
    return Microsoft365Integration(config)


async def _run_action(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute *action*, mapping the integration's error dict to HTTP errors."""
    integration = await _create_integration()
    try:
        result = await integration.execute_action(action, params)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request failed") from exc
    except Exception as exc:
        logger.exception("Microsoft 365 action %s failed", action)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc
    if "error" in result:
        logger.warning("Microsoft 365 action %s returned an error", action)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request failed")
    return result
