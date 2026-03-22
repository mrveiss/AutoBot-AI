# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for LLM cost tracker pricing. Issue #1961."""

import pytest
from services.llm_cost_tracker import MODEL_PRICING


class TestModelPricingCompleteness:
    """Verify MODEL_PRICING covers all required 2025-2026 models."""

    REQUIRED_MODELS = [
        # Anthropic Claude 4.x
        "claude-opus-4-20250514",
        "claude-sonnet-4-20250514",
        "claude-haiku-4-5-20251001",
        # OpenAI GPT-4.1 family
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        # OpenAI reasoning
        "o3-mini",
        # Google Gemini 2.5
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        # Existing baseline models
        "gpt-4o",
        "claude-3-5-sonnet-20241022",
        "gemini-2.0-flash",
    ]

    LOCAL_MODELS = [
        "llama3",
        "llama3.1",
        "llama3.2",
        "llama3.3",
        "mistral",
        "mixtral",
        "codellama",
        "qwen2.5",
        "qwen3",
        "deepseek-coder",
        "deepseek-r1",
        "phi3",
        "phi4",
        "gemma2",
        "gemma3",
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
            assert (
                MODEL_PRICING[model]["input"] == 0.0
            ), f"{model} local model should have input price 0.0"
            assert (
                MODEL_PRICING[model]["output"] == 0.0
            ), f"{model} local model should have output price 0.0"

    def test_paid_models_have_positive_output_price(self):
        """Cloud API models must have a positive output price."""
        cloud_prefixes = ("claude-", "gpt-", "o1", "o3", "gemini-")
        for model, pricing in MODEL_PRICING.items():
            if model.startswith(cloud_prefixes):
                assert (
                    pricing["output"] > 0
                ), f"Cloud model {model} should have positive output price"

    def test_claude_opus_4_more_expensive_than_haiku(self):
        """Opus tier should cost more than Haiku tier."""
        opus = MODEL_PRICING["claude-opus-4-20250514"]["output"]
        haiku = MODEL_PRICING["claude-haiku-4-5-20251001"]["output"]
        assert opus > haiku, "Claude Opus 4 output should cost more than Haiku 4.5"

    def test_gpt41_cheaper_than_gpt4_turbo(self):
        """GPT-4.1 should be cheaper than GPT-4-turbo."""
        gpt41 = MODEL_PRICING["gpt-4.1"]["input"]
        turbo = MODEL_PRICING["gpt-4-turbo"]["input"]
        assert gpt41 < turbo, "GPT-4.1 input should cost less than GPT-4-turbo"
