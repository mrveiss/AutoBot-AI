# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for LLM cost tracker pricing. Issue #1961."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from constants.model_constants import (
    ANTHROPIC_CLAUDE35_SONNET,
    ANTHROPIC_CLAUDE_HAIKU4_5,
    ANTHROPIC_CLAUDE_OPUS4,
    ANTHROPIC_CLAUDE_SONNET4,
    GOOGLE_GEMINI20_FLASH,
    GOOGLE_GEMINI25_FLASH,
    GOOGLE_GEMINI25_PRO,
    LOCAL_CODELLAMA,
    LOCAL_DEEPSEEK_CODER,
    LOCAL_DEEPSEEK_R1,
    LOCAL_GEMMA2,
    LOCAL_GEMMA3,
    LOCAL_LLAMA3,
    LOCAL_LLAMA31,
    LOCAL_LLAMA32,
    LOCAL_LLAMA33,
    LOCAL_MISTRAL,
    LOCAL_MIXTRAL,
    LOCAL_PHI3,
    LOCAL_PHI4,
    LOCAL_QWEN3,
    LOCAL_QWEN25,
    OPENAI_GPT4_TURBO,
    OPENAI_GPT4O,
    OPENAI_GPT41,
    OPENAI_GPT41_MINI,
    OPENAI_GPT41_NANO,
    OPENAI_O3,
    OPENAI_O3_MINI,
    OPENAI_O4_MINI,
)
from services.llm_cost_tracker import (
    MODEL_PRICING,
    PRICING_STALENESS_DAYS,
    PRICING_VERSION,
    LLMCostTracker,
    _check_pricing_staleness,
)
from tests.fixtures.mocks import make_async_redis, make_redis_pipeline


class TestModelPricingCompleteness:
    """Verify MODEL_PRICING covers all required 2025-2026 models."""

    REQUIRED_MODELS = [
        # Anthropic Claude 4.x
        ANTHROPIC_CLAUDE_OPUS4,
        ANTHROPIC_CLAUDE_SONNET4,
        ANTHROPIC_CLAUDE_HAIKU4_5,
        # OpenAI GPT-4.1 family
        OPENAI_GPT41,
        OPENAI_GPT41_MINI,
        OPENAI_GPT41_NANO,
        # OpenAI reasoning
        OPENAI_O3,
        OPENAI_O3_MINI,
        OPENAI_O4_MINI,
        # Google Gemini 2.5
        GOOGLE_GEMINI25_PRO,
        GOOGLE_GEMINI25_FLASH,
        # Existing baseline models
        OPENAI_GPT4O,
        ANTHROPIC_CLAUDE35_SONNET,
        GOOGLE_GEMINI20_FLASH,
    ]

    LOCAL_MODELS = [
        LOCAL_LLAMA3,
        LOCAL_LLAMA31,
        LOCAL_LLAMA32,
        LOCAL_LLAMA33,
        LOCAL_MISTRAL,
        LOCAL_MIXTRAL,
        LOCAL_CODELLAMA,
        LOCAL_QWEN25,
        LOCAL_QWEN3,
        LOCAL_DEEPSEEK_CODER,
        LOCAL_DEEPSEEK_R1,
        LOCAL_PHI3,
        LOCAL_PHI4,
        LOCAL_GEMMA2,
        LOCAL_GEMMA3,
    ]

    @pytest.mark.parametrize("model", REQUIRED_MODELS)
    def test_model_has_pricing(self, model):
        """Every required model must have an entry in MODEL_PRICING."""
        assert model in MODEL_PRICING, f"Missing pricing for {model}"

    @pytest.mark.parametrize("model", REQUIRED_MODELS)
    def test_pricing_has_input_and_output(self, model):
        """Each pricing entry must contain both input and output keys."""
        if model in MODEL_PRICING:
            assert "input" in MODEL_PRICING[model], f"{model} missing 'input' key"
            assert "output" in MODEL_PRICING[model], f"{model} missing 'output' key"

    def test_no_negative_prices(self):
        """No model should have a negative price."""
        for model, pricing in MODEL_PRICING.items():
            assert pricing["input"] >= 0, f"{model} has negative input price"
            assert pricing["output"] >= 0, f"{model} has negative output price"

    @pytest.mark.parametrize("model", LOCAL_MODELS)
    def test_local_models_are_free(self, model):
        """All local/Ollama models must be priced at $0."""
        if model in MODEL_PRICING:
            assert MODEL_PRICING[model]["input"] == 0.0, f"{model} local model should have input price 0.0"
            assert MODEL_PRICING[model]["output"] == 0.0, f"{model} local model should have output price 0.0"

    def test_paid_models_have_positive_output_price(self):
        """Cloud API models must have a positive output price."""
        cloud_prefixes = ("claude-", "gpt-", "o1", "o3", "gemini-")
        for model, pricing in MODEL_PRICING.items():
            if model.startswith(cloud_prefixes):
                assert pricing["output"] > 0, f"Cloud model {model} should have positive output price"

    def test_claude_opus_4_more_expensive_than_haiku(self):
        """Opus tier should cost more than Haiku tier."""
        opus = MODEL_PRICING[ANTHROPIC_CLAUDE_OPUS4]["output"]
        haiku = MODEL_PRICING[ANTHROPIC_CLAUDE_HAIKU4_5]["output"]
        assert opus > haiku, "Claude Opus 4 output should cost more than Haiku 4.5"

    def test_gpt41_cheaper_than_gpt4_turbo(self):
        """GPT-4.1 should be cheaper than GPT-4-turbo."""
        gpt41 = MODEL_PRICING[OPENAI_GPT41]["input"]
        turbo = MODEL_PRICING[OPENAI_GPT4_TURBO]["input"]
        assert gpt41 < turbo, "GPT-4.1 input should cost less than GPT-4-turbo"

    def test_o3_more_expensive_than_o3_mini(self):
        """o3 reasoning should cost more than o3-mini."""
        o3 = MODEL_PRICING[OPENAI_O3]["input"]
        o3_mini = MODEL_PRICING[OPENAI_O3_MINI]["input"]
        assert o3 >= o3_mini, "o3 input should cost at least as much as o3-mini"

    def test_deepseek_api_models_have_positive_price(self):
        """DeepSeek hosted API models should have a positive price."""
        from constants.model_constants import DEEPSEEK_R1_API, DEEPSEEK_V3

        for model in (DEEPSEEK_V3, DEEPSEEK_R1_API):
            assert MODEL_PRICING[model]["input"] > 0, f"{model} should have positive input price"
            assert MODEL_PRICING[model]["output"] > 0, f"{model} should have positive output price"

    def test_pricing_version_is_valid_iso_date(self):
        """PRICING_VERSION must be a valid ISO date string."""
        try:
            date.fromisoformat(PRICING_VERSION)
        except ValueError:
            pytest.fail(f"PRICING_VERSION {PRICING_VERSION!r} is not a valid ISO date")


