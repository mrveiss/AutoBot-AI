# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for reasoning effort → provider parameter mapping (MVA-3028)."""

import importlib.util
import pathlib

import pytest

# Load the real reasoning_effort module directly to bypass the llm_shared stub
# registered in conftest.py, which replaces llm_shared.providers with a MagicMock.
_RE_PATH = pathlib.Path(__file__).parent.parent.parent / "llm_shared" / "providers" / "reasoning_effort.py"
_re_spec = importlib.util.spec_from_file_location("llm_shared.providers.reasoning_effort", str(_RE_PATH))
_re_mod = importlib.util.module_from_spec(_re_spec)
_re_spec.loader.exec_module(_re_mod)
_map_effort_to_provider_params = _re_mod._map_effort_to_provider_params


class TestAutoAndEmptyEffort:
    def test_auto_returns_empty(self):
        assert _map_effort_to_provider_params("auto", "anthropic") == {}

    def test_empty_string_returns_empty(self):
        assert _map_effort_to_provider_params("", "anthropic") == {}

    def test_none_effort_returns_empty(self):
        assert _map_effort_to_provider_params(None, "anthropic") == {}

    def test_auto_openai_returns_empty(self):
        assert _map_effort_to_provider_params("auto", "openai") == {}


class TestAnthropicProvider:
    @pytest.mark.parametrize("provider", ["anthropic", "claude", "Anthropic", "Claude"])
    def test_low_effort(self, provider):
        result = _map_effort_to_provider_params("low", provider)
        assert result == {"thinking_tokens": 2000}

    @pytest.mark.parametrize("provider", ["anthropic", "claude"])
    def test_medium_effort(self, provider):
        result = _map_effort_to_provider_params("medium", provider)
        assert result == {"thinking_tokens": 5000}

    @pytest.mark.parametrize("provider", ["anthropic", "claude"])
    def test_high_effort(self, provider):
        result = _map_effort_to_provider_params("high", provider)
        assert result == {"thinking_tokens": 10000}

    def test_unknown_effort_defaults_to_medium_tokens(self):
        result = _map_effort_to_provider_params("extreme", "anthropic")
        assert result == {"thinking_tokens": 5000}


class TestOpenAIProvider:
    @pytest.mark.parametrize("effort", ["low", "medium", "high"])
    def test_valid_effort_passthrough(self, effort):
        result = _map_effort_to_provider_params(effort, "openai")
        assert result == {"reasoning_effort": effort}

    def test_openai_case_insensitive(self):
        result = _map_effort_to_provider_params("high", "OpenAI")
        assert result == {"reasoning_effort": "high"}

    def test_unknown_effort_returns_empty(self):
        result = _map_effort_to_provider_params("extreme", "openai")
        assert result == {}


class TestBedrockProvider:
    @pytest.mark.parametrize(
        "effort,expected_tokens",
        [("low", 2000), ("medium", 5000), ("high", 10000)],
    )
    def test_effort_maps_to_thinking_tokens(self, effort, expected_tokens):
        result = _map_effort_to_provider_params(effort, "bedrock")
        assert result == {"thinking_tokens": expected_tokens}

    def test_bedrock_case_insensitive(self):
        result = _map_effort_to_provider_params("low", "Bedrock")
        assert result == {"thinking_tokens": 2000}

    def test_unknown_effort_defaults_to_medium_tokens(self):
        result = _map_effort_to_provider_params("unknown", "bedrock")
        assert result == {"thinking_tokens": 5000}


class TestVertexAndGeminiProvider:
    @pytest.mark.parametrize("provider", ["vertex", "vertexai", "gemini", "Gemini"])
    @pytest.mark.parametrize("effort", ["low", "medium", "high"])
    def test_returns_empty_for_all_efforts(self, provider, effort):
        assert _map_effort_to_provider_params(effort, provider) == {}


class TestUnknownProvider:
    def test_unknown_provider_returns_empty(self):
        assert _map_effort_to_provider_params("high", "some-unknown-provider") == {}

    def test_none_provider_returns_empty(self):
        assert _map_effort_to_provider_params("high", None) == {}

    def test_empty_provider_returns_empty(self):
        assert _map_effort_to_provider_params("high", "") == {}
