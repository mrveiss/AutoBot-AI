# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Integration tests for auto-refresh pricing infrastructure (GH#6480)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
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


@pytest.mark.asyncio
async def test_google_source_returns_models():
    from llm_shared.pricing.google_source import GooglePricingSource

    src = GooglePricingSource()
    result = await src.fetch()
    assert len(result) > 0
    assert all(isinstance(v, ModelPricing) for v in result.values())
    assert all(v.provider == "google" for v in result.values())


@pytest.mark.asyncio
async def test_deepseek_source_returns_models():
    from llm_shared.pricing.deepseek_source import DeepSeekPricingSource

    src = DeepSeekPricingSource()
    result = await src.fetch()
    assert len(result) > 0
    assert all(isinstance(v, ModelPricing) for v in result.values())
    assert all(v.provider == "deepseek" for v in result.values())


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


class _DictRedis:
    """Just enough of an async Redis for the store's key paths, with each key's TTL recorded."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = value
        self.ttl.pop(key, None)
        return True

    async def setex(self, key, ttl, value):
        self.data[key] = value
        self.ttl[key] = ttl
        return True

    async def delete(self, key):
        return 1 if self.data.pop(key, None) is not None else 0

    def pipeline(self):
        return _DictPipeline(self)


class _DictPipeline:
    def __init__(self, redis: _DictRedis) -> None:
        self._redis, self._queued = redis, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    def setex(self, key, ttl, value):
        self._queued.append((key, ttl, value))

    async def execute(self, raise_on_error=True):
        return [await self._redis.setex(*queued) for queued in self._queued]


@pytest.fixture
def dict_redis():
    """A real PricingRedisStore talks to this in-memory Redis for the test's duration."""
    fake = _DictRedis()
    with patch("llm_shared.pricing.redis_store.get_async_redis_client", AsyncMock(return_value=fake)):
        yield fake


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
async def test_an_override_is_stored_apart_from_refreshed_prices_and_never_expires(dict_redis):
    from llm_shared.pricing.redis_store import PricingRedisStore

    mp = ModelPricing(provider="openai", model_id="GPT-4.1", input_per_1m=2.0, output_per_1m=8.0)
    assert await PricingRedisStore().set_override(mp) is True
    assert list(dict_redis.data) == ["model_pricing:override:gpt-4.1"]
    assert dict_redis.ttl == {}, "an operator's override must not expire on the refresh TTL"


# ---------------------------------------------------------------------------
# pricing_refresh Celery task — simulate provider change reflected on next read
# ---------------------------------------------------------------------------


def _source(provider, pricings=None, raises=None):
    """A stand-in catalogue whose fetch returns *pricings* (or raises)."""
    src = MagicMock()
    src.provider = provider
    src.fetch = AsyncMock(side_effect=raises) if raises else AsyncMock(return_value=pricings or {})
    return src


def _store():
    store = MagicMock()
    for name in ("set_refresh_status", "retain_refresh_status", "set_crosscheck"):
        setattr(store, name, AsyncMock())
    store.set_many = AsyncMock(side_effect=lambda merged: len(merged))
    store.set_model_index = AsyncMock(side_effect=lambda merged: len(merged))
    return store


def _mp(provider, model_id, inp, out, source):
    return ModelPricing(provider=provider, model_id=model_id, input_per_1m=inp, output_per_1m=out, source=source)


