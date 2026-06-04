# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for RedisCache.set_json/.get_json default serializer (Issue #6696).

Background: ``json.dumps`` raised TypeError on dataclass instances (e.g.
``SystemMetric`` in autobot-backend/utils/system_metrics.py) — every Redis
cache write of dash_task analytics results silently failed. The fix is a
``default=`` fallback in cache_wrapper.set_json that handles dataclasses
and Pydantic models centrally.
"""

import dataclasses
from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest

from autobot_shared.redis_management.cache_wrapper import RedisCache, _json_default

# ---------------------------------------------------------------------------
# Sample types
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _Metric:
    timestamp: float
    name: str
    value: float
    metadata: Dict[str, Any] = None


class _PydanticV2Like:
    """Stand-in for a Pydantic v2 BaseModel — has model_dump()."""

    def __init__(self, name: str, value: int) -> None:
        self.name = name
        self.value = value

    def model_dump(self) -> Dict[str, Any]:
        return {"name": self.name, "value": self.value}


class _PydanticV1Like:
    """Stand-in for a Pydantic v1 BaseModel — has dict() + __fields__."""

    __fields__ = {"name": ..., "value": ...}

    def __init__(self, name: str, value: int) -> None:
        self.name = name
        self.value = value

    def dict(self) -> Dict[str, Any]:
        return {"name": self.name, "value": self.value}


# ---------------------------------------------------------------------------
# _json_default unit tests
# ---------------------------------------------------------------------------


class TestJsonDefault:
    """Issue #6696: the json.dumps default= fallback."""

    def test_serializes_dataclass(self) -> None:
        m = _Metric(timestamp=1.0, name="cpu", value=42.0, metadata={"host": "vm1"})
        assert _json_default(m) == {
            "timestamp": 1.0,
            "name": "cpu",
            "value": 42.0,
            "metadata": {"host": "vm1"},
        }

    def test_serializes_pydantic_v2_model(self) -> None:
        assert _json_default(_PydanticV2Like("k", 7)) == {"name": "k", "value": 7}

    def test_serializes_pydantic_v1_model(self) -> None:
        assert _json_default(_PydanticV1Like("k", 7)) == {"name": "k", "value": 7}

    def test_raises_typeerror_for_unknown_type(self) -> None:
        class Custom:
            pass

        with pytest.raises(TypeError, match="Custom"):
            _json_default(Custom())

    def test_does_not_treat_dataclass_class_itself_as_instance(self) -> None:
        # is_dataclass returns True for both the class and its instances —
        # we only want to serialise instances.
        with pytest.raises(TypeError):
            _json_default(_Metric)


# ---------------------------------------------------------------------------
# Round-trip integration tests
# ---------------------------------------------------------------------------


class TestRedisCacheRoundTrip:
    """Issue #6696: end-to-end set_json / get_json with non-JSON-native types."""

    @pytest.mark.asyncio
    async def test_dataclass_round_trip_via_set_json(self):
        """SystemMetric-shaped dataclass must serialise without raising."""
        store = {}

        async def fake_set(key, payload, ex=None):
            store[key] = payload
            return True

        async def fake_get(key):
            return store.get(key)

        client = AsyncMock()
        client.set = fake_set
        client.get = fake_get

        cache = RedisCache(client)
        m = _Metric(timestamp=1.0, name="cpu", value=42.0)

        ok = await cache.set_json("m:1", {"latest": m})
        assert ok is True
        assert "m:1" in store

        got = await cache.get_json("m:1")
        assert got == {"latest": {"timestamp": 1.0, "name": "cpu", "value": 42.0, "metadata": None}}

    @pytest.mark.asyncio
    async def test_pydantic_round_trip(self):
        store = {}

        async def fake_set(key, payload, ex=None):
            store[key] = payload
            return True

        async def fake_get(key):
            return store.get(key)

        client = AsyncMock()
        client.set = fake_set
        client.get = fake_get

        cache = RedisCache(client)
        ok = await cache.set_json("p:1", _PydanticV2Like("ratio", 99))
        assert ok is True
        assert (await cache.get_json("p:1")) == {"name": "ratio", "value": 99}

    @pytest.mark.asyncio
    async def test_unknown_type_still_logs_and_returns_false(self) -> None:
        """Custom unknown classes must surface the failure as before."""

        async def failing_set(*args, **kwargs) -> None:
            raise AssertionError("set() should never be called with bad payload")

        client = AsyncMock()
        client.set = failing_set

        cache = RedisCache(client)

        class Custom:
            pass

        ok = await cache.set_json("k", Custom())
        # set_json wraps json.dumps in try/except → False on failure, no raise
        assert ok is False
