# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for context_window_manager — architecture-family-aware cap bypass.

Issue #7351: non-transformer models must not be compressed at the 4K/8K cap.
"""

from unittest.mock import patch

import pytest

from context_window_manager import _NON_TRANSFORMER_FAMILIES, ContextWindowManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TRANSFORMER_CONFIG = {
    "models": {
        "default": {
            "name": "llama3",
            "context_window_tokens": 4096,
            "max_output_tokens": 2048,
            "message_budget": {
                "system_prompt": 500,
                "recent_messages": 20,
                "max_history_tokens": 3000,
            },
        },
        "llama3": {
            "context_window_tokens": 4096,
            "max_output_tokens": 2048,
            "message_budget": {
                "system_prompt": 500,
                "recent_messages": 20,
                "max_history_tokens": 3000,
            },
        },
        "mamba-3b": {
            "architecture_family": "state_space",
            "context_window_tokens": 131072,
            "max_output_tokens": 4096,
            "message_budget": {
                "system_prompt": 500,
                "recent_messages": 50,
                "max_history_tokens": 100000,
            },
        },
        "mamba2-7b": {
            "architecture_family": "ssm",
            "context_window_tokens": 131072,
            "max_output_tokens": 4096,
            "message_budget": {
                "system_prompt": 500,
                "recent_messages": 50,
                "max_history_tokens": 100000,
            },
        },
        "jamba-7b": {
            "architecture_family": "hybrid",
            "context_window_tokens": 256000,
            "max_output_tokens": 8192,
            "message_budget": {
                "system_prompt": 500,
                "recent_messages": 100,
                "max_history_tokens": 200000,
            },
        },
        "linear-attn-2b": {
            "architecture_family": "linear_attention",
            "context_window_tokens": 65536,
            "max_output_tokens": 2048,
            "message_budget": {
                "system_prompt": 500,
                "recent_messages": 50,
                "max_history_tokens": 50000,
            },
        },
    },
    "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},
}


def _manager_with_config(config: dict) -> ContextWindowManager:
    """Return a ContextWindowManager with an injected config (no YAML load)."""
    mgr = object.__new__(ContextWindowManager)
    mgr.config = config
    mgr.current_model = config["models"]["default"]["name"]
    return mgr


# ---------------------------------------------------------------------------
# _NON_TRANSFORMER_FAMILIES constant
# ---------------------------------------------------------------------------


class TestNonTransformerFamilies:
    def test_contains_expected_families(self):
        assert "state_space" in _NON_TRANSFORMER_FAMILIES
        assert "linear_attention" in _NON_TRANSFORMER_FAMILIES
        assert "hybrid" in _NON_TRANSFORMER_FAMILIES

    def test_transformer_not_in_set(self):
        assert "transformer" not in _NON_TRANSFORMER_FAMILIES


# ---------------------------------------------------------------------------
# get_architecture_family
# ---------------------------------------------------------------------------


class TestGetArchitectureFamily:
    def test_default_is_transformer(self):
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        assert mgr.get_architecture_family("llama3") == "transformer"

    def test_state_space_returned(self):
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        assert mgr.get_architecture_family("mamba-3b") == "state_space"

    def test_hybrid_returned(self):
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        assert mgr.get_architecture_family("jamba-7b") == "hybrid"

    def test_linear_attention_returned(self):
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        assert mgr.get_architecture_family("linear-attn-2b") == "linear_attention"

    def test_unknown_model_returns_transformer(self):
        """Unknown model falls back to default entry which has no family → 'transformer'."""
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        assert mgr.get_architecture_family("nonexistent-model") == "transformer"

    def test_uses_current_model_when_none(self):
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        mgr.current_model = "mamba-3b"
        assert mgr.get_architecture_family() == "state_space"


# ---------------------------------------------------------------------------
# get_compression_threshold — transformer caps unchanged
# ---------------------------------------------------------------------------


class TestGetCompressionThresholdTransformer:
    def test_transformer_returns_8192_default(self):
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        assert mgr.get_compression_threshold("llama3") == 8192

    def test_transformer_respects_explicit_compression_threshold(self):
        config = {
            "models": {
                "default": {
                    "name": "model-a",
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
                "model-a": {
                    "compression_threshold": 16384,
                    "context_window_tokens": 32768,
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
            },
            "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},
        }
        mgr = _manager_with_config(config)
        assert mgr.get_compression_threshold("model-a") == 16384


# ---------------------------------------------------------------------------
# get_compression_threshold — non-transformer bypass
# ---------------------------------------------------------------------------


class TestGetCompressionThresholdNonTransformer:
    def test_state_space_uses_context_window(self):
        """State-space model's threshold must equal its declared context_window_tokens."""
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        assert mgr.get_compression_threshold("mamba-3b") == 131072

    def test_hybrid_uses_context_window(self):
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        assert mgr.get_compression_threshold("jamba-7b") == 256000

    def test_linear_attention_uses_context_window(self):
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        assert mgr.get_compression_threshold("linear-attn-2b") == 65536

    def test_state_space_not_capped_at_8192(self):
        """131072-token SSM must not receive the transformer 8192 cap."""
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        threshold = mgr.get_compression_threshold("mamba-3b")
        assert threshold > 8192, f"SSM threshold {threshold} should exceed 8192"

    def test_non_transformer_fallback_when_no_context_window(self):
        """If context_window_tokens absent on a non-transformer, fall back to 8192."""
        config = {
            "models": {
                "default": {
                    "name": "ssm",
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
                "ssm": {
                    "architecture_family": "state_space",
                    # no context_window_tokens
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
            },
            "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},
        }
        mgr = _manager_with_config(config)
        assert mgr.get_compression_threshold("ssm") == 8192


# ---------------------------------------------------------------------------
# async_should_compress
# ---------------------------------------------------------------------------


class TestAsyncShouldCompress:
    @pytest.mark.asyncio
    async def test_non_transformer_always_returns_false(self):
        """Non-transformer models must never trigger compression."""
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        result = await mgr.async_should_compress(200000, "mamba-3b")
        assert result is False

    @pytest.mark.asyncio
    async def test_hybrid_always_returns_false(self):
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        result = await mgr.async_should_compress(999999, "jamba-7b")
        assert result is False

    @pytest.mark.asyncio
    async def test_linear_attention_always_returns_false(self):
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        result = await mgr.async_should_compress(500000, "linear-attn-2b")
        assert result is False


# ---------------------------------------------------------------------------
# Regression: #8359 explicit compression_threshold overrides family heuristic
# ---------------------------------------------------------------------------


class TestCompressionThresholdExplicitOverride:
    def test_non_transformer_explicit_override_respected(self):
        """Issue #8359: explicit compression_threshold must win over context_window_tokens."""
        config = {
            "models": {
                "default": {
                    "name": "ssm-big",
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
                "ssm-big": {
                    "architecture_family": "state_space",
                    "context_window_tokens": 131072,
                    "compression_threshold": 32768,  # explicit override
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
            },
            "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},
        }
        mgr = _manager_with_config(config)
        # Must return the explicit 32768, not context_window_tokens (131072).
        assert mgr.get_compression_threshold("ssm-big") == 32768

    def test_transformer_explicit_override_still_respected(self):
        """Explicit override must also work for transformer models (existing behaviour)."""
        config = {
            "models": {
                "default": {
                    "name": "t5",
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
                "t5": {
                    "compression_threshold": 4096,
                    "context_window_tokens": 8192,
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
            },
            "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},
        }
        mgr = _manager_with_config(config)
        assert mgr.get_compression_threshold("t5") == 4096


# ---------------------------------------------------------------------------
# Regression: #8360 unknown model must not inherit default model's family
# ---------------------------------------------------------------------------


class TestGetArchitectureFamilyFallthrough:
    def test_unknown_model_does_not_inherit_default_family(self):
        """Issue #8360: unknown model must return 'transformer', not default's family."""
        config = {
            "models": {
                "default": {
                    "name": "mamba-default",
                    "architecture_family": "state_space",  # non-transformer default!
                    "context_window_tokens": 131072,
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
                "mamba-default": {
                    "architecture_family": "state_space",
                    "context_window_tokens": 131072,
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
            },
            "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},
        }
        mgr = _manager_with_config(config)
        # Unknown model must NOT inherit state_space from default entry.
        assert mgr.get_architecture_family("totally-unknown-model") == "transformer"


# ---------------------------------------------------------------------------
# Regression: #8361 architecture_family values normalized before frozenset check
# ---------------------------------------------------------------------------


class TestArchitectureFamilyNormalization:
    def test_uppercase_family_recognized(self):
        """Issue #8361: 'State_Space' must be normalized to 'state_space'."""
        config = {
            "models": {
                "default": {
                    "name": "m",
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
                "m": {
                    "architecture_family": "State_Space",
                    "context_window_tokens": 131072,
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
            },
            "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},
        }
        mgr = _manager_with_config(config)
        assert mgr.get_architecture_family("m") == "state_space"

    def test_family_with_whitespace_normalized(self):
        """Issue #8361: ' hybrid ' must be stripped and lowercased."""
        config = {
            "models": {
                "default": {
                    "name": "j",
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
                "j": {
                    "architecture_family": " Hybrid ",
                    "context_window_tokens": 256000,
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
            },
            "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},
        }
        mgr = _manager_with_config(config)
        assert mgr.get_architecture_family("j") == "hybrid"

    def test_uppercased_family_bypasses_compression(self):
        """Issue #8361: uppercase family must still trigger non-transformer bypass."""
        config = {
            "models": {
                "default": {
                    "name": "ssm",
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
                "ssm": {
                    "architecture_family": "STATE_SPACE",
                    "context_window_tokens": 100000,
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
            },
            "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},
        }
        mgr = _manager_with_config(config)
        # Should use context_window_tokens (100000), not the transformer 8192 cap.
        assert mgr.get_compression_threshold("ssm") == 100000


# ---------------------------------------------------------------------------
# New in MVA-1387: "ssm" family value from llm_shared.ArchitectureFamily.SSM
# ---------------------------------------------------------------------------


class TestSsmFamilyValue:
    def test_ssm_in_non_transformer_families(self):
        assert "ssm" in _NON_TRANSFORMER_FAMILIES

    def test_ssm_family_returns_ssm(self):
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        assert mgr.get_architecture_family("mamba2-7b") == "ssm"

    def test_ssm_compression_threshold_uses_context_window(self):
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        assert mgr.get_compression_threshold("mamba2-7b") == 131072

    def test_ssm_not_capped_at_8192(self):
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        assert mgr.get_compression_threshold("mamba2-7b") > 8192

    @pytest.mark.asyncio
    async def test_ssm_async_compress_returns_false(self):
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        result = await mgr.async_should_compress(50000, "mamba2-7b")
        assert result is False


# ---------------------------------------------------------------------------
# New in MVA-1387: registry fallback via llm_shared.get_architecture_family
# ---------------------------------------------------------------------------

_TRANSFORMER_ONLY_CONFIG = {
    "models": {
        "default": {
            "name": "llama3",
            "context_window_tokens": 4096,
            "max_output_tokens": 2048,
            "message_budget": {"system_prompt": 500, "recent_messages": 20, "max_history_tokens": 3000},
        },
        "llama3": {
            "context_window_tokens": 4096,
            "max_output_tokens": 2048,
            "message_budget": {"system_prompt": 500, "recent_messages": 20, "max_history_tokens": 3000},
        },
    },
    "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},
}


class TestRegistryFallback:
    """get_architecture_family delegates to llm_shared when model absent from YAML."""

    def test_model_not_in_config_calls_registry(self):
        mgr = _manager_with_config(_TRANSFORMER_ONLY_CONFIG)
        with patch(
            "context_window_manager.ContextWindowManager._registry_family",
            return_value="ssm",
        ) as mock_reg:
            result = mgr.get_architecture_family("mamba-unknown")
        mock_reg.assert_called_once_with("mamba-unknown")
        assert result == "ssm"

    def test_model_in_config_without_family_calls_registry(self):
        """Entry exists but has no architecture_family key → delegate to registry."""
        config = {
            "models": {
                "default": {
                    "name": "no-family-model",
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
                "no-family-model": {
                    "context_window_tokens": 131072,
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                    # no architecture_family key
                },
            },
            "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},
        }
        mgr = _manager_with_config(config)
        with patch(
            "context_window_manager.ContextWindowManager._registry_family",
            return_value="hybrid",
        ) as mock_reg:
            result = mgr.get_architecture_family("no-family-model")
        mock_reg.assert_called_once_with("no-family-model")
        assert result == "hybrid"

    def test_model_in_config_with_family_does_not_call_registry(self):
        """Explicit family in YAML must skip the registry lookup."""
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        with patch(
            "context_window_manager.ContextWindowManager._registry_family",
        ) as mock_reg:
            result = mgr.get_architecture_family("mamba-3b")
        mock_reg.assert_not_called()
        assert result == "state_space"

    def test_registry_exception_falls_back_to_transformer(self):
        """If llm_shared import fails, must not raise — return 'transformer'."""
        _manager_with_config(_TRANSFORMER_ONLY_CONFIG)
        with patch(
            "context_window_manager.ContextWindowManager._registry_family",
            side_effect=RuntimeError("import error"),
        ):
            # get_architecture_family delegates to _registry_family which raises;
            # we verify the integration handles ImportError at the _registry_family
            # boundary (the static method catches exceptions internally).
            pass
        # Test _registry_family's own exception guard directly.
        with patch(
            "llm_shared.model_param_registry.get_architecture_family",
            side_effect=ImportError("llm_shared unavailable"),
        ):
            result = ContextWindowManager._registry_family("any-model")
        assert result == "transformer"


# ---------------------------------------------------------------------------
# Acceptance criterion (MVA-1387): SSM 128K model accepts 50K prompt
# ---------------------------------------------------------------------------


class TestAcceptanceCriteria:
    @pytest.mark.asyncio
    async def test_ssm_128k_accepts_50k_prompt_without_compression(self):
        """AC: SSM/hybrid model with 128K native context must not compress 50K tokens."""
        config = {
            "models": {
                "default": {
                    "name": "mamba-128k",
                    "message_budget": {"system_prompt": 0, "recent_messages": 10, "max_history_tokens": 1000},
                },
                "mamba-128k": {
                    "architecture_family": "ssm",
                    "context_window_tokens": 131072,
                    "message_budget": {"system_prompt": 0, "recent_messages": 50, "max_history_tokens": 100000},
                },
            },
            "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},
        }
        mgr = _manager_with_config(config)
        result = await mgr.async_should_compress(50000, "mamba-128k")
        assert result is False, "SSM 128K model must not compress a 50K-token prompt"

    def test_transformer_continues_to_cap(self):
        """AC: transformer models must still return the 8192 threshold."""
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        assert mgr.get_compression_threshold("llama3") == 8192


# ---------------------------------------------------------------------------
# Issue #9294: Adaptive context budget for models not in YAML
# ---------------------------------------------------------------------------


class TestGetAdaptiveContextLength:
    """MVA-3098: get_adaptive_context_length() scales unknown models via registry."""

    def test_model_in_yaml_returns_declared_value(self):
        """AC #9294.1: YAML-configured models return exact context_window_tokens."""
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        assert mgr.get_adaptive_context_length("llama3") == 4096
        assert mgr.get_adaptive_context_length("mamba-3b") == 131072

    def test_unknown_model_with_registry_hit_scales_to_85_percent(self):
        """AC #9294.2: Unknown model with registry hit → 85% of discovered window."""
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        with patch(
            "context_window_manager.ContextWindowManager._query_known_context_length",
            return_value=128000,
        ):
            result = mgr.get_adaptive_context_length("new-ollama-model")
        # 128000 * 0.85 = 108800
        assert result == 108800

    def test_unknown_model_with_no_registry_falls_back_to_4096(self):
        """AC #9294.3: Unknown model with no registry entry → YAML default (4096)."""
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        with patch(
            "context_window_manager.ContextWindowManager._query_known_context_length",
            return_value=0,
        ):
            result = mgr.get_adaptive_context_length("totally-unknown")
        assert result == 4096

    def test_very_large_context_capped_at_200k(self):
        """AC #9294.4: Very large context window (>200k) capped at _CONTEXT_HARD_MAX."""
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        with patch(
            "context_window_manager.ContextWindowManager._query_known_context_length",
            return_value=1_000_000,
        ):
            result = mgr.get_adaptive_context_length("huge-model")
        # 1M * 0.85 = 850k, but capped at 200k
        assert result == 200_000

    def test_uses_current_model_when_none(self):
        """get_adaptive_context_length() with no model_name uses current_model."""
        mgr = _manager_with_config(_TRANSFORMER_CONFIG)
        mgr.current_model = "jamba-7b"
        assert mgr.get_adaptive_context_length() == 256000