@pytest.mark.asyncio
async def test_refresh_writes_crosschecked_prices_and_keeps_its_denominator():
    """#16229: prices come from the live catalogues, each labelled with its cross-check verdict."""
    from services.pricing_refresh import refresh_all

    primary = {
        "claude-haiku-4-5": _mp("anthropic", "claude-haiku-4-5", 1.0, 5.0, "litellm"),
        "gpt-4o": _mp("openai", "gpt-4o", 2.5, 10.0, "litellm"),
    }
    secondary = {
        "anthropic/claude-haiku-4.5": _mp("anthropic", "claude-haiku-4.5", 1.0, 5.0, "openrouter"),
        "x-ai/grok-9": _mp("x-ai", "grok-9", 3.0, 15.0, "openrouter"),
    }
    store = _store()
    with (
        patch(
            "services.pricing_refresh._build_sources",
            return_value=(_source("litellm", primary), _source("openrouter", secondary)),
        ),
        patch("llm_shared.pricing.redis_store.PricingRedisStore", return_value=store),
    ):
        summary = await refresh_all()

    [merged] = store.set_many.call_args.args
    verdicts = {p.model_id: p.crosscheck for p in merged.values()}
    assert verdicts == {"claude-haiku-4-5": "agree", "gpt-4o": "single", "grok-9": "single"}
    assert summary["crosscheck"]["compared"] == 1, "the report must say how many it actually compared"
    assert (summary["crosscheck"]["only_primary"], summary["crosscheck"]["only_secondary"]) == (1, 1)
    assert summary["sources"] == {
        "litellm": {"success": True, "model_count": 2},
        "openrouter": {"success": True, "model_count": 2},
    }
    store.retain_refresh_status.assert_awaited_once_with({"litellm", "openrouter"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failed_primary", [_source("litellm", {}), _source("litellm", raises=RuntimeError("down"))], ids=["empty", "raises"]
)
async def test_a_failed_primary_writes_nothing_and_is_recorded_as_failed(failed_primary):
    """A failed catalogue must not refresh anything -- stored prices keep their real age."""
    from services.pricing_refresh import refresh_all

    store = _store()
    secondary = _source("openrouter", {"x/y": _mp("x", "y", 1.0, 1.0, "openrouter")})
    with (
        patch("services.pricing_refresh._build_sources", return_value=(failed_primary, secondary)),
        patch("llm_shared.pricing.redis_store.PricingRedisStore", return_value=store),
    ):
        summary = await refresh_all()

    store.set_many.assert_not_called()
    store.set_model_index.assert_not_called()
    assert summary["sources"]["litellm"] == {"success": False, "model_count": 0}
    store.set_refresh_status.assert_any_await("litellm", success=False, model_count=0)


# ---------------------------------------------------------------------------
# refresh_if_empty (#16231, AC2) and main() (#16231, AC1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_if_empty_refreshes_a_never_refreshed_store():
    """An empty refresh_status means first boot: refresh_if_empty must actually refresh."""
    from services.pricing_refresh import refresh_if_empty

    store = MagicMock()
    store.get_refresh_status = AsyncMock(return_value={})
    fake_summary = {"sources": {}, "written": 3}
    with (
        patch("llm_shared.pricing.redis_store.PricingRedisStore", return_value=store),
        patch("services.pricing_refresh.refresh_all", AsyncMock(return_value=fake_summary)) as refresh_mock,
    ):
        result = await refresh_if_empty()

    refresh_mock.assert_awaited_once()
    assert result == fake_summary


@pytest.mark.asyncio
async def test_refresh_if_empty_does_nothing_when_status_is_not_empty():
    """A store that has already refreshed once must not be refreshed again at boot."""
    from services.pricing_refresh import refresh_if_empty

    store = MagicMock()
    store.get_refresh_status = AsyncMock(return_value={"litellm": {"success": True}})
    with (
        patch("llm_shared.pricing.redis_store.PricingRedisStore", return_value=store),
        patch("services.pricing_refresh.refresh_all", AsyncMock()) as refresh_mock,
    ):
        result = await refresh_if_empty()

    refresh_mock.assert_not_called()
    assert result is None


@pytest.mark.asyncio
async def test_refresh_if_empty_never_raises_on_a_broken_store():
    """A first-boot refresh failure must not propagate — startup must never fail on it."""
    from services.pricing_refresh import refresh_if_empty

    store = MagicMock()
    store.get_refresh_status = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch("llm_shared.pricing.redis_store.PricingRedisStore", return_value=store):
        result = await refresh_if_empty()

    assert result is None


def test_refresh_if_empty_task_is_registered_under_its_name():
    """#16231 AC2: pricing.refresh_if_empty is the task worker_ready queues by name."""
    from services.pricing_refresh import refresh_pricing_if_empty

    assert refresh_pricing_if_empty.name == "pricing.refresh_if_empty"


def test_worker_ready_queues_the_first_boot_refresh_task_and_never_runs_it_inline():
    """#16231 AC2: a Celery worker coming up enqueues the check via .delay(), not a direct call."""
    from services.pricing_refresh import _queue_first_boot_refresh

    with patch("services.pricing_refresh.refresh_pricing_if_empty.delay") as delay_mock:
        _queue_first_boot_refresh()

    delay_mock.assert_called_once_with()


def test_the_first_boot_refresh_handler_is_actually_wired_to_worker_ready():
    """Assert the WIRING, not just the handler — mirrors workers/audit_tasks_test.py's #13570 guard."""
    import weakref

    from celery.signals import worker_ready

    import services.pricing_refresh as pricing_refresh_module

    resolved = [r() if isinstance(r, weakref.ReferenceType) else r for _, r in worker_ready.receivers]
    names = {getattr(r, "__name__", "") for r in resolved if r is not None}
    assert pricing_refresh_module._queue_first_boot_refresh.__name__ in names


def test_main_returns_zero_and_writes_summary_when_prices_were_written(capsys):
    """The one-shot CLI writes its JSON summary as machine output and exits 0."""
    from services import pricing_refresh

    fake_summary = {"sources": {"litellm": {"success": True, "model_count": 2}}, "written": 2, "indexed": 2}
    with patch("services.pricing_refresh.refresh_all", AsyncMock(return_value=fake_summary)):
        rc = pricing_refresh.main()

    assert rc == 0
    assert json.loads(capsys.readouterr().out.strip()) == fake_summary


def test_main_returns_one_and_still_writes_summary_when_nothing_was_written(capsys):
    """An offline install: main() must still emit the summary, and exit non-zero (#16231)."""
    from services import pricing_refresh

    fake_summary = {"sources": {"litellm": {"success": False, "model_count": 0}}}
    with patch("services.pricing_refresh.refresh_all", AsyncMock(return_value=fake_summary)):
        rc = pricing_refresh.main()

    assert rc == 1
    assert json.loads(capsys.readouterr().out.strip()) == fake_summary


@pytest.mark.asyncio
async def test_a_failed_attempt_keeps_the_last_successful_refresh_time():
    """#16229: re-stamping last_refresh_at on failure is what made stale pricing look fresh."""
    from llm_shared.pricing.redis_store import PricingRedisStore

    earlier = "2026-09-01T02:15:00+00:00"
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=json.dumps({"litellm": {"success": True, "last_refresh_at": earlier}}))
    store = PricingRedisStore()
    with patch("llm_shared.pricing.redis_store.get_async_redis_client", AsyncMock(return_value=redis_mock)):
        await store.set_refresh_status("litellm", success=False, model_count=0)

    written = json.loads(redis_mock.setex.call_args.args[2])["litellm"]
    assert written["last_refresh_at"] == earlier, "a failed attempt must not look like a fresh refresh"
    assert written["success"] is False and written["last_attempt_at"] != earlier


