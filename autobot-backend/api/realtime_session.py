# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Backend SDP proxy for realtime voice (GH#7342, multi-provider via #9025).
Cost + duration telemetry wired in (GH#7421).

Accepts a WebRTC SDP offer (or websocket handshake blob) from the browser and
dispatches it to the *selected* realtime voice provider via the provider
registry (#9025). The default provider is OpenAI Realtime, so behaviour is
unchanged unless AUTOBOT_VOICE_REALTIME_PROVIDER (or a per-conversation
override) selects another provider. Upstream credentials never reach the
browser.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.schemas_realtime_session import RealtimeSessionSummary
from api.user_management.dependencies import get_current_user
from api.voice_bundle_helpers import voice_bundle_user_id
from auth_middleware import check_admin_permission
from autobot_shared.auth.permissions import Role, is_admin_role
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import get_config
from voice_processing.realtime.base import RealtimeProviderError
from voice_processing.realtime.registry import (
    get_active_provider_id,
    get_active_realtime_provider,
    list_realtime_providers,
    set_active_provider,
)

logger = get_logger(__name__)

# #16375: every route here spends something on the caller's behalf — an upstream
# realtime negotiation, a billed token budget, or an MCP tool invocation — so the
# router authenticates. The browser already sends credentials (useRealtimeVoice.ts
# calls fetchWithAuth), so this gate adds no client change.
router = APIRouter(dependencies=[Depends(get_current_user)])


# ── Telemetry endpoint models (Issue #7421) ───────────────────────────────────


class SessionEndRequest(BaseModel):
    reason: str = "normal"


class ResponseDoneRequest(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    audio_in_s: float = 0.0
    audio_out_s: float = 0.0


class ToolCallRequest(BaseModel):
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


# ── Provider selection models (Issue #9025) ───────────────────────────────────


class RealtimeProviderInfo(BaseModel):
    id: str
    name: str
    configured: bool
    transport: str
    supports_tools: bool
    supports_audio_output: bool
    supports_cost_tracking: bool


class RealtimeProvidersResponse(BaseModel):
    selected: str
    providers: list[RealtimeProviderInfo]


class SetRealtimeProviderRequest(BaseModel):
    provider: Optional[str] = None


def _get_model() -> str:
    cfg = get_config()
    return cfg.misc.voice_realtime_model or "gpt-realtime-2"


@router.post("/session")
async def create_realtime_session(
    sdp: str = Form(..., media_type="text/plain"),
    session: str = Form(..., media_type="application/json"),
) -> Response:
    """
    SDP offer proxy for realtime voice, dispatched to the selected provider.

    Accepts multipart form fields:
      - sdp (text/plain): WebRTC SDP offer from the browser
      - session (application/json): session configuration JSON

    Returns the provider's negotiation answer. For WebRTC providers this is the
    SDP answer with Content-Type: application/sdp. Provider errors map to 503
    (not configured) or 502 (upstream failure).
    """
    session_id = str(uuid.uuid4())
    provider = get_active_realtime_provider()

    try:
        negotiation = await provider.negotiate(
            offer=sdp,
            session_config=session,
            session_id=session_id,
        )
    except RealtimeProviderError as exc:
        logger.warning("Realtime provider %r negotiation failed: %s", provider.provider_id, exc)
        raise HTTPException(
            status_code=exc.status,
            detail={"success": False, "message": str(exc)},
        )
    except Exception as exc:
        logger.error("Unexpected error negotiating realtime session: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "Internal error in voice service"},
        )

    # Issue #7421: start telemetry for this session (must never break the session)
    try:
        from services.voice_realtime_telemetry import get_voice_realtime_telemetry

        await get_voice_realtime_telemetry().session_start(session_id=session_id, model=_get_model())
    except Exception as exc:
        logger.warning("voice_realtime telemetry start failed: %s", exc)

    headers = {"X-Realtime-Session-Id": session_id, "X-Realtime-Provider": provider.provider_id}
    headers.update(negotiation.headers)
    return Response(content=negotiation.answer, media_type=negotiation.media_type, headers=headers)


# ── Provider selection endpoints (Issue #9025) ────────────────────────────────


@router.get("/providers", response_model=RealtimeProvidersResponse)
async def list_providers() -> dict:
    """List realtime voice providers + the active selection (never returns keys)."""
    return {"selected": get_active_provider_id(), "providers": list_realtime_providers()}


# Admin, not just authenticated: set_active_provider mutates the in-process
# selection for every session, not the caller's own.
@router.patch(
    "/providers",
    response_model=RealtimeProvidersResponse,
    dependencies=[Depends(check_admin_permission)],
)
async def set_provider(body: SetRealtimeProviderRequest) -> dict:
    """Set the active realtime provider (in-process; doc'd restart limitation).

    Pass {"provider": null} to clear the override and fall back to the
    AUTOBOT_VOICE_REALTIME_PROVIDER config / default.
    """
    try:
        set_active_provider(body.provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"selected": get_active_provider_id(), "providers": list_realtime_providers()}


# ── Telemetry endpoints (Issue #7421) ─────────────────────────────────────────


@router.post("/session/{session_id}/end")
async def end_realtime_session(session_id: str, body: SessionEndRequest) -> dict:
    """Finalise telemetry for a Realtime session."""
    from services.voice_realtime_telemetry import DisconnectReason, get_voice_realtime_telemetry

    try:
        reason = DisconnectReason(body.reason)
    except ValueError:
        reason = DisconnectReason.NORMAL
    await get_voice_realtime_telemetry().session_end(session_id=session_id, reason=reason)
    return {"status": "ok", "session_id": session_id}


@router.post("/session/{session_id}/response_done")
async def ingest_response_done(session_id: str, body: ResponseDoneRequest) -> dict:
    """Ingest a response.done payload and enforce soft-caps."""
    from services.voice_realtime_telemetry import CapBreachError, get_voice_realtime_telemetry

    telemetry = get_voice_realtime_telemetry()
    await telemetry.record_response_done(
        session_id=session_id,
        input_tokens=body.input_tokens,
        output_tokens=body.output_tokens,
        cached_input_tokens=body.cached_input_tokens,
        audio_in_s=body.audio_in_s,
        audio_out_s=body.audio_out_s,
    )
    try:
        await telemetry.check_caps(session_id)
    except CapBreachError as exc:
        await telemetry.session_end(session_id=session_id, reason=exc.reason)
        # CapBreachError carries an intentional, hardcoded
        # client-facing cap-breach notice (e.g. "session ended: N minute limit reached"), not a stack trace.
        return {"status": "cap_breach", "reason": exc.reason.value, "message": str(exc)}
    return {"status": "ok"}


@router.post("/tools/call")
async def call_realtime_tool(
    body: ToolCallRequest, request: Request, current_user: dict = Depends(get_current_user)
) -> dict:
    """The one handler for ``POST /api/voice/realtime/tools/call`` (#7343, #18721).

    Only a tool in the caller's active voice bundle may run (403 otherwise), and the call carries the
    authenticated session, user and company, never the model's (#18430). ``X-Session-Id`` stands in when the
    body names no session.
    """
    from services.realtime_mcp_bridge import get_realtime_bridge

    role = current_user.get("role") or Role.USER.value
    user_id = voice_bundle_user_id(current_user)  # the same key the listing endpoint resolves the bundle by
    bridge = await get_realtime_bridge(is_admin=is_admin_role(role))  # #12717
    allowed = {t.name for t in await bridge.list_realtime_tools(user_id=user_id, role=role)}
    if body.name not in allowed:
        raise HTTPException(status_code=403, detail="Tool not permitted in active voice bundle")
    result = await bridge.call_tool(
        name=body.name,
        arguments=body.arguments,
        session_id=body.session_id or request.headers.get("X-Session-Id"),
        user_id=user_id,
        company_id=current_user.get("org_id"),
    )
    return {"call_id": body.call_id, "content": result.content, "is_error": result.is_error}


@router.get("/sessions", response_model=list[RealtimeSessionSummary])
async def list_realtime_sessions(user_id: str | None = None, limit: int = 20) -> list[RealtimeSessionSummary]:
    """Return recent Realtime sessions for the UsageView (#7421)."""
    from services.voice_realtime_telemetry import get_voice_realtime_telemetry

    telemetry = get_voice_realtime_telemetry()
    records = await telemetry.list_recent_sessions(user_id=user_id, limit=limit)
    return [
        RealtimeSessionSummary(
            session_id=r.session_id,
            user_id=r.user_id,
            model=r.model,
            started_at=r.started_at,
            ended_at=r.ended_at,
            duration_s=r.duration_s,
            audio_in_s=r.audio_in_s,
            audio_out_s=r.audio_out_s,
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            tool_calls=r.tool_calls,
            estimated_cost_usd=r.estimated_cost_usd,
            disconnect_reason=r.disconnect_reason,
        )
        for r in records
    ]
