# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for TemporalSearchService with mocked Redis.

Issue #1075: Test coverage for temporal search and causal chain traversal.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from autobot_shared.logging_manager import get_logger
from knowledge.temporal_search import TemporalSearchService

logger = get_logger(__name__)


# --- Fixtures ---


@pytest.fixture
def mock_redis():
    """Create a mock async Redis client.

    ``TemporalSearchService`` awaits every command, so the command methods
    must be ``AsyncMock``.  A plain ``MagicMock`` returns a non-awaitable,
    ``await`` raises ``TypeError``, and the service's ``except Exception``
    handlers turn that into an empty result — every assertion then compared
    against zero regardless of the fixture data (#13270).

    ``redis.json()`` itself is *synchronous* on ``redis.asyncio.Redis`` (it
    returns the JSON command group), so it stays a ``MagicMock``; only the
    commands it exposes are awaitable.
    """
    redis = MagicMock()
    redis.get = AsyncMock()
    redis.smembers = AsyncMock()
    redis.zrangebyscore = AsyncMock()

    json_commands = MagicMock()
    json_commands.get = AsyncMock()
    redis.json.return_value = json_commands
    return redis


@pytest.fixture
def service(mock_redis):
    return TemporalSearchService(mock_redis)


@pytest.fixture
def sample_event():
    return {
        "id": str(uuid4()),
        "name": "Product Launch",
        "event_type": "milestone",
        "timestamp": "2024-06-01T00:00:00",
        "participants": [str(uuid4())],
    }


# --- Search Events in Range ---


class TestSearchEventsInRange:
    """Tests for search_events_in_range."""

    @pytest.mark.asyncio
    async def test_finds_events(self, service, mock_redis, sample_event):
        event_id = "event-1"
        mock_redis.zrangebyscore.return_value = [event_id]
        mock_redis.json().get.return_value = sample_event

        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        events = await service.search_events_in_range(start, end)

        assert len(events) == 1
        assert events[0]["name"] == "Product Launch"

    @pytest.mark.asyncio
    async def test_filters_by_event_type(self, service, mock_redis, sample_event):
        mock_redis.zrangebyscore.return_value = ["e1"]
        mock_redis.json().get.return_value = sample_event

        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        events = await service.search_events_in_range(start, end, event_types=["action"])
        assert len(events) == 0
        # The event was fetched and then filtered out — not a failed query.
        mock_redis.json().get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_filters_by_participant(self, service, mock_redis, sample_event):
        participant_id = uuid4()
        sample_event["participants"] = [str(participant_id)]
        mock_redis.zrangebyscore.return_value = ["e1"]
        mock_redis.json().get.return_value = sample_event

        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        events = await service.search_events_in_range(start, end, participants=[participant_id])
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_no_matching_participants(self, service, mock_redis, sample_event):
        mock_redis.zrangebyscore.return_value = ["e1"]
        mock_redis.json().get.return_value = sample_event

        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        events = await service.search_events_in_range(start, end, participants=[uuid4()])
        assert len(events) == 0
        # The event was fetched and then filtered out — not a failed query.
        mock_redis.json().get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_range(self, service, mock_redis):
        mock_redis.zrangebyscore.return_value = []
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 2)
        events = await service.search_events_in_range(start, end)
        assert events == []
        # Empty range means nothing was fetched at all.
        mock_redis.json().get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_missing_events(self, service, mock_redis):
        mock_redis.zrangebyscore.return_value = ["e1", "e2"]
        mock_redis.json().get.side_effect = [
            None,
            {"name": "Found", "event_type": "action"},
        ]

        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        events = await service.search_events_in_range(start, end)
        assert len(events) == 1


# --- Event Timeline ---


class TestGetEventTimeline:
    """Tests for get_event_timeline."""

    @pytest.mark.asyncio
    async def test_returns_sorted_events(self, service, mock_redis):
        entity_id = str(uuid4())
        mock_redis.get.return_value = entity_id.encode()
        mock_redis.smembers.return_value = ["e1", "e2"]

        event1 = {
            "name": "First",
            "timestamp": "2024-01-01T00:00:00",
        }
        event2 = {
            "name": "Second",
            "timestamp": "2024-06-01T00:00:00",
        }
        mock_redis.json().get.side_effect = [event1, event2]

        events = await service.get_event_timeline("test_entity")
        assert len(events) == 2
        assert events[0]["name"] == "First"

    @pytest.mark.asyncio
    async def test_returns_events_with_decoded_responses_client(self, service, mock_redis):
        """End-to-end guard for #13270.

        The shared client decodes responses, so the entity-id lookup returns
        ``str``.  ``.decode()`` on that raised AttributeError, which
        get_event_timeline's ``except Exception`` turned into an empty
        timeline for *every* entity — a user-visible defect on
        ``GET /events/{entity_name}/timeline``.
        """
        mock_redis.get.return_value = str(uuid4())
        mock_redis.smembers.return_value = ["e1"]
        mock_redis.json().get.return_value = {
            "name": "Only",
            "timestamp": "2024-03-01T00:00:00",
        }

        events = await service.get_event_timeline("test_entity")
        assert len(events) == 1
        assert events[0]["name"] == "Only"

    @pytest.mark.asyncio
    async def test_entity_not_found(self, service, mock_redis):
        mock_redis.get.return_value = None
        events = await service.get_event_timeline("unknown")
        assert events == []
        mock_redis.smembers.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_respects_limit(self, service, mock_redis):
        entity_id = str(uuid4())
        mock_redis.get.return_value = entity_id.encode()
        mock_redis.smembers.return_value = ["e1", "e2", "e3"]

        events = [{"name": f"E{i}", "timestamp": f"2024-0{i+1}-01T00:00:00"} for i in range(3)]
        mock_redis.json().get.side_effect = events

        result = await service.get_event_timeline("entity", limit=2)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_skips_events_without_timestamp(self, service, mock_redis):
        entity_id = str(uuid4())
        mock_redis.get.return_value = entity_id.encode()
        mock_redis.smembers.return_value = ["e1"]
        mock_redis.json().get.return_value = {"name": "NoTime"}

        events = await service.get_event_timeline("entity")
        assert len(events) == 0
        # The event was fetched and dropped for lacking a timestamp.
        mock_redis.json().get.assert_awaited_once()