@pytest.mark.asyncio
async def test_the_model_index_skips_reseller_routes_and_variants():
    from llm_shared.pricing.redis_store import PricingRedisStore

    store = PricingRedisStore()
    captured = {}

    async def fake_setex_many(items):
        captured.update(items)
        return len(items)

    store._setex_many = fake_setex_many
    await store.set_model_index(
        {
            "a": _mp("anthropic", "Claude-Haiku-4-5", 1.0, 5.0, "litellm"),
            "b": _mp("bedrock", "bedrock/anthropic.claude", 9.0, 9.0, "litellm"),
            "c": _mp("vendor", "model:free", 0.0, 0.0, "openrouter"),
            "d": _mp("openai", "claude-haiku-4-5", 7.0, 7.0, "openrouter"),
        }
    )
    assert list(captured) == ["model_pricing:by_model:claude-haiku-4-5"]
    assert captured["model_pricing:by_model:claude-haiku-4-5"]["input_per_1m"] == 1.0, "first entry wins"


@pytest.mark.asyncio
async def test_cost_tracker_finds_a_live_price_by_model_name(dict_redis):
    """#16229: LiteLLM files Gemini under "gemini"; the by-model index finds it without a provider key."""
    from llm_shared.pricing.redis_store import PricingRedisStore
    from services.llm_cost_tracker import LLMCostTracker

    await PricingRedisStore().set_model_index({"k": _mp("gemini", "gemini-2.5-pro", 1.25, 10.0, "litellm")})
    legacy = await LLMCostTracker()._redis_pricing_lookup("gemini-2.5-pro")
    assert legacy == {"input": 1.25, "output": 10.0}


