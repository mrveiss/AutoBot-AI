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

import sys
import textwrap
import types
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

from llm_shared.model_param_registry import (  # noqa: E402
    _FALLBACK_KWARGS,
    _load_registry,
    apply_model_defaults,
    apply_prompt_prefix,
    get_architecture_family,
    get_model_kwargs,
    get_prompt_prefix,
    get_provider_model_id,
    resolve_model_name,
    ArchitectureFamily,
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
        assert kwargs["max_tokens"] == 2000  # overridden by provider

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


# ---------------------------------------------------------------------------
# Tests: get_prompt_prefix (#3263)
# ---------------------------------------------------------------------------


class TestGetPromptPrefix:
    def test_model_with_prefix_returns_string(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            models:
              - display_name: prefixed-model
                api_name:
                  ollama: prefixed-model
                aliases: []
                prompt_prefix: "Think step by step before answering."
                api_kwargs:
                  default:
                    temperature: 0.7
                    max_tokens: 4096
        """)
        yaml_file = tmp_path / "llm_models.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        with patch.dict("os.environ", {"AUTOBOT_LLM_MODELS_YAML": str(yaml_file)}):
            _clear_cache()
            prefix = get_prompt_prefix("prefixed-model")
        assert prefix == "Think step by step before answering."

    def test_model_without_prefix_returns_none(self):
        prefix = get_prompt_prefix("gpt-4o")
        assert prefix is None

    def test_unknown_model_returns_none(self):
        prefix = get_prompt_prefix("totally-unknown-xyz")
        assert prefix is None

    def test_alias_resolved_before_lookup(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            models:
              - display_name: my-model
                api_name:
                  ollama: my-model
                aliases:
                  - my-alias
                prompt_prefix: "Answer concisely."
                api_kwargs:
                  default:
                    temperature: 0.7
                    max_tokens: 2048
        """)
        yaml_file = tmp_path / "llm_models.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        with patch.dict("os.environ", {"AUTOBOT_LLM_MODELS_YAML": str(yaml_file)}):
            _clear_cache()
            prefix = get_prompt_prefix("my-alias")
        assert prefix == "Answer concisely."

    def test_empty_prefix_returns_none(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            models:
              - display_name: empty-prefix-model
                api_name:
                  ollama: empty-prefix-model
                aliases: []
                prompt_prefix: ""
                api_kwargs:
                  default:
                    temperature: 0.7
                    max_tokens: 2048
        """)
        yaml_file = tmp_path / "llm_models.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        with patch.dict("os.environ", {"AUTOBOT_LLM_MODELS_YAML": str(yaml_file)}):
            _clear_cache()
            prefix = get_prompt_prefix("empty-prefix-model")
        assert prefix is None

    def test_deepseek_r1_has_prefix_in_real_yaml(self):
        """deepseek-r1 ships a prompt_prefix in the real llm_models.yaml."""
        prefix = get_prompt_prefix("deepseek-r1")
        assert prefix is not None
        assert len(prefix) > 0


# ---------------------------------------------------------------------------
# Tests: apply_prompt_prefix (#3263)
# ---------------------------------------------------------------------------


class TestApplyPromptPrefix:
    def test_prefix_prepended_to_first_user_message(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            models:
              - display_name: cot-model
                api_name:
                  ollama: cot-model
                aliases: []
                prompt_prefix: "Think carefully."
                api_kwargs:
                  default:
                    temperature: 0.7
                    max_tokens: 2048
        """)
        yaml_file = tmp_path / "llm_models.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        messages = [
            {"role": "system", "content": "You are a helper."},
            {"role": "user", "content": "What is 2+2?"},
        ]
        with patch.dict("os.environ", {"AUTOBOT_LLM_MODELS_YAML": str(yaml_file)}):
            _clear_cache()
            result = apply_prompt_prefix("cot-model", messages)
        assert result[1]["content"] == "Think carefully.\nWhat is 2+2?"
        # system message must be untouched
        assert result[0]["content"] == "You are a helper."

    def test_no_prefix_leaves_messages_unchanged(self):
        messages = [{"role": "user", "content": "Hello"}]
        result = apply_prompt_prefix("gpt-4o", messages)
        assert result[0]["content"] == "Hello"

    def test_returns_same_list_object(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            models:
              - display_name: cot-model2
                api_name:
                  ollama: cot-model2
                aliases: []
                prompt_prefix: "Be precise."
                api_kwargs:
                  default:
                    temperature: 0.7
                    max_tokens: 2048
        """)
        yaml_file = tmp_path / "llm_models.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        messages = [{"role": "user", "content": "Hi"}]
        with patch.dict("os.environ", {"AUTOBOT_LLM_MODELS_YAML": str(yaml_file)}):
            _clear_cache()
            result = apply_prompt_prefix("cot-model2", messages)
        assert result is messages

    def test_only_first_user_message_modified(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            models:
              - display_name: multi-turn-model
                api_name:
                  ollama: multi-turn-model
                aliases: []
                prompt_prefix: "Step by step:"
                api_kwargs:
                  default:
                    temperature: 0.7
                    max_tokens: 2048
        """)
        yaml_file = tmp_path / "llm_models.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        messages = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "Answer"},
            {"role": "user", "content": "Second question"},
        ]
        with patch.dict("os.environ", {"AUTOBOT_LLM_MODELS_YAML": str(yaml_file)}):
            _clear_cache()
            apply_prompt_prefix("multi-turn-model", messages)
        assert messages[0]["content"] == "Step by step:\nFirst question"
        assert messages[2]["content"] == "Second question"

    def test_no_user_message_leaves_list_unchanged(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            models:
              - display_name: system-only-model
                api_name:
                  ollama: system-only-model
                aliases: []
                prompt_prefix: "Prefix here."
                api_kwargs:
                  default:
                    temperature: 0.7
                    max_tokens: 2048
        """)
        yaml_file = tmp_path / "llm_models.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        messages = [{"role": "system", "content": "Only a system message"}]
        with patch.dict("os.environ", {"AUTOBOT_LLM_MODELS_YAML": str(yaml_file)}):
            _clear_cache()
            result = apply_prompt_prefix("system-only-model", messages)
        assert result[0]["content"] == "Only a system message"


# ---------------------------------------------------------------------------
# Tests: get_architecture_family (GH#7347)
# ---------------------------------------------------------------------------


class TestGetArchitectureFamily:
    def test_known_yaml_model_returns_transformer(self):
        assert get_architecture_family("claude-sonnet-4-6") == ArchitectureFamily.TRANSFORMER

    def test_gpt4o_returns_transformer(self):
        assert get_architecture_family("gpt-4o") == ArchitectureFamily.TRANSFORMER

    def test_ollama_model_returns_transformer(self):
        assert get_architecture_family("llama3.3") == ArchitectureFamily.TRANSFORMER

    def test_model_card_mamba_returns_ssm(self):
        fam = get_architecture_family("unknown-local", model_card_config={"model_type": "mamba"})
        assert fam == ArchitectureFamily.SSM

    def test_model_card_mamba2_returns_ssm(self):
        fam = get_architecture_family("some-model", model_card_config={"model_type": "mamba2"})
        assert fam == ArchitectureFamily.SSM

    def test_model_card_mixtral_returns_moe(self):
        fam = get_architecture_family("some-model", model_card_config={"model_type": "mixtral"})
        assert fam == ArchitectureFamily.MOE

    def test_pattern_match_mamba_name_returns_ssm(self):
        fam = get_architecture_family("mamba-3b-local")
        assert fam == ArchitectureFamily.SSM

    def test_pattern_match_emits_warning(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            get_architecture_family("mamba-unknown-7b")
        assert "architecture_family" in caplog.text
        assert "pattern" in caplog.text

    def test_unknown_model_no_config_defaults_transformer(self):
        fam = get_architecture_family("totally-unknown-xyz-model")
        assert fam == ArchitectureFamily.TRANSFORMER

    def test_alias_resolved_before_lookup(self):
        fam = get_architecture_family("gpt4o")
        assert fam == ArchitectureFamily.TRANSFORMER

    def test_explicit_yaml_field_wins_over_config(self, tmp_path):
        import textwrap
        from unittest.mock import patch

        yaml_content = textwrap.dedent("""\
            models:
              - display_name: my-ssm-model
                architecture_family: ssm
                api_name:
                  ollama: my-ssm-model
                aliases: []
                api_kwargs:
                  default:
                    temperature: 0.7
                    max_tokens: 2048
        """)
        yaml_file = tmp_path / "llm_models.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        with patch.dict("os.environ", {"AUTOBOT_LLM_MODELS_YAML": str(yaml_file)}):
            _clear_cache()
            # config.json says transformer but YAML says ssm — YAML wins
            fam = get_architecture_family(
                "my-ssm-model",
                model_card_config={"model_type": "llama"},
            )
        assert fam == ArchitectureFamily.SSM