# --- Causal Chain Traversal ---


class TestFindCausalChain:
    """Tests for find_causal_chain (recursive traversal)."""

    @pytest.mark.asyncio
    async def test_forward_chain(self, service, mock_redis):
        event1 = {"id": "e1", "name": "Cause"}
        event2 = {"id": "e2", "name": "Effect"}

        mock_redis.json().get.side_effect = [event1, event2]
        mock_redis.smembers.side_effect = [{"e2"}, set()]

        chain = await service.find_causal_chain(uuid4(), direction="forward")
        assert len(chain) == 2
        assert chain[0]["name"] == "Cause"
        assert chain[1]["name"] == "Effect"

    @pytest.mark.asyncio
    async def test_backward_chain(self, service, mock_redis):
        event1 = {"id": "e1", "name": "Effect"}
        event2 = {"id": "e2", "name": "Root Cause"}

        mock_redis.json().get.side_effect = [event1, event2]
        mock_redis.smembers.side_effect = [{"e2"}, set()]

        chain = await service.find_causal_chain(uuid4(), direction="backward")
        assert len(chain) == 2

    @pytest.mark.asyncio
    async def test_respects_max_depth(self, service, mock_redis):
        def make_event(eid):
            return {"id": eid, "name": f"Event {eid}"}

        mock_redis.json().get.side_effect = [make_event(f"e{i}") for i in range(10)]
        mock_redis.smembers.side_effect = [{f"e{i+1}"} for i in range(10)]

        chain = await service.find_causal_chain(uuid4(), direction="forward", max_depth=3)
        # Exactly max_depth levels are visited before the recursion stops.
        assert len(chain) == 3

    @pytest.mark.asyncio
    async def test_handles_cycles(self, service, mock_redis):
        """Cycle detection via visited set prevents infinite recursion.

        The traversal starts at ``id_a``, so the ``id_b -> id_a`` edge is a
        real cycle back to the root.  Keyed lookups (rather than a
        side_effect list) keep the graph well-defined for every visit, so
        the assertion proves the visited set stopped the walk instead of a
        mock running out of values.
        """
        id_a = uuid4()
        id_b = uuid4()
        events = {
            f"event:{id_a}": {"id": str(id_a), "name": "A"},
            f"event:{id_b}": {"id": str(id_b), "name": "B"},
        }
        # a -> b -> a (cycle); default max_depth of 5 would otherwise
        # produce a 5-event chain.
        links = {
            f"event:{id_a}:effects": {str(id_b)},
            f"event:{id_b}:effects": {str(id_a)},
        }
        mock_redis.json().get.side_effect = lambda key: events.get(key)
        mock_redis.smembers.side_effect = lambda key: links.get(key, set())

        chain = await service.find_causal_chain(id_a, direction="forward")
        assert len(chain) == 2
        assert [e["name"] for e in chain] == ["A", "B"]

    @pytest.mark.asyncio
    async def test_empty_chain(self, service, mock_redis):
        mock_redis.json().get.return_value = None
        chain = await service.find_causal_chain(uuid4())
        assert chain == []
        # A missing root event stops the walk before any link lookup.
        mock_redis.smembers.assert_not_awaited()


# --- Entity ID Lookup ---


class TestGetEntityIdByName:
    """Tests for _get_entity_id_by_name."""

    @pytest.mark.asyncio
    async def test_found(self, service, mock_redis):
        mock_redis.get.return_value = b"some-uuid"
        result = await service._get_entity_id_by_name("Python")
        assert result == "some-uuid"
        mock_redis.get.assert_awaited_with("entity:name:python")

    @pytest.mark.asyncio
    async def test_found_with_decoded_responses_client(self, service, mock_redis):
        """The live client sets decode_responses=True, so get() yields str.

        A bare ``.decode()`` raised AttributeError on this — the shape that
        actually runs in production (#13270).
        """
        mock_redis.get.return_value = "some-uuid"
        result = await service._get_entity_id_by_name("Python")
        assert result == "some-uuid"

    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_redis):
        mock_redis.get.return_value = None
        result = await service._get_entity_id_by_name("Unknown")
        assert result is None

    @pytest.mark.asyncio
    async def test_normalizes_name(self, service, mock_redis):
        mock_redis.get.return_value = b"id"
        await service._get_entity_id_by_name("  Python  ")
        mock_redis.get.assert_awaited_with("entity:name:python")