@pytest.mark.asyncio
async def test_an_override_outranks_the_refreshed_price_and_survives_the_next_refresh(dict_redis):
    """#16229 review: an override was written, reported success, and changed nothing."""
    from llm_shared.pricing.redis_store import PricingRedisStore

    store = PricingRedisStore()
    live = {"litellm:claude-haiku-4-5": _mp("anthropic", "claude-haiku-4-5", 1.0, 5.0, "litellm")}
    await store.set_model_index(live)
    await store.set_override(_mp("anthropic", "claude-haiku-4-5", 2.0, 9.0, "override"))
    await store.set_model_index(live)  # the next daily refresh
    assert (await store.resolve("claude-haiku-4-5")).input_per_1m == 2.0
    assert await store.delete_override("claude-haiku-4-5") is True
    assert (await store.resolve("claude-haiku-4-5")).input_per_1m == 1.0, "removal restores the live price"
    assert await store.delete_override("claude-haiku-4-5") is False


@pytest.mark.asyncio
async def test_an_admin_override_changes_what_the_cost_tracker_charges(dict_redis):
    """End to end: the admin endpoints, the store and the tracker agree on one price."""
    from api.admin_pricing import delete_model_pricing_override, override_model_pricing
    from api.schemas_pricing import PricingOverrideRequest
    from llm_shared.pricing.redis_store import PricingRedisStore
    from services.llm_cost_tracker import LLMCostTracker

    await PricingRedisStore().set_model_index({"k": _mp("anthropic", "claude-haiku-4-5", 1.0, 5.0, "litellm")})
    body = PricingOverrideRequest(input_per_1m=2.0, output_per_1m=9.0)
    response = await override_model_pricing("anthropic", "claude-haiku-4-5", body, _admin=True)
    assert response["stored"] is True
    tracker = LLMCostTracker()
    assert (await tracker._redis_pricing_lookup("claude-haiku-4-5"))["input"] == 2.0
    removed = await delete_model_pricing_override("anthropic", "claude-haiku-4-5", _admin=True)
    assert removed["deleted"] is True
    assert (await tracker._redis_pricing_lookup("claude-haiku-4-5"))["input"] == 1.0


@pytest.mark.asyncio
async def test_admin_refresh_now_returns_the_refresh_summary():
    """#16231: the admin 'refresh now' endpoint awaits a real refresh and returns its summary."""
    from api.admin_pricing import refresh_pricing_now

    fake_summary = {"sources": {"litellm": {"success": True, "model_count": 5}}, "written": 5, "indexed": 5}
    with patch("services.pricing_refresh.refresh_all", AsyncMock(return_value=fake_summary)):
        result = await refresh_pricing_now(_admin=True)

    assert result == fake_summary


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
        record = await tracker._build_and_persist_record(
            "anthropic",
            "claude-opus-4-0",
            1_000_000,
            1_000_000,
            None,
            None,
            None,
            None,
            None,
            True,
            None,
            None,
        )
        cost = record.cost_usd

    assert cost is not None
    assert abs(cost - 0.03) < 1e-5, f"Expected 0.03 but got {cost}"


# ---------------------------------------------------------------------------
# Beat cadence (#16231, AC3): env-backed, and the TTL always outlasts it
# ---------------------------------------------------------------------------


def test_beat_cadence_is_env_backed_not_a_fixed_crontab():
    """celery_app.py is heavy/pytest-stubbed (#7766); read its source like celery_beat_registration_test.py."""
    celery_app_src = (Path(__file__).resolve().parents[1] / "celery_app.py").read_text(encoding="utf-8")

    match = re.search(r'"pricing-refresh-daily":\s*\{[^}]*"schedule":\s*([^,\n]+),', celery_app_src)
    assert match, "pricing-refresh-daily entry not found in celery_app.py beat_schedule"
    assert match.group(1).strip() == "timedelta(hours=_PRICING_REFRESH_INTERVAL_HOURS)"
    assert (
        "from llm_shared.pricing.redis_store import REFRESH_INTERVAL_HOURS as _PRICING_REFRESH_INTERVAL_HOURS"
        in celery_app_src
    ), "the beat cadence must be imported from the one env-backed constant, not redeclared"


def test_ttl_always_outlasts_the_refresh_interval_it_is_meant_to_survive():
    """#16231 AC3: the TTL can never be shorter than the cadence, whatever the env sets it to."""
    from llm_shared.pricing.redis_store import _TTL_SECONDS, REFRESH_INTERVAL_HOURS

    assert _TTL_SECONDS > REFRESH_INTERVAL_HOURS * 3600
