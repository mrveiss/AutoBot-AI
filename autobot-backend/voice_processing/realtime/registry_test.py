# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the multi-provider realtime voice registry + selection (#9025).

Scenarios:
  - registry resolves the default provider (openai) with no config
  - config / override selects a provider
  - unknown override raises; unknown config falls back to default
  - a selected-but-unconfigured non-default provider falls back to default
  - the OpenAI provider's negotiate() proxies the SDP offer (provider I/O mocked)
  - an unconfigured provider's negotiate() raises 503
  - seam providers report configured state honestly and refuse cleanly (503)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice_processing.realtime import registry
from voice_processing.realtime.base import RealtimeProviderError, RealtimeTransport
from voice_processing.realtime.openai_provider import OpenAIRealtimeProvider
from voice_processing.realtime.seam import GeminiLiveProvider


@pytest.fixture(autouse=True)
def _clear_override():
    """Each test starts with no in-process override."""
    registry.set_active_provider(None)
    yield
    registry.set_active_provider(None)


# ── selection / registry resolution ───────────────────────────────────────────


def test_default_provider_is_openai():
    assert registry.get_active_provider_id() == "openai"
    provider = registry.get_active_realtime_provider()
    assert isinstance(provider, OpenAIRealtimeProvider)
    assert provider.provider_id == "openai"


def test_override_selects_provider():
    registry.set_active_provider("gemini")
    assert registry.get_active_provider_id() == "gemini"


def test_unknown_override_raises():
    with pytest.raises(ValueError):
        registry.set_active_provider("does-not-exist")


def test_unknown_config_falls_back_to_default():
    cfg = MagicMock()
    cfg.misc.voice_realtime_provider = "nonsense"
    with patch.object(registry, "get_config", return_value=cfg):
        provider = registry.get_active_realtime_provider()
    assert isinstance(provider, OpenAIRealtimeProvider)


def test_selected_unconfigured_non_default_falls_back_to_default():
    # gemini selected but no GEMINI_API_KEY → fall back to openai
    registry.set_active_provider("gemini")
    with patch.object(GeminiLiveProvider, "is_configured", new=False):
        provider = registry.get_active_realtime_provider()
    assert isinstance(provider, OpenAIRealtimeProvider)


def test_list_realtime_providers_metadata_no_secrets():
    providers = registry.list_realtime_providers()
    ids = {p["id"] for p in providers}
    assert {"openai", "gemini", "elevenlabs", "ultravox"} <= ids
    for p in providers:
        assert set(p) == {
            "id",
            "name",
            "configured",
            "transport",
            "supports_tools",
            "supports_audio_output",
            "supports_cost_tracking",
        }


# ── OpenAI provider dispatch (provider I/O mocked) ─────────────────────────────


def _mock_aiohttp_session(status: int, body: bytes):
    resp = MagicMock()
    resp.status = status
    resp.read = AsyncMock(return_value=body)
    post_cm = MagicMock()
    post_cm.__aenter__ = AsyncMock(return_value=resp)
    post_cm.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post = MagicMock(return_value=post_cm)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return session_cm


@pytest.mark.asyncio
async def test_openai_negotiate_proxies_offer():
    provider = OpenAIRealtimeProvider()
    answer = b"v=0\r\nsdp-answer\r\n"
    with (
        patch.object(OpenAIRealtimeProvider, "_api_key", return_value="sk-test"),
        patch("aiohttp.ClientSession", return_value=_mock_aiohttp_session(200, answer)),
    ):
        result = await provider.negotiate(offer="v=0", session_config="{}", session_id="sid")
    assert result.answer == answer
    assert result.media_type == "application/sdp"
    assert provider.capabilities.transport is RealtimeTransport.WEBRTC


@pytest.mark.asyncio
async def test_openai_negotiate_unconfigured_raises_503():
    provider = OpenAIRealtimeProvider()
    with patch.object(OpenAIRealtimeProvider, "_api_key", return_value=""):
        with pytest.raises(RealtimeProviderError) as exc:
            await provider.negotiate(offer="v=0", session_config="{}", session_id="sid")
    assert exc.value.status == 503


@pytest.mark.asyncio
async def test_openai_negotiate_upstream_500_maps_502():
    provider = OpenAIRealtimeProvider()
    with (
        patch.object(OpenAIRealtimeProvider, "_api_key", return_value="sk-test"),
        patch("aiohttp.ClientSession", return_value=_mock_aiohttp_session(500, b"boom")),
    ):
        with pytest.raises(RealtimeProviderError) as exc:
            await provider.negotiate(offer="v=0", session_config="{}", session_id="sid")
    assert exc.value.status == 502


# ── seam providers refuse cleanly ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_seam_provider_refuses_with_503():
    provider = GeminiLiveProvider()
    with pytest.raises(RealtimeProviderError) as exc:
        await provider.negotiate(offer="x", session_config="{}", session_id="sid")
    assert exc.value.status == 503


def test_seam_provider_configured_reflects_env():
    provider = GeminiLiveProvider()
    with patch.dict("os.environ", {"GEMINI_API_KEY": "k"}, clear=False):
        assert provider.is_configured is True
    with patch.dict("os.environ", {}, clear=True):
        assert GeminiLiveProvider().is_configured is False
