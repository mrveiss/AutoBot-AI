# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for temporal fact validity (valid_from / valid_to) on memory graph entities
and relations.

Issue #3790.
"""

import sys
import types
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub out heavy dependencies so the modules import without a real Redis
# ---------------------------------------------------------------------------

_autobot_shared = types.ModuleType("autobot_shared")
_autobot_shared.__path__ = []  # make it a package

_redis_client_mod = types.ModuleType("autobot_shared.redis_client")
_redis_client_mod.get_redis_client = MagicMock(return_value=None)

_redis_mgmt = types.ModuleType("autobot_shared.redis_management")
_redis_mgmt.__path__ = []
_redis_types = types.ModuleType("autobot_shared.redis_management.types")
_redis_types.DATABASE_MAPPING = {"knowledge": 2}

_ssot = types.ModuleType("autobot_shared.ssot_config")
_cfg = MagicMock()
_cfg.vm.redis = "127.0.0.1"
_ssot.config = _cfg

for name, mod in [
    ("autobot_shared", _autobot_shared),
    ("autobot_shared.redis_client", _redis_client_mod),
    ("autobot_shared.redis_management", _redis_mgmt),
    ("autobot_shared.redis_management.types", _redis_types),
    ("autobot_shared.ssot_config", _ssot),
]:
    sys.modules.setdefault(name, mod)


# Now import the modules under test (after stubs are in place)
from autobot_memory_graph.entities import EntityOperationsMixin  # noqa: E402
from autobot_memory_graph.queries import (  # noqa: E402
    QueryOperationsMixin,
    _is_entity_valid,
    _is_entity_valid_at,
)
from autobot_memory_graph.relations import RelationOperationsMixin  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _entity(valid_from: str | None = None, valid_to: str | None = None, entity_type: str = "TASK") -> Dict[str, Any]:
    """Build a minimal entity dict for testing."""
    return {
        "id": "aaaa-1111",
        "type": entity_type,
        "name": "Test Entity",
        "observations": [],
        "metadata": {
            "valid_from": valid_from,
            "valid_to": valid_to,
        },
    }


def _make_graph():
    """Build a minimal AutoBotMemoryGraph-like object using only the mixins."""

    class FakeGraph(EntityOperationsMixin, RelationOperationsMixin, QueryOperationsMixin):
        def __init__(self):
            self.redis_client = MagicMock()
            self.knowledge_base = None
            self.search_cache = {}
            self.embedding_cache = {}
            self._initialized = True

        def ensure_initialized(self):
            pass

    return FakeGraph()


# ---------------------------------------------------------------------------
# Unit tests — _is_entity_valid helper
# ---------------------------------------------------------------------------


class TestIsEntityValid:
    def test_no_metadata_key_is_valid(self):
        """Entity without metadata dict is treated as valid (legacy data)."""
        assert _is_entity_valid({}) is True

    def test_valid_to_none_is_valid(self):
        assert _is_entity_valid(_entity(valid_to=None)) is True

    def test_valid_to_set_is_expired(self):
        past = _iso(_now() - timedelta(hours=1))
        assert _is_entity_valid(_entity(valid_to=past)) is False

    def test_future_valid_to_still_valid(self):
        future = _iso(_now() + timedelta(hours=1))
        assert _is_entity_valid(_entity(valid_to=future)) is True  # still valid until future


# ---------------------------------------------------------------------------
# Unit tests — _is_entity_valid_at helper
# ---------------------------------------------------------------------------


class TestIsEntityValidAt:
    def test_no_bounds_always_valid(self):
        """Legacy entity with no valid_from/valid_to is valid at any point."""
        e = _entity(valid_from=None, valid_to=None)
        assert _is_entity_valid_at(e, _iso(_now())) is True

    def test_valid_at_midpoint(self):
        past = _iso(_now() - timedelta(hours=2))
        future = _iso(_now() + timedelta(hours=2))
        e = _entity(valid_from=past, valid_to=future)
        assert _is_entity_valid_at(e, _iso(_now())) is True

    def test_as_of_before_valid_from(self):
        future = _iso(_now() + timedelta(hours=1))
        e = _entity(valid_from=future, valid_to=None)
        assert _is_entity_valid_at(e, _iso(_now())) is False

    def test_as_of_after_valid_to(self):
        past_start = _iso(_now() - timedelta(hours=2))
        past_end = _iso(_now() - timedelta(hours=1))
        e = _entity(valid_from=past_start, valid_to=past_end)
        assert _is_entity_valid_at(e, _iso(_now())) is False

    def test_exactly_at_valid_to_boundary(self):
        boundary = _iso(_now())
        e = _entity(valid_from=None, valid_to=boundary)
        # valid_to >= as_of  → boundary >= boundary → True
        assert _is_entity_valid_at(e, boundary) is True


# ---------------------------------------------------------------------------
# Integration-style tests — entity operations
# ---------------------------------------------------------------------------


class TestEntityTemporalFields:
    def test_prepare_metadata_includes_valid_fields(self):
        graph = _make_graph()
        meta = graph._prepare_entity_metadata(None, None)
        assert "valid_from" in meta
        assert meta["valid_to"] is None
        # valid_from should be parseable ISO-8601
        datetime.fromisoformat(meta["valid_from"])

    @pytest.mark.asyncio
    async def test_invalidate_entity_sets_valid_to(self):
        graph = _make_graph()
        entity_id = "test-uuid-1234"
        stored = {
            "id": entity_id,
            "type": "TASK",
            "metadata": {"valid_from": _iso(_now()), "valid_to": None},
        }

        json_mock = MagicMock()
        json_mock.get = AsyncMock(return_value=stored)
        json_mock.set = AsyncMock()
        graph.redis_client.json = MagicMock(return_value=json_mock)

        result = await graph.invalidate_entity(entity_id)

        assert result is True
        # First set call should be for valid_to
        first_call = json_mock.set.call_args_list[0]
        assert first_call.args[1] == "$.metadata.valid_to"
        assert first_call.args[2] is not None  # some timestamp string

    @pytest.mark.asyncio
    async def test_invalidate_entity_returns_false_when_not_found(self):
        graph = _make_graph()
        json_mock = MagicMock()
        json_mock.get = AsyncMock(return_value=None)
        graph.redis_client.json = MagicMock(return_value=json_mock)

        result = await graph.invalidate_entity("nonexistent-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_invalidate_entity_accepts_custom_ended_at(self):
        graph = _make_graph()
        entity_id = "test-uuid-5678"
        stored = {"id": entity_id, "type": "TASK", "metadata": {"valid_to": None}}

        custom_ts = "2025-01-15T12:00:00+00:00"
        json_mock = MagicMock()
        json_mock.get = AsyncMock(return_value=stored)
        json_mock.set = AsyncMock()
        graph.redis_client.json = MagicMock(return_value=json_mock)

        await graph.invalidate_entity(entity_id, ended_at=custom_ts)

        first_call = json_mock.set.call_args_list[0]
        assert first_call.args[2] == custom_ts


# ---------------------------------------------------------------------------
# Integration-style tests — relation operations
# ---------------------------------------------------------------------------


class TestRelationTemporalFields:
    def test_build_relation_objects_has_temporal_fields(self):
        graph = _make_graph()
        rel, rev = graph._build_relation_objects("from-id", "to-id", "depends_on", 1.0, None)
        assert "valid_from" in rel
        assert rel["valid_to"] is None
        assert "valid_from" in rev
        assert rev["valid_to"] is None

    def test_build_relation_by_id_objects_has_temporal_fields(self):
        graph = _make_graph()
        rel, rev = graph._build_relation_by_id_objects("from-id", "to-id", "depends_on", None)
        assert "valid_from" in rel
        assert rel["valid_to"] is None
        assert "valid_from" in rev
        assert rev["valid_to"] is None

    @pytest.mark.asyncio
    async def test_invalidate_relation_sets_valid_to(self):
        graph = _make_graph()
        from_id = "aaa"
        to_id = "bbb"
        rel_type = "depends_on"

        out_data = {
            "entity_id": from_id,
            "relations": [
                {"to": to_id, "type": rel_type, "valid_to": None},
                {"to": "other", "type": rel_type, "valid_to": None},
            ],
        }
        in_data = {
            "entity_id": to_id,
            "relations": [{"from": from_id, "type": rel_type, "valid_to": None}],
        }

        async def fake_get(key):
            if "out" in key:
                return out_data
            return in_data

        json_mock = MagicMock()
        json_mock.get = AsyncMock(side_effect=fake_get)
        json_mock.set = AsyncMock()
        graph.redis_client.json = MagicMock(return_value=json_mock)

        result = await graph.invalidate_relation(from_id, rel_type, to_id)

        assert result is True
        # Verify valid_to was stamped on the matching outgoing relation
        assert out_data["relations"][0]["valid_to"] is not None
        # Non-matching relation should be untouched
        assert out_data["relations"][1]["valid_to"] is None

    @pytest.mark.asyncio
    async def test_invalidate_relation_returns_false_when_no_match(self):
        graph = _make_graph()

        json_mock = MagicMock()
        json_mock.get = AsyncMock(return_value=None)
        graph.redis_client.json = MagicMock(return_value=json_mock)

        result = await graph.invalidate_relation("x", "depends_on", "y")
        assert result is False


# ---------------------------------------------------------------------------
# Integration-style tests — query operations
# ---------------------------------------------------------------------------


class TestQueryTemporalFiltering:
    def _make_entities(self):
        past = _iso(_now() - timedelta(hours=1))
        future = _iso(_now() + timedelta(hours=1))
        active = _entity(valid_from=None, valid_to=None, entity_type="TASK")
        active["name"] = "Active Task"
        expired = _entity(valid_from=None, valid_to=past, entity_type="TASK")
        expired["name"] = "Expired Task"
        future_entity = _entity(valid_from=future, valid_to=None, entity_type="TASK")
        future_entity["name"] = "Future Task"
        return active, expired, future_entity

    @pytest.mark.asyncio
    async def test_fallback_search_excludes_expired_by_default(self):
        graph = _make_graph()
        active, expired, _ = self._make_entities()

        async def fake_scan_iter(match):
            for k in ["memory:entity:active", "memory:entity:expired"]:
                yield k

        pipe_mock = MagicMock()
        pipe_mock.execute = AsyncMock(return_value=[active, expired])
        pipe_mock.json = MagicMock(return_value=pipe_mock)
        pipe_mock.get = MagicMock(return_value=pipe_mock)

        graph.redis_client.scan_iter = fake_scan_iter
        graph.redis_client.pipeline = MagicMock(return_value=pipe_mock)

        results = await graph._fallback_search("", "TASK", 50)
        names = [e["name"] for e in results]
        assert "Active Task" in names
        assert "Expired Task" not in names

    @pytest.mark.asyncio
    async def test_fallback_search_include_expired_returns_all(self):
        graph = _make_graph()
        active, expired, _ = self._make_entities()

        async def fake_scan_iter(match):
            for k in ["memory:entity:active", "memory:entity:expired"]:
                yield k

        pipe_mock = MagicMock()
        pipe_mock.execute = AsyncMock(return_value=[active, expired])
        pipe_mock.json = MagicMock(return_value=pipe_mock)
        pipe_mock.get = MagicMock(return_value=pipe_mock)

        graph.redis_client.scan_iter = fake_scan_iter
        graph.redis_client.pipeline = MagicMock(return_value=pipe_mock)

        results = await graph._fallback_search("", "TASK", 50, include_expired=True)
        names = [e["name"] for e in results]
        assert "Active Task" in names
        assert "Expired Task" in names

    @pytest.mark.asyncio
    async def test_get_entities_as_of_returns_correct_set(self):
        graph = _make_graph()
        two_hours_ago = _now() - timedelta(hours=2)
        one_hour_ago = _now() - timedelta(hours=1)
        now = _now()

        # Entity valid 2h ago → 1h ago (expired before as_of=now)
        old = _entity(
            valid_from=_iso(two_hours_ago),
            valid_to=_iso(one_hour_ago),
            entity_type="TASK",
        )
        old["name"] = "Old Entity"

        # Entity valid from 1h ago onwards (no end)
        current = _entity(valid_from=_iso(one_hour_ago), valid_to=None, entity_type="TASK")
        current["name"] = "Current Entity"

        # Entity of wrong type
        wrong_type = _entity(valid_from=None, valid_to=None, entity_type="BUG")
        wrong_type["name"] = "Bug Entity"

        async def fake_scan_iter(match):
            for k in ["k1", "k2", "k3"]:
                yield k

        pipe_mock = MagicMock()
        pipe_mock.execute = AsyncMock(return_value=[old, current, wrong_type])
        pipe_mock.json = MagicMock(return_value=pipe_mock)
        pipe_mock.get = MagicMock(return_value=pipe_mock)

        graph.redis_client.scan_iter = fake_scan_iter
        graph.redis_client.pipeline = MagicMock(return_value=pipe_mock)

        results = await graph.get_entities_as_of("TASK", _iso(now))
        names = [e["name"] for e in results]

        assert "Current Entity" in names
        assert "Old Entity" not in names  # expired before as_of
        assert "Bug Entity" not in names  # wrong type

    @pytest.mark.asyncio
    async def test_legacy_entity_without_valid_to_treated_as_current(self):
        """Entities already in Redis without valid_to must not be filtered out."""
        legacy = {"id": "xyz", "type": "TASK", "name": "Legacy", "observations": []}
        # No "metadata" key at all
        assert _is_entity_valid(legacy) is True
        assert _is_entity_valid_at(legacy, _iso(_now())) is True
