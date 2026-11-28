# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``events.bus.publish_event`` is the one definition serving every former caller (#18459).

``orchestration.primitives`` used to carry a second ``publish_event`` that only
forwarded to the bus with an identical signature. The primitives package and
the orchestrator now bind the bus function itself.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import orchestration.primitives as primitives
import orchestrator
from events import bus
from events.bus import PersistStrategy


def test_every_former_caller_binds_the_bus_definition():
    assert primitives.publish_event is bus.publish_event
    assert primitives.PersistStrategy is bus.PersistStrategy
    assert orchestrator._publish_event is bus.publish_event


@pytest.mark.asyncio
async def test_primitives_publish_event_reaches_the_bus_with_default_persist():
    fake_bus = MagicMock()
    fake_bus.publish = AsyncMock()
    with patch.object(bus, "get_event_bus", return_value=fake_bus):
        await primitives.publish_event("my-channel", "my-event", {"key": "val"})

    fake_bus.publish.assert_awaited_once_with("my-channel", "my-event", {"key": "val"}, persist=PersistStrategy.MEMORY)


@pytest.mark.asyncio
async def test_primitives_publish_event_respects_persist_strategy():
    fake_bus = MagicMock()
    fake_bus.publish = AsyncMock()
    with patch.object(bus, "get_event_bus", return_value=fake_bus):
        await primitives.publish_event("global", "settings_update", {"a": True}, persist=PersistStrategy.NONE)

    fake_bus.publish.assert_awaited_once_with("global", "settings_update", {"a": True}, persist=PersistStrategy.NONE)
