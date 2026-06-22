# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
OpenAI Realtime provider (Issue #9025) — first concrete RealtimeVoiceProvider.

Wraps the existing SDP-proxy upstream call (originally inline in
``api.realtime_session``, GH#7342) behind the provider abstraction. Behaviour is
byte-identical to the previous inline implementation: it forwards the browser's
SDP offer as multipart to OpenAI's Realtime API with the server-side
OPENAI_API_KEY injected and returns the SDP answer. The key never reaches the
browser.
"""

from __future__ import annotations

import os

import aiohttp

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import get_config
from voice_processing.realtime.base import (
    RealtimeCapabilities,
    RealtimeNegotiation,
    RealtimeProviderError,
    RealtimeTransport,
    RealtimeVoiceProvider,
)

logger = get_logger(__name__)

_OPENAI_REALTIME_URL = "https://api.openai.com/v1/realtime/sessions"
_OPENAI_BETA_HEADER = "realtime=v1"
_DEFAULT_MODEL = "gpt-realtime-2"


class OpenAIRealtimeProvider(RealtimeVoiceProvider):
    """OpenAI Realtime WebRTC provider (default realtime voice provider)."""

    provider_id = "openai"

    @property
    def provider_name(self) -> str:
        return "OpenAI Realtime"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key())

    @property
    def capabilities(self) -> RealtimeCapabilities:
        return RealtimeCapabilities(
            transport=RealtimeTransport.WEBRTC,
            supports_tools=True,
            supports_audio_output=True,
            supports_cost_tracking=True,
        )

    @staticmethod
    def _api_key() -> str:
        """Return the OpenAI API key from SSOT config with env-var fallback."""
        cfg = get_config()
        return cfg.llm.openai_api_key or os.environ.get("OPENAI_API_KEY", "")

    @staticmethod
    def _model() -> str:
        cfg = get_config()
        return cfg.misc.voice_realtime_model or _DEFAULT_MODEL

    async def negotiate(
        self,
        *,
        offer: str,
        session_config: str,
        session_id: str,
    ) -> RealtimeNegotiation:
        """Proxy the SDP offer to OpenAI Realtime and return the SDP answer."""
        api_key = self._api_key()
        if not api_key:
            logger.error("OPENAI_API_KEY not configured — cannot proxy SDP offer")
            raise RealtimeProviderError("Voice service not available: API key not configured", status=503)

        form = aiohttp.FormData()
        form.add_field("model", self._model())
        form.add_field("sdp", offer, content_type="text/plain")
        form.add_field("session", session_config, content_type="application/json")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": _OPENAI_BETA_HEADER,
        }

        body = await self._post(form, headers)
        return RealtimeNegotiation(answer=body, media_type="application/sdp")

    async def _post(self, form: aiohttp.FormData, headers: dict[str, str]) -> bytes:
        """POST the offer upstream and map upstream failures to provider errors."""
        timeout = aiohttp.ClientTimeout(connect=30, total=60)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as http:
                async with http.post(_OPENAI_REALTIME_URL, data=form, headers=headers) as upstream:
                    body = await upstream.read()
                    self._raise_for_status(upstream.status, body)
                    return body
        except RealtimeProviderError:
            raise
        except aiohttp.ClientError as exc:
            logger.error("Network error proxying SDP offer: %s", exc)
            raise RealtimeProviderError("Network error contacting voice service", status=502)

    @staticmethod
    def _raise_for_status(status: int, body: bytes) -> None:
        """Map upstream HTTP status to a RealtimeProviderError (502 on failure)."""
        if status == 401:
            logger.warning("OpenAI Realtime API returned 401 Unauthorized")
            raise RealtimeProviderError("Upstream authentication failed", status=502)
        if status >= 500:
            logger.error("OpenAI Realtime API returned %s: %s", status, body[:256])
            raise RealtimeProviderError(f"Upstream error: {status}", status=502)
        if status not in (200, 201):
            logger.warning("OpenAI Realtime API returned unexpected status %s", status)
            raise RealtimeProviderError(f"Unexpected upstream status: {status}", status=502)
