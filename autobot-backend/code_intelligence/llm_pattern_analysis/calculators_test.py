# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cost projection reads the live catalogue, not a frozen import (#16230).

`TokenTracker.DEFAULT_COSTS` and `CostCalculator.MODEL_PRICING` were class
attributes bound to `MODEL_PRICING_PER_1K_TOKENS` when this module was first
imported. A price that changed in Redis afterwards could not reach either of
them without a process restart — and nothing said so, because the projection
still produced a confident number.

These tests pin the two halves of the fix that a reading of the diff cannot
prove: that a price change is *observed* between two calls in the same process,
and that a cold cache degrades to the documented estimate rate with a warning
rather than to silence or to a crash.
"""

from __future__ import annotations

import logging
import time

import pytest

from code_intelligence.llm_pattern_analysis.calculators import (
    _NON_MODEL_RATES_PER_1K,
    CostCalculator,
    TokenTracker,
    live_pricing_per_1k,
)
from code_intelligence.llm_pattern_analysis.data_models import UsagePattern
from code_intelligence.llm_pattern_analysis.types import UsagePatternType
from llm_shared.pricing import sync_cache
from llm_shared.pricing.sources import ModelPricing

_LOGGER_NAME = "code_intelligence.llm_pattern_analysis.calculators"


@pytest.fixture(autouse=True)
def _cold_cache():
    sync_cache._reset_for_tests()
    yield
    sync_cache._reset_for_tests()


def _populate(prices: dict[str, ModelPricing], age_s: float = 0.0) -> None:
    sync_cache._snapshot = sync_cache._Snapshot(prices=prices, fetched_at=time.monotonic() - age_s)


def _catalogue(input_per_1m: float, output_per_1m: float) -> dict[str, ModelPricing]:
    return {
        "gpt-4": ModelPricing(
            provider="openai",
            model_id="gpt-4",
            input_per_1m=input_per_1m,
            output_per_1m=output_per_1m,
        )
    }


# --- the unit conversion ---------------------------------------------------


def test_per_1m_catalogue_prices_are_exposed_per_1k():
    """The catalogue is per 1M; both consumers here divide by 1000."""
    _populate(_catalogue(30.0, 60.0))
    rates = live_pricing_per_1k()
    assert rates["gpt-4"] == {"prompt": 0.03, "completion": 0.06}


def test_the_input_output_keys_are_renamed_to_prompt_completion():
    """`ModelPricing` says input/output; every consumer here says prompt/completion."""
    _populate(_catalogue(30.0, 60.0))
    assert set(live_pricing_per_1k()["gpt-4"]) == {"prompt", "completion"}


# --- the actual defect: a frozen binding -----------------------------------


def test_a_price_change_is_visible_without_reimporting():
    """The whole point of #16230, and what a class attribute could not do."""
    tracker = TokenTracker()

    _populate(_catalogue(30.0, 60.0))
    before = tracker.track_usage("gpt-4", 1000, 1000).estimated_cost_usd

    _populate(_catalogue(60.0, 120.0))
    after = tracker.track_usage("gpt-4", 1000, 1000).estimated_cost_usd

    assert after == pytest.approx(before * 2), (
        "the doubled catalogue price did not reach the projection — the rates are bound "
        "somewhere at import time again"
    )


def test_cost_calculator_also_sees_the_change():
    """`CostCalculator`'s methods are classmethods; its binding was separate."""
    pattern = UsagePattern(
        pattern_id="p1",
        pattern_type=UsagePatternType.CODE_GENERATION,
        file_path="x.py",
        line_number=1,
        code_snippet="llm.call()",
        model_used="gpt-4",
    )

    _populate(_catalogue(30.0, 60.0))
    before = CostCalculator.estimate_costs([pattern])[0].daily_cost_usd

    _populate(_catalogue(60.0, 120.0))
    after = CostCalculator.estimate_costs([pattern])[0].daily_cost_usd

    assert after == pytest.approx(before * 2)


# --- degradation -----------------------------------------------------------


def test_a_cold_cache_leaves_only_the_two_non_model_rates_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        rates = live_pricing_per_1k()
    assert rates == _NON_MODEL_RATES_PER_1K
    assert any("pricing cache unavailable" in r.message for r in caplog.records)


def test_a_stale_cache_degrades_the_same_way(monkeypatch, caplog):
    """`PricingCacheStale` subclasses `PricingCacheCold`; this caller must not care."""
    monkeypatch.setattr(sync_cache, "MAX_SNAPSHOT_AGE_S", 10)
    _populate(_catalogue(30.0, 60.0), age_s=11)
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        rates = live_pricing_per_1k()
    assert "gpt-4" not in rates
    assert any("pricing cache unavailable" in r.message for r in caplog.records)


def test_a_fresh_cache_does_not_warn(caplog):
    """The contrast — without it the two tests above pass on a cache that never works."""
    _populate(_catalogue(30.0, 60.0))
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        rates = live_pricing_per_1k()
    assert "gpt-4" in rates
    assert not [r for r in caplog.records if r.name == _LOGGER_NAME]


def test_an_unknown_model_still_costs_something_with_a_cold_cache():
    """#15860's rule on the projection surface: unknown must not read as free."""
    assert TokenTracker().track_usage("some-model-nobody-priced", 1000, 1000).estimated_cost_usd > 0


def test_a_catalogue_cannot_shadow_the_default_fallback():
    """A vendor publishing a model literally called "default" must not become the fallback."""
    _populate(
        {"default": ModelPricing(provider="mischief", model_id="default", input_per_1m=999.0, output_per_1m=999.0)}
    )
    assert live_pricing_per_1k()["default"] == _NON_MODEL_RATES_PER_1K["default"]
