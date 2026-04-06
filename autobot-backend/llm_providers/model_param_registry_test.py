# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for the YAML-driven per-model parameter registry (#3257).

Fully offline — no real LLM calls.  The YAML file on disk is used directly
(Path.__file__-relative) but ``_load_registry.cache_clear()`` is called
between tests so each test starts with a cold cache.
"""

from __future__ import annotations

import textwrap
import types
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Minimal stubs so the module imports cleanly outside the full runtime.
# (mirrors the pattern in anthropic_provider_test.py)
# ---------------------------------------------------------------------------


def _stub_module(name: str, **attrs) -> types.ModuleType:
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


if "xxhash" not in sys.modules:
    from unittest.mock import MagicMock
    _stub_module(
        "xxhash",
        xxh64=MagicMock(return_value=MagicMock(hexdigest=MagicMock(return_value="0" * 16))),
    )

# ---------------------------------------------------------------------------
# Now safe to import the registry
# ---------------------------------------------------------------------------

from llm_providers.model_param_registry import (  # noqa: E402
    _FALLBACK_KWARGS,
    _load_registry,
    apply_model_defaults,
    get_model_kwargs,
    get_provider_model_id,
    resolve_model_name,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clear_cache() -> None:
    """Clear the lru_cache so each test loads fresh."""
    _load_registry.cache_clear()


@pytest.fixture(autouse=True)
def clear_registry_cache():
    """Automatically clear the registry LRU cache before every test."""
    _clear_cache()
    yield
    _clear_cache()


# ---------------------------------------------------------------------------
# Tests: resolve_model_name
# ---------------------------------------------------------------------------


class TestResolveModelName:
    def test_canonical_name_returned_unchanged(self):
        result = resolve_model_name("gpt-4o")
        assert result == "gpt-4o"

    def test_alias_resolves_to_display_name(self):
        result = resolve_model_name("gpt4o")
        assert result == "gpt-4o"

    def test_unknown_name_returned_unchanged(self):
        result = resolve_model_name("some-unknown-model-xyz")
        assert result == "some-unknown-model-xyz"

    def test_anthropic_alias(self):
        result = resolve_model_name("claude-sonnet")
        assert result == "claude-3-5-sonnet-20241022"

    def test_ollama_tag_alias(self):
        result = resolve_model_name("llama3.3:latest")
        assert result == "llama3.3"


# ---------------------------------------------------------------------------
# Tests: get_model_kwargs
# ---------------------------------------------------------------------------


class TestGetModelKwargs:
    def test_known_model_returns_yaml_defaults(self):
        kwargs = get_model_kwargs("gpt-4o")
        assert kwargs["temperature"] == 1
        assert kwargs["max_tokens"] == 4096

    def test_alias_resolved_before_lookup(self):
        kwargs_alias = get_model_kwargs("gpt4o")
        kwargs_canonical = get_model_kwargs("gpt-4o")
        assert kwargs_alias == kwargs_canonical

    def test_unknown_model_returns_fallback(self):
        kwargs = get_model_kwargs("totally-unknown-model")
        assert kwargs == dict(_FALLBACK_KWARGS)

    def test_provider_specific_override_applied(self, tmp_path):
        """Provider-specific api_kwargs override the default block."""
        yaml_content = textwrap.dedent("""\
            models:
              - display_name: test-model
                api_name:
                  myprovider: test-model
                aliases: []
                api_kwargs:
                  default:
                    temperature: 0.5
                    max_tokens: 1000
                  myprovider:
                    max_tokens: 2000
        """)
        yaml_file = tmp_path / "llm_models.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        with patch.dict("os.environ", {"AUTOBOT_LLM_MODELS_YAML": str(yaml_file)}):
            _clear_cache()
            kwargs = get_model_kwargs("test-model", provider="myprovider")
        assert kwargs["temperature"] == 0.5  # from default
        assert kwargs["max_tokens"] == 2000   # overridden by provider

    def test_returned_dict_is_copy(self):
        """Mutating the returned dict must not affect subsequent calls."""
        kwargs1 = get_model_kwargs("gpt-4o")
        kwargs1["extra"] = "injected"
        kwargs2 = get_model_kwargs("gpt-4o")
        assert "extra" not in kwargs2

    def test_coding_model_has_low_temperature(self):
        kwargs = get_model_kwargs("codellama")
        assert kwargs["temperature"] == 0.2

    def test_anthropic_claude_has_temperature_one(self):
        kwargs = get_model_kwargs("claude-sonnet-4-6")
        assert kwargs["temperature"] == 1

    def test_reasoning_model_has_no_temperature(self):
        """o1/o3 models must not receive temperature — the OpenAI API rejects it."""
        kwargs = get_model_kwargs("o1")
        assert "temperature" not in kwargs
        assert kwargs["max_tokens"] == 32768


# ---------------------------------------------------------------------------
# Tests: get_provider_model_id
# ---------------------------------------------------------------------------


class TestGetProviderModelId:
    def test_known_model_and_provider(self):
        result = get_provider_model_id("gpt-4o", "openai")
        assert result == "gpt-4o"

    def test_alias_resolved(self):
        result = get_provider_model_id("gpt4o", "openai")
        assert result == "gpt-4o"

    def test_provider_not_in_api_name_returns_canonical(self):
        result = get_provider_model_id("gpt-4o", "unknown_provider")
        assert result == "gpt-4o"

    def test_unknown_model_returns_input_unchanged(self):
        result = get_provider_model_id("my-custom-model", "ollama")
        assert result == "my-custom-model"

    def test_anthropic_model(self):
        result = get_provider_model_id("claude-sonnet-4-6", "anthropic")
        assert result == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Tests: apply_model_defaults
# ---------------------------------------------------------------------------


class TestApplyModelDefaults:
    def test_caller_kwargs_win_over_yaml(self):
        merged = apply_model_defaults(
            "gpt-4o",
            provider="openai",
            caller_kwargs={"max_tokens": 100, "temperature": 0.1},
        )
        assert merged["max_tokens"] == 100
        assert merged["temperature"] == 0.1

    def test_no_caller_kwargs_uses_yaml(self):
        merged = apply_model_defaults("gpt-4o", provider="openai")
        assert merged["temperature"] == 1
        assert merged["max_tokens"] == 4096

    def test_partial_caller_override(self):
        merged = apply_model_defaults(
            "gpt-4o",
            provider="openai",
            caller_kwargs={"max_tokens": 512},
        )
        assert merged["max_tokens"] == 512
        assert merged["temperature"] == 1  # still from YAML

    def test_none_provider_uses_default_block(self):
        merged = apply_model_defaults("gpt-4o", provider=None)
        assert merged["temperature"] == 1

    def test_unknown_model_uses_fallback(self):
        merged = apply_model_defaults("unknown-model-xyz", provider=None)
        assert merged == dict(_FALLBACK_KWARGS)


# ---------------------------------------------------------------------------
# Tests: missing / malformed YAML
# ---------------------------------------------------------------------------


class TestMissingYaml:
    def test_missing_yaml_returns_fallback(self, tmp_path):
        yaml_file = tmp_path / "nonexistent.yaml"
        with patch.dict("os.environ", {"AUTOBOT_LLM_MODELS_YAML": str(yaml_file)}):
            _clear_cache()
            kwargs = get_model_kwargs("gpt-4o")
        assert kwargs == dict(_FALLBACK_KWARGS)

    def test_empty_models_section_returns_fallback(self, tmp_path):
        yaml_file = tmp_path / "llm_models.yaml"
        yaml_file.write_text("models: []\n", encoding="utf-8")
        with patch.dict("os.environ", {"AUTOBOT_LLM_MODELS_YAML": str(yaml_file)}):
            _clear_cache()
            kwargs = get_model_kwargs("gpt-4o")
        assert kwargs == dict(_FALLBACK_KWARGS)