class TestPricingStaleness:
    """Verify the staleness detection logic. Issue #1961."""

    def test_fresh_pricing_emits_no_warning(self, caplog):
        """No warning when pricing was updated today."""
        today = date.today().isoformat()
        with patch("services.llm_cost_tracker.PRICING_VERSION", today):
            import logging

            with caplog.at_level(logging.WARNING, logger="services.llm_cost_tracker"):
                _check_pricing_staleness()
        assert not any("days old" in r.message for r in caplog.records)

    def test_stale_pricing_emits_warning(self, caplog):
        """A WARNING must be emitted when the pricing table is past the threshold."""
        stale_date = (date.today() - timedelta(days=PRICING_STALENESS_DAYS + 1)).isoformat()
        with patch("services.llm_cost_tracker.PRICING_VERSION", stale_date):
            import logging

            with caplog.at_level(logging.WARNING, logger="services.llm_cost_tracker"):
                _check_pricing_staleness()
        assert any("days old" in r.message for r in caplog.records)

    def test_invalid_pricing_version_emits_warning(self, caplog):
        """An invalid PRICING_VERSION string must emit a WARNING."""
        with patch("services.llm_cost_tracker.PRICING_VERSION", "not-a-date"):
            import logging

            with caplog.at_level(logging.WARNING, logger="services.llm_cost_tracker"):
                _check_pricing_staleness()
        assert any("valid ISO date" in r.message for r in caplog.records)


class TestUnknownModelFallback:
    """Verify pattern-based pricing heuristics for unknown models. Issue #1961."""

    def setup_method(self):
        self.tracker = LLMCostTracker()

    def test_unknown_claude_sonnet_variant_uses_sonnet_pricing(self):
        """An unrecognised claude-sonnet-X model should be priced like claude-sonnet."""
        cost = self.tracker.calculate_cost("claude-sonnet-5-future", 1_000_000, 1_000_000)
        expected_input = MODEL_PRICING["claude-sonnet-4-20250514"]["input"]
        expected_output = MODEL_PRICING["claude-sonnet-4-20250514"]["output"]
        assert cost == round(expected_input + expected_output, 6)

    def test_unknown_claude_opus_variant_uses_opus_pricing(self):
        """An unrecognised claude-opus-X model should use opus-tier pricing."""
        cost = self.tracker.calculate_cost("claude-opus-5-future", 1_000_000, 1_000_000)
        expected_input = MODEL_PRICING["claude-opus-4-20250514"]["input"]
        expected_output = MODEL_PRICING["claude-opus-4-20250514"]["output"]
        assert cost == round(expected_input + expected_output, 6)

    def test_unknown_gpt41_variant_uses_gpt41_pricing(self):
        """An unrecognised gpt-4.1-X model should be resolved via substring match."""
        # "gpt-4.1-preview" contains "gpt-4.1" so it will match the known key.
        cost = self.tracker.calculate_cost("gpt-4.1-preview", 1_000_000, 1_000_000)
        expected_input = MODEL_PRICING["gpt-4.1"]["input"]
        expected_output = MODEL_PRICING["gpt-4.1"]["output"]
        assert cost == round(expected_input + expected_output, 6)

    def test_fully_unknown_model_returns_zero(self, caplog):
        """A model with no name-pattern match must return 0.0 and log a warning."""
        import logging

        with caplog.at_level(logging.WARNING, logger="services.llm_cost_tracker"):
            cost = self.tracker.calculate_cost("totally-unknown-xyz-model", 100, 100)
        assert cost == 0.0
        assert any("no pricing entry" in r.message for r in caplog.records)

    def test_known_model_does_not_use_fallback(self):
        """An exactly-known model must use its own pricing, not the fallback."""
        exact_pricing = MODEL_PRICING["gpt-4o"]
        cost = self.tracker.calculate_cost("gpt-4o", 1_000_000, 1_000_000)
        expected = round(exact_pricing["input"] + exact_pricing["output"], 6)
        assert cost == expected


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
