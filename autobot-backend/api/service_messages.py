# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Cross-service message audit trail API (#1379).

Provides endpoints for querying the ServiceMessageBus — the Redis-backed
audit log of all inter-service messages exchanged across the fleet.

Endpoints:
- GET /api/service-messages/latest — recent messages (filterable)
- GET /api/service-messages/{msg_id} — single message by ID
- GET /api/service-messages/chain/{correlation_id} — full correlation chain
"""

import logging
from typing import List, Optional

from auth_middleware import auth_middleware
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from utils.catalog_http_exceptions import raise_auth_error, raise_server_error

from autobot_shared.message_bus import get_message_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/service-messages", tags=["service-messages"])


# ------------------------------------------------------------------
# Response models
# ------------------------------------------------------------------


class ServiceMessageResponse(BaseModel):
    """Single serialised ServiceMessage."""

    msg_id: str
    ts: str
    sender: str
    receiver: str
    msg_type: str
    content: str
    correlation_id: str
    meta: dict = Field(default_factory=dict)


class LatestMessagesResponse(BaseModel):
    """Response for GET /latest."""

    success: bool
    count: int
    messages: List[ServiceMessageResponse]


class SingleMessageResponse(BaseModel):
    """Response for GET /{msg_id}."""

    success: bool
    message: Optional[ServiceMessageResponse] = None


class CorrelationChainResponse(BaseModel):
    """Response for GET /chain/{correlation_id}."""

    success: bool
    correlation_id: str
    count: int
    messages: List[ServiceMessageResponse]


# ------------------------------------------------------------------
# Auth helper
# ------------------------------------------------------------------


def _check_admin(request: Request) -> bool:
    """Require admin role for service-message access."""
    try:
        user_data = auth_middleware.get_user_from_request(request)
        if not user_data:
            raise_auth_error(
                "AUTH_0002",
                "Authentication required for service message access",
            )
        user_role = user_data.get("role")
        if not user_role:
            raise_auth_error("AUTH_0002", "User role not assigned - access denied")
        if user_role != "admin":
            raise_auth_error(
                "AUTH_0003",
                "Admin permission required for service message access",
            )
        return True
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Permission check failed: %s", e)
        raise_server_error("API_0003", "Permission check error")


def _msg_to_response(msg) -> ServiceMessageResponse:
    """Convert a ServiceMessage to a response dict."""
    return ServiceMessageResponse(
        msg_id=msg.msg_id,
        ts=msg.ts,
        sender=msg.sender,
        receiver=msg.receiver,
        msg_type=msg.msg_type,
        content=msg.content,
        correlation_id=msg.correlation_id,
        meta=msg.meta,
    )


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/latest", response_model=LatestMessagesResponse)
async def get_latest_messages(
    request: Request,
    count: int = Query(50, ge=1, le=500, description="Number of messages"),
    sender: Optional[str] = Query(None, description="Filter by sender"),
    receiver: Optional[str] = Query(None, description="Filter by receiver"),
    msg_type: Optional[str] = Query(None, description="Filter by type"),
    _admin: bool = Depends(_check_admin),
):
    """Return the most recent cross-service messages.

    Supports optional filters by sender, receiver, and message type.
    """
    try:
        bus = get_message_bus()
        messages = await bus.get_latest(
            count=count,
            sender=sender,
            receiver=receiver,
            msg_type=msg_type,
        )
        return LatestMessagesResponse(
            success=True,
            count=len(messages),
            messages=[_msg_to_response(m) for m in messages],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch latest service messages: %s", e)
        raise_server_error("API_0003", f"Service message query error: {e}")


@router.get("/chain/{correlation_id}", response_model=CorrelationChainResponse)
async def get_correlation_chain(
    request: Request,
    correlation_id: str,
    _admin: bool = Depends(_check_admin),
):
    """Return all messages sharing a correlation ID, sorted by timestamp.

    Used for tracing full request chains across services.
    """
    try:
        bus = get_message_bus()
        messages = await bus.get_correlation_chain(correlation_id)
        return CorrelationChainResponse(
            success=True,
            correlation_id=correlation_id,
            count=len(messages),
            messages=[_msg_to_response(m) for m in messages],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to fetch correlation chain %s: %s",
            correlation_id,
            e,
        )
        raise_server_error("API_0003", f"Correlation chain query error: {e}")


@router.get("/{msg_id}", response_model=SingleMessageResponse)
async def get_message(
    request: Request,
    msg_id: str,
    _admin: bool = Depends(_check_admin),
):
    """Return a single service message by its ID."""
    try:
        bus = get_message_bus()
        msg = await bus.get_message(msg_id)
        if msg is None:
            return SingleMessageResponse(success=True, message=None)
        return SingleMessageResponse(
            success=True,
            message=_msg_to_response(msg),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch message %s: %s", msg_id, e)
        raise_server_error("API_0003", f"Service message fetch error: {e}")
