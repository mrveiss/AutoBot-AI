# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for LLM cost tracker pricing. Issues #1961, #16230.

Rewritten for #16230. This module used to import ``MODEL_PRICING`` from
``services.llm_cost_tracker`` and assert properties of that hardcoded table --
completeness, orderings, zero-priced local models. The table is gone; pricing
is runtime state mirrored from Redis by ``llm_shared.pricing.sync_cache``.

Two of the old properties do not survive that move and are **not** restated
here as weaker versions of themselves:

* *"every required model has an entry"* was a commit-time fact about a literal.
  Whether the live catalogue covers a model is a property of Redis at runtime,
  and a repo test that asserted it would be asserting nothing.
* *"opus costs more than haiku"*, *"gpt-4.1 is cheaper than gpt-4-turbo"* were
  assertions about the table's numbers. The numbers now come from a vendor
  catalogue, and pinning them here would pin a copy of it.

What replaces them is the behaviour those tests existed to protect, which is
checkable against an injected snapshot: the right price is *selected* (exact →
longest-prefix → tier-correct fallback pattern), a local model is free without
consulting the cache at all, and a cold or stale cache degrades loudly to
$0.00 rather than silently pricing off fabricated data.
"""

import logging
import time
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.local_models import LOCAL_MODEL_NAMES
from constants.model_constants import (
    ANTHROPIC_CLAUDE_HAIKU4_5,
    ANTHROPIC_CLAUDE_OPUS4,
    ANTHROPIC_CLAUDE_SONNET4,
    OPENAI_GPT4O,
    OPENAI_GPT41,
    OPENAI_O3,
    OPENAI_O3_MINI,
)
from llm_shared.pricing import sync_cache
from llm_shared.pricing.sources import ModelPricing
from services.llm_cost_tracker import LLMCostTracker
from tests.fixtures.mocks import make_async_redis, make_redis_pipeline

_LOGGER_NAME = "services.llm_cost_tracker"


def _price(model_id: str, inp: float, out: float) -> ModelPricing:
    return ModelPricing(provider="test", model_id=model_id, input_per_1m=inp, output_per_1m=out)


#: A deliberately small catalogue. Every entry is here because some test below
#: names it; it is not a trimmed copy of the real one, and no test may assume a
#: model it does not put in here itself.
_CATALOGUE = {
    ANTHROPIC_CLAUDE_OPUS4.lower(): _price(ANTHROPIC_CLAUDE_OPUS4, 15.0, 75.0),
    ANTHROPIC_CLAUDE_SONNET4.lower(): _price(ANTHROPIC_CLAUDE_SONNET4, 3.0, 15.0),
    ANTHROPIC_CLAUDE_HAIKU4_5.lower(): _price(ANTHROPIC_CLAUDE_HAIKU4_5, 1.0, 5.0),
    OPENAI_GPT4O.lower(): _price(OPENAI_GPT4O, 2.5, 10.0),
    OPENAI_GPT41.lower(): _price(OPENAI_GPT41, 2.0, 8.0),
    OPENAI_O3.lower(): _price(OPENAI_O3, 10.0, 40.0),
    OPENAI_O3_MINI.lower(): _price(OPENAI_O3_MINI, 1.1, 4.4),
}


@pytest.fixture(autouse=True)
def _cold_cache():
    """Every test starts from a never-populated cache and leaves one behind.

    ``sync_cache._snapshot`` is a module global shared by every caller in the
    process, so a test that populated it and did not clear it would hand the
    next one a catalogue it never asked for -- the pricing equivalent of the
    order-dependent pass this module is being rewritten away from.
    """
    sync_cache._reset_for_tests()
    yield
    sync_cache._reset_for_tests()


def _populate(prices=None, age_s: float = 0.0) -> None:
    """Install *prices* as the live snapshot, ``age_s`` seconds old."""
    sync_cache._snapshot = sync_cache._Snapshot(
        prices=_CATALOGUE if prices is None else prices,
        fetched_at=time.monotonic() - age_s,
    )


class TestPriceSelection:
    """Which catalogue entry a model name resolves to (#1961, #16230)."""

    def setup_method(self):
        self.tracker = LLMCostTracker()

    def test_an_exactly_known_model_uses_its_own_price(self):
        _populate()
        entry = _CATALOGUE[OPENAI_GPT4O.lower()]
        cost = self.tracker.calculate_cost(OPENAI_GPT4O, 1_000_000, 1_000_000)
        assert cost == round(entry.input_per_1m + entry.output_per_1m, 6)

    def test_a_versioned_suffix_resolves_by_longest_prefix(self):
        """``gpt-4o-2024-11-20`` is the same model as ``gpt-4o``."""
        _populate()
        entry = _CATALOGUE[OPENAI_GPT4O.lower()]
        cost = self.tracker.calculate_cost(f"{OPENAI_GPT4O}-2024-11-20", 1_000_000, 0)
        assert cost == round(entry.input_per_1m, 6)

    def test_a_dotted_family_prefix_resolves_within_its_own_family(self):
        """``gpt-4.1-preview`` is a GPT-4.1, not a GPT-4o and not a GPT-4-turbo."""
        _populate()
        entry = _CATALOGUE[OPENAI_GPT41.lower()]
        cost = self.tracker.calculate_cost(f"{OPENAI_GPT41}-preview", 1_000_000, 0)
        assert cost == round(entry.input_per_1m, 6)
        assert cost != round(_CATALOGUE[OPENAI_GPT4O.lower()].input_per_1m, 6)

    def test_o3_does_not_resolve_to_o3_mini(self):
        """#2030's bidirectional-substring bug: prefix order must be longest-first.

        Both keys are in the catalogue and one is a prefix of the other, so a
        shortest-first scan would price ``o3`` at ``o3-mini``'s rate. The two
        prices differ by ~9x, which is the whole reason this is pinned.
        """
        _populate()
        cost = self.tracker.calculate_cost(OPENAI_O3, 1_000_000, 0)
        assert cost == round(_CATALOGUE[OPENAI_O3.lower()].input_per_1m, 6)
        assert cost != round(_CATALOGUE[OPENAI_O3_MINI.lower()].input_per_1m, 6)

    def test_o3_mini_still_resolves_to_itself(self):
        """The contrast: fixing the above must not send ``o3-mini`` to ``o3``."""
        _populate()
        cost = self.tracker.calculate_cost(OPENAI_O3_MINI, 1_000_000, 0)
        assert cost == round(_CATALOGUE[OPENAI_O3_MINI.lower()].input_per_1m, 6)


class TestUnknownModelFallback:
    """Pattern-based pricing heuristics for models the catalogue lacks (#1961)."""

    def setup_method(self):
        self.tracker = LLMCostTracker()

    def test_an_unknown_sonnet_variant_is_priced_as_sonnet(self):
        _populate()
        entry = _CATALOGUE[ANTHROPIC_CLAUDE_SONNET4.lower()]
        cost = self.tracker.calculate_cost("claude-sonnet-5-future", 1_000_000, 1_000_000)
        assert cost == round(entry.input_per_1m + entry.output_per_1m, 6)

    def test_an_unknown_opus_variant_is_priced_as_opus_not_as_generic_claude(self):
        """Tier order, which is the property the old opus>haiku assertion protected.

        ``_FALLBACK_PATTERNS`` lists ``claude-opus`` before the bare ``claude``
        catch-all. If that order were lost, an unknown Opus would be billed at
        Sonnet's rate -- 5x under, silently.
        """
        _populate()
        opus = _CATALOGUE[ANTHROPIC_CLAUDE_OPUS4.lower()]
        sonnet = _CATALOGUE[ANTHROPIC_CLAUDE_SONNET4.lower()]
        cost = self.tracker.calculate_cost("claude-opus-5-future", 1_000_000, 0)
        assert cost == round(opus.input_per_1m, 6)
        assert cost != round(sonnet.input_per_1m, 6)

    def test_an_unknown_haiku_variant_is_priced_as_haiku(self):
        _populate()
        entry = _CATALOGUE[ANTHROPIC_CLAUDE_HAIKU4_5.lower()]
        cost = self.tracker.calculate_cost("claude-haiku-9-future", 1_000_000, 0)
        assert cost == round(entry.input_per_1m, 6)

    def test_a_fallback_whose_reference_model_is_absent_does_not_invent_a_price(self):
        """The pattern matches but the catalogue has no Opus -- that is $0, not a guess."""
        _populate({OPENAI_GPT4O.lower(): _CATALOGUE[OPENAI_GPT4O.lower()]})
        assert self.tracker.calculate_cost("claude-opus-5-future", 1_000_000, 1_000_000) == 0.0

    def test_a_fully_unknown_model_returns_zero_and_says_so(self, caplog):
        _populate()
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            cost = self.tracker.calculate_cost("totally-unknown-xyz-model", 100, 100)
        assert cost == 0.0
        assert any("no live catalogue price" in r.message for r in caplog.records)


class TestLocalModelsAreFreeWithoutTheCatalogue:
    """#16316: a local model is free by construction, checked before the cache."""

    def setup_method(self):
        self.tracker = LLMCostTracker()

    @pytest.mark.parametrize("model", sorted(LOCAL_MODEL_NAMES))
    def test_every_local_model_costs_nothing(self, model):
        _populate()
        assert self.tracker.calculate_cost(model, 1_000_000, 1_000_000) == 0.0

    @pytest.mark.parametrize("model", sorted(LOCAL_MODEL_NAMES))
    def test_every_local_model_costs_nothing_with_a_cold_cache(self, model, caplog):
        """The stronger half: absence from the catalogue must not read as unknown.

        The cache is never populated here, so a local model reaching the
        snapshot lookup at all would raise ``PricingCacheCold`` internally and
        take the degraded path. Both paths return 0.0, so the *value* cannot
        tell them apart -- the warning is what distinguishes "free" from
        "could not price it", and there must not be one.
        """
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            assert self.tracker.calculate_cost(model, 1_000_000, 1_000_000) == 0.0
        # Scoped to this module's logger: caplog collects whatever else happens
        # to propagate, and an unrelated warning must not read as a pricing one.
        mine = [r for r in caplog.records if r.name == _LOGGER_NAME]
        assert not mine, f"{model} was priced through the cache, not recognised as local: {mine}"


class TestColdAndStaleCacheDegradeLoudly:
    """The staleness contract, moved off PRICING_VERSION onto the live snapshot.

    ``calculate_cost`` is an analytics figure, not a budget gate, so it degrades
    to $0.00 instead of refusing -- but never silently. ``llc/services/budget.py``
    is the enforcement path and raises ``UnpricedModel`` for the same condition.
    """

    def setup_method(self):
        self.tracker = LLMCostTracker()

    def test_a_cold_cache_prices_at_zero_and_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            cost = self.tracker.calculate_cost(OPENAI_GPT4O, 1_000_000, 1_000_000)
        assert cost == 0.0
        assert any("pricing cache unavailable" in r.message for r in caplog.records)

    def test_a_stale_cache_prices_at_zero_and_warns(self, monkeypatch, caplog):
        """Populated but too old is the same answer as never populated.

        ``PricingCacheStale`` subclasses ``PricingCacheCold`` precisely so this
        caller does not have to distinguish them; this pins that it does not.
        """
        monkeypatch.setattr(sync_cache, "MAX_SNAPSHOT_AGE_S", 10)
        _populate(age_s=11)
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            cost = self.tracker.calculate_cost(OPENAI_GPT4O, 1_000_000, 1_000_000)
        assert cost == 0.0
        assert any("pricing cache unavailable" in r.message for r in caplog.records)

    def test_a_snapshot_inside_the_freshness_bound_still_prices(self, monkeypatch):
        """The contrast, or the two tests above would pass on a cache that never works."""
        monkeypatch.setattr(sync_cache, "MAX_SNAPSHOT_AGE_S", 10)
        _populate(age_s=1)
        entry = _CATALOGUE[OPENAI_GPT4O.lower()]
        cost = self.tracker.calculate_cost(OPENAI_GPT4O, 1_000_000, 1_000_000)
        assert cost == round(entry.input_per_1m + entry.output_per_1m, 6)


class TestScanIterUsage:
    """Verify get_all_user_costs / get_all_agent_costs / _fetch_model_costs use scan_iter
    instead of redis.keys() — Issue #4443."""

    def _make_tracker(self):
        tracker = LLMCostTracker()
        return tracker

    @pytest.mark.asyncio
    async def test_get_all_user_costs_uses_scan_iter(self):
        """get_all_user_costs must iterate via scan_iter, not keys()."""
        tracker = self._make_tracker()
        user_key = b"cost:user_totals:alice"
        pipe = make_redis_pipeline(
            execute_returns=[
                {b"cost_usd": b"1.5", b"input_tokens": b"100", b"output_tokens": b"200", b"call_count": b"3"}
            ]
        )
        redis_mock = make_async_redis(scan_iter_keys=[user_key], pipeline=pipe)
        with patch.object(tracker, "get_redis", AsyncMock(return_value=redis_mock)):
            result = await tracker.get_all_user_costs()

        assert len(result) == 1
        assert result[0]["user_id"] == "alice"
        assert result[0]["cost_usd"] == pytest.approx(1.5)

    @pytest.mark.asyncio
    async def test_get_all_user_costs_excludes_daily_subkeys(self):
        """Keys containing ':daily:' must be filtered out."""
        tracker = self._make_tracker()
        keys = [b"cost:user_totals:alice", b"cost:user_totals:alice:daily:2026-04-15"]
        pipe = make_redis_pipeline(
            execute_returns=[
                {b"cost_usd": b"2.0", b"input_tokens": b"50", b"output_tokens": b"50", b"call_count": b"1"}
            ]
        )
        redis_mock = make_async_redis(scan_iter_keys=keys, pipeline=pipe)
        with patch.object(tracker, "get_redis", AsyncMock(return_value=redis_mock)):
            result = await tracker.get_all_user_costs()

        assert len(result) == 1
        assert result[0]["user_id"] == "alice"

    @pytest.mark.asyncio
    async def test_get_all_user_costs_returns_empty_on_no_keys(self):
        """Returns [] when no matching keys exist."""
        tracker = self._make_tracker()
        redis_mock = make_async_redis(scan_iter_keys=[])
        with patch.object(tracker, "get_redis", AsyncMock(return_value=redis_mock)):
            result = await tracker.get_all_user_costs()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_all_agent_costs_uses_scan_iter(self):
        """get_all_agent_costs must use scan_iter, not keys()."""
        tracker = self._make_tracker()
        agent_key = b"cost:agent_totals:bot1"
        pipe = make_redis_pipeline(
            execute_returns=[
                {b"cost_usd": b"0.75", b"input_tokens": b"80", b"output_tokens": b"120", b"call_count": b"2"}
            ]
        )
        redis_mock = make_async_redis(scan_iter_keys=[agent_key], pipeline=pipe)
        with patch.object(tracker, "get_redis", AsyncMock(return_value=redis_mock)):
            result = await tracker.get_all_agent_costs()

        assert len(result) == 1
        assert result[0]["agent_id"] == "bot1"
        assert result[0]["cost_usd"] == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_fetch_model_costs_uses_scan_iter(self):
        """_fetch_model_costs must use scan_iter, not keys()."""
        tracker = self._make_tracker()
        model_key = b"cost:model_totals:gpt-4o"
        pipe = make_redis_pipeline(
            execute_returns=[
                {b"cost_usd": b"3.0", b"input_tokens": b"200", b"output_tokens": b"300", b"call_count": b"5"}
            ]
        )
        redis_mock = make_async_redis(scan_iter_keys=[model_key], pipeline=pipe)
        result = await tracker._fetch_model_costs(redis_mock)

        assert "gpt-4o" in result
        assert result["gpt-4o"]["cost_usd"] == pytest.approx(3.0)
