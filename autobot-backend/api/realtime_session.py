# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backend SDP proxy for OpenAI Realtime WebRTC (GH#7342).
Cost + duration telemetry wired in (GH#7421).

Accepts a WebRTC SDP offer from the browser, forwards it as multipart to
OpenAI's Realtime API with the OPENAI_API_KEY injected server-side, and
returns the SDP answer.  The key never reaches the browser.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import aiohttp
from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import get_config

logger = get_logger(__name__)
router = APIRouter()

_OPENAI_REALTIME_URL = "https://api.openai.com/v1/realtime/sessions"
_OPENAI_BETA_HEADER = "realtime=v1"


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


class SessionSummary(BaseModel):
    session_id: str
    user_id: str | None
    model: str
    started_at: str
    ended_at: str | None
    duration_s: float
    audio_in_s: float
    audio_out_s: float
    input_tokens: int
    output_tokens: int
    tool_calls: int
    estimated_cost_usd: float
    disconnect_reason: str


def _get_api_key() -> str:
    """Return the OpenAI API key from SSOT config with env-var fallback."""
    cfg = get_config()
    key = cfg.llm.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
    return key


def _get_model() -> str:
    cfg = get_config()
    return cfg.misc.voice_realtime_model or "gpt-realtime-2"


@router.post("/session")
async def create_realtime_session(  # noqa: PLR0912
    sdp: str = Form(..., media_type="text/plain"),
    session: str = Form(..., media_type="application/json"),
) -> Response:
    """
    SDP offer proxy for OpenAI Realtime WebRTC.

    Accepts multipart form fields:
      - sdp (text/plain): WebRTC SDP offer from the browser
      - session (application/json): session configuration JSON

    Returns the SDP answer from OpenAI with Content-Type: application/sdp.
    Maps upstream 401 → 502 and 5xx → 502; missing key → 503.
    """
    # Issue #7421: generate a session_id for telemetry tracking
    session_id = str(uuid.uuid4())

    api_key = _get_api_key()
    if not api_key:
        logger.error("OPENAI_API_KEY not configured — cannot proxy SDP offer")
        raise HTTPException(
            status_code=503,
            detail={"success": False, "message": "Voice service not available: API key not configured"},
        )

    model = _get_model()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": _OPENAI_BETA_HEADER,
    }

    form = aiohttp.FormData()
    form.add_field("model", model)
    form.add_field("sdp", sdp, content_type="text/plain")
    form.add_field("session", session, content_type="application/json")

    try:
        timeout = aiohttp.ClientTimeout(connect=30, total=60)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.post(_OPENAI_REALTIME_URL, data=form, headers=headers) as upstream:
                body = await upstream.read()

                if upstream.status == 401:
                    logger.warning("OpenAI Realtime API returned 401 Unauthorized")
                    raise HTTPException(
                        status_code=502,
                        detail={"success": False, "message": "Upstream authentication failed"},
                    )

                if upstream.status >= 500:
                    logger.error(
                        "OpenAI Realtime API returned %s: %s",
                        upstream.status,
                        body[:256],
                    )
                    raise HTTPException(
                        status_code=502,
                        detail={"success": False, "message": f"Upstream error: {upstream.status}"},
                    )

                if upstream.status != 201 and upstream.status != 200:
                    logger.warning(
                        "OpenAI Realtime API returned unexpected status %s",
                        upstream.status,
                    )
                    raise HTTPException(
                        status_code=502,
                        detail={"success": False, "message": f"Unexpected upstream status: {upstream.status}"},
                    )

                # Issue #7421: start telemetry for this session
                try:
                    from services.voice_realtime_telemetry import get_voice_realtime_telemetry

                    await get_voice_realtime_telemetry().session_start(session_id=session_id, model=_get_model())
                except Exception as exc:  # telemetry must never break the session
                    logger.warning("voice_realtime telemetry start failed: %s", exc)

                # Return SDP answer with session_id header so frontend can close telemetry
                return Response(
                    content=body,
                    media_type="application/sdp",
                    headers={"X-Realtime-Session-Id": session_id},
                )

    except HTTPException:
        raise
    except aiohttp.ClientError as exc:
        logger.error("Network error proxying SDP offer: %s", exc)
        raise HTTPException(
            status_code=502,
            detail={"success": False, "message": "Network error contacting voice service"},
        )
    except Exception as exc:
        logger.error("Unexpected error in SDP proxy: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "Internal error in voice service"},
        )


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
        return {"status": "cap_breach", "reason": exc.reason.value, "message": str(exc)}
    return {"status": "ok"}


@router.post("/tools/call")
async def call_realtime_tool(body: ToolCallRequest) -> dict:
    """Route a Realtime tool call through the MCP bridge (#7343 stub)."""
    from services.realtime_mcp_bridge import get_realtime_bridge

    bridge = await get_realtime_bridge()
    result = await bridge.call_tool(name=body.name, arguments=body.arguments, session_id=body.session_id)
    return {"call_id": body.call_id, "content": result.content, "is_error": result.is_error}


@router.get("/sessions", response_model=list[SessionSummary])
async def list_realtime_sessions(user_id: str | None = None, limit: int = 20) -> list[SessionSummary]:
    """Return recent Realtime sessions for the UsageView (#7421)."""
    from services.voice_realtime_telemetry import get_voice_realtime_telemetry

    telemetry = get_voice_realtime_telemetry()
    records = await telemetry.list_recent_sessions(user_id=user_id, limit=limit)
    return [
        SessionSummary(
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
