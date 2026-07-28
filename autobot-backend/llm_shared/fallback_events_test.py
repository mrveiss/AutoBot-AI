# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the canonical PROVIDER_FALLBACK event helper (#11995)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from events.event_types import PROVIDER_FALLBACK
from llm_shared.fallback_events import emit_fallback_event


@pytest.mark.asyncio
async def test_emit_fallback_event_publishes_canonical_payload():
    """Publishes PROVIDER_FALLBACK on the "global" channel with full payload."""
    with patch("llm_shared.fallback_events.publish_event", new=AsyncMock()) as mock_publish:
        await emit_fallback_event(
            conversation_id="conv-1",
            primary_model="claude-opus-4",
            fallback_model="claude-sonnet-4",
            primary_provider="anthropic",
            fallback_provider="anthropic",
            reason="rate_limit_429",
            chain_tried=["claude-opus-4", "claude-sonnet-4"],
            degraded_skipped=["claude-haiku-4"],
            request_id="req-1",
        )

    mock_publish.assert_awaited_once()
    channel, event_type, payload = mock_publish.await_args.args
    assert channel == "global"
    assert event_type == PROVIDER_FALLBACK
    assert payload["conversation_id"] == "conv-1"
    assert payload["request_id"] == "req-1"
    assert payload["primary_model"] == "claude-opus-4"
    assert payload["fallback_model"] == "claude-sonnet-4"
    assert payload["reason"] == "rate_limit_429"
    assert payload["chain_tried"] == ["claude-opus-4", "claude-sonnet-4"]
    assert payload["degraded_skipped"] == ["claude-haiku-4"]
    assert payload["exhausted"] is False
    assert isinstance(payload["timestamp"], float)


@pytest.mark.asyncio
async def test_emit_fallback_event_defaults_conversation_id_to_system():
    """No conversation_id → "system", matching the existing Redis write convention."""
    with patch("llm_shared.fallback_events.publish_event", new=AsyncMock()) as mock_publish:
        await emit_fallback_event(
            conversation_id=None,
            primary_model="claude-opus-4",
            fallback_model=None,
            exhausted=True,
        )

    payload = mock_publish.await_args.args[2]
    assert payload["conversation_id"] == "system"
    assert payload["exhausted"] is True
    assert payload["chain_tried"] == []
    assert payload["degraded_skipped"] == []


@pytest.mark.asyncio
async def test_emit_fallback_event_publish_failure_is_non_fatal():
    """A broken event bus must never break the fallback request it describes."""
    with patch(
        "llm_shared.fallback_events.publish_event",
        new=AsyncMock(side_effect=RuntimeError("bus down")),
    ):
        await emit_fallback_event(
            conversation_id="conv-1",
            primary_model="claude-opus-4",
            fallback_model="claude-sonnet-4",
        )  # must not raise
