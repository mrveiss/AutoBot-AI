# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backend SDP proxy for OpenAI Realtime WebRTC (GH#7342).

Accepts a WebRTC SDP offer from the browser, forwards it as multipart to
OpenAI's Realtime API with the OPENAI_API_KEY injected server-side, and
returns the SDP answer.  The key never reaches the browser.
"""

from __future__ import annotations

import os

import aiohttp
from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import Response

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import get_config

logger = get_logger(__name__)
router = APIRouter()

_OPENAI_REALTIME_URL = "https://api.openai.com/v1/realtime/calls"
_OPENAI_BETA_HEADER = "realtime=v1"


def _get_api_key() -> str:
    """Return the OpenAI API key from SSOT config with env-var fallback."""
    cfg = get_config()
    key = cfg.llm.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
    return key


def _get_model() -> str:
    cfg = get_config()
    return cfg.misc.voice_realtime_model or "gpt-realtime-2"


@router.post("/session")
async def create_realtime_session(
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
        async with aiohttp.ClientSession() as http:
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

                return Response(content=body, media_type="application/sdp")

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
