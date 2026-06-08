# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for orchestration/primitives/events.py (#5060)."""

from unittest.mock import AsyncMock, patch

import pytest

from events.bus import PersistStrategy
from orchestration.primitives.events import publish_event


@pytest.mark.asyncio
async def test_publish_event_delegates_to_bus():
    with patch("orchestration.primitives.events._bus_publish_event", new_callable=AsyncMock) as mock_bus:
        await publish_event("my-channel", "my-event", {"key": "val"})

    mock_bus.assert_awaited_once_with(
        "my-channel",
        "my-event",
        {"key": "val"},
        persist=PersistStrategy.MEMORY,
    )


@pytest.mark.asyncio
async def test_publish_event_respects_persist_strategy():
    with patch("orchestration.primitives.events._bus_publish_event", new_callable=AsyncMock) as mock_bus:
        await publish_event(
            "global",
            "settings_update",
            {"phi2_enabled": True},
            persist=PersistStrategy.NONE,
        )

    mock_bus.assert_awaited_once_with(
        "global",
        "settings_update",
        {"phi2_enabled": True},
        persist=PersistStrategy.NONE,
    )
