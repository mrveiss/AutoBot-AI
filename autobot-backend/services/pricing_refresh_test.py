# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Integration tests for auto-refresh pricing infrastructure (GH#6480)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_shared.pricing.sources import ModelPricing


# ---------------------------------------------------------------------------
# ModelPricing round-trip
# ---------------------------------------------------------------------------


def test_model_pricing_round_trip():
    now = datetime.now(tz=timezone.utc)
    mp = ModelPricing(
        provider="anthropic",
        model_id="claude-sonnet-4-0",
        input_per_1m=3.0,
        output_per_1m=15.0,
        cache_read_per_1m=0.30,
        updated_at=now,
    )
    d = mp.to_dict()
    restored = ModelPricing.from_dict(d)
    assert restored.input_per_1m == mp.input_per_1m
    assert restored.output_per_1m == mp.output_per_1m
    assert restored.provider == mp.provider
    assert restored.model_id == mp.model_id


def test_model_pricing_as_legacy_dict():
    mp = ModelPricing(provider="openai", model_id="gpt-4.1", input_per_1m=2.0, output_per_1m=8.0)
    legacy = mp.as_legacy_dict()
    assert legacy == {"input": 2.0, "output": 8.0}


# ---------------------------------------------------------------------------
# PricingSource implementations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anthropic_source_returns_models():
    from llm_shared.pricing.anthropic_source import AnthropicPricingSource

    src = AnthropicPricingSource()
    result = await src.fetch()
    assert len(result) > 0
    assert all(isinstance(v, ModelPricing) for v in result.values())
    assert all(v.provider == "anthropic" for v in result.values())


@pytest.mark.asyncio
async def test_openai_source_returns_models():
    from llm_shared.pricing.openai_source import OpenAIPricingSource

    src = OpenAIPricingSource()
    result = await src.fetch()
    assert len(result) > 0
    assert all(isinstance(v, ModelPricing) for v in result.values())
    assert all(v.provider == "openai" for v in result.values())


# ---------------------------------------------------------------------------
# PricingRedisStore
# ---------------------------------------------------------------------------


def _make_redis_mock(stored: dict | None = None):
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=json.dumps(stored) if stored else None)
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.scan_iter = MagicMock(return_value=_async_iter([]))
    pipe_mock = AsyncMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=None)
    pipe_mock.setex = AsyncMock()
    pipe_mock.execute = AsyncMock(return_value=[True])
    mock.pipeline = MagicMock(return_value=pipe_mock)
    return mock


async def _async_iter(items):
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_redis_store_get_hit():
    from llm_shared.pricing.redis_store import PricingRedisStore

    mp = ModelPricing(
        provider="anthropic",
        model_id="claude-haiku-4-5",
        input_per_1m=0.8,
        output_per_1m=4.0,
        updated_at=datetime.now(tz=timezone.utc),
    )
    redis_mock = _make_redis_mock(stored=mp.to_dict())

    store = PricingRedisStore()
    with patch("llm_shared.pricing.redis_store.get_async_redis_client", AsyncMock(return_value=redis_mock)):
        result = await store.get("anthropic", "claude-haiku-4-5")

    assert result is not None
    assert result.input_per_1m == 0.8
    assert result.model_id == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_redis_store_get_miss():
    from llm_shared.pricing.redis_store import PricingRedisStore

    redis_mock = _make_redis_mock(stored=None)
    store = PricingRedisStore()
    with patch("llm_shared.pricing.redis_store.get_async_redis_client", AsyncMock(return_value=redis_mock)):
        result = await store.get("anthropic", "nonexistent-model")
    assert result is None


@pytest.mark.asyncio
async def test_redis_store_set():
    from llm_shared.pricing.redis_store import PricingRedisStore

    redis_mock = _make_redis_mock()
    redis_mock.setex = AsyncMock(return_value=True)
    mp = ModelPricing(provider="openai", model_id="gpt-4.1", input_per_1m=2.0, output_per_1m=8.0)
    store = PricingRedisStore()
    with patch("llm_shared.pricing.redis_store.get_async_redis_client", AsyncMock(return_value=redis_mock)):
        ok = await store.set(mp)
    assert ok is True
    redis_mock.setex.assert_called_once()


# ---------------------------------------------------------------------------
# pricing_refresh Celery task — simulate provider change reflected on next read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_writes_new_pricing_to_redis():
    """Simulates: provider price change → next read reflects new value."""
    from services.pricing_refresh import _refresh_all

    captured_writes: dict[str, ModelPricing] = {}

    async def fake_set_many(pricings):
        captured_writes.update(pricings)
        return len(pricings)

    async def fake_set_status(provider, success, model_count):
        pass

    mock_store = AsyncMock()
    mock_store.set_many = fake_set_many
    mock_store.set_refresh_status = fake_set_status

    with patch("services.pricing_refresh.PricingRedisStore", return_value=mock_store):
        summary = await _refresh_all()

    assert "anthropic" in summary
    assert "openai" in summary
    assert summary["anthropic"]["success"] is True
    assert summary["openai"]["success"] is True
    assert len(captured_writes) > 0


# ---------------------------------------------------------------------------
# LLMCostTracker: Redis cache takes priority over hardcoded table
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_tracker_uses_redis_pricing_when_available():
    """When Redis has pricing, _build_and_persist_record uses it instead of hardcoded."""
    from services.llm_cost_tracker import LLMCostTracker

    tracker = LLMCostTracker()

    # Simulate Redis returning a custom price (0.01/0.02 per 1M) for a model
    cheap_pricing = ModelPricing(
        provider="anthropic",
        model_id="claude-opus-4-0",
        input_per_1m=0.01,  # artificially cheap
        output_per_1m=0.02,
        updated_at=datetime.now(tz=timezone.utc),
    )

    async def fake_redis_lookup(model_lower):
        if model_lower == "claude-opus-4-0":
            return cheap_pricing.as_legacy_dict()
        return None

    tracker._redis_pricing_lookup = fake_redis_lookup

    # 1M input tokens + 1M output tokens at cheap price = 0.01 + 0.02 = 0.03
    # Hardcoded would give 15.00 + 75.00 = 90.00
    with patch.object(tracker, "_store_usage_record", AsyncMock(return_value=True)):
        cost = None

        async def capture_record(*args, **kwargs):
            nonlocal cost
            # intercept at the record-creation step
            record = await tracker._build_and_persist_record(
                "anthropic", "claude-opus-4-0", 1_000_000, 1_000_000,
                None, None, None, None, None, True, None, None,
            )
            cost = record.cost_usd
            return True

        with patch.object(tracker, "_store_usage_record", capture_record):
            await capture_record()

    assert cost is not None
    assert abs(cost - 0.03) < 1e-5, f"Expected 0.03 but got {cost}"
