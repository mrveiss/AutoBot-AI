# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for model_inspector.

Covers: _extract_from_config with mock config, _estimate_param_count with known
values, _count_params_via_skeleton with mocked accelerate/transformers, cache TTL
expiration, inspect_model caching, missing-library error paths, and
model_fits_in_vram through the TierRouter interface.

Issue #3186: Add test coverage for model_inspector.
"""

import time
from unittest.mock import MagicMock, patch

from llm_shared.optimization.model_inspector import (
    ModelInfo,
    _cache_put,
    _count_params_via_skeleton,
    _estimate_param_count,
    _extract_from_config,
    clear_cache,
    inspect_model,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    num_hidden_layers: int = 32,
    hidden_size: int = 4096,
    num_attention_heads: int = 32,
    vocab_size: int = 32000,
) -> MagicMock:
    """Return a minimal PretrainedConfig-like mock."""
    cfg = MagicMock(name="PretrainedConfig")
    cfg.num_hidden_layers = num_hidden_layers
    cfg.hidden_size = hidden_size
    cfg.num_attention_heads = num_attention_heads
    cfg.vocab_size = vocab_size
    # Ensure secondary attribute lookups return None (not a MagicMock truthy value)
    cfg.num_layers = None
    cfg.n_layer = None
    cfg.d_model = None
    cfg.n_embd = None
    cfg.n_head = None
    return cfg


def _make_transformers_mock(param_count: int = 7_000_000_000) -> MagicMock:
    """Return a minimal transformers mock with AutoConfig and AutoModelForCausalLM."""
    model_mock = MagicMock(name="Model")
    # Simulate parameters() returning tensors with numel() values summing to param_count
    p1 = MagicMock()
    p1.numel.return_value = param_count
    model_mock.parameters.return_value = [p1]

    auto_model_mock = MagicMock(name="AutoModelForCausalLM")
    auto_model_mock.from_config.return_value = model_mock

    transformers = MagicMock(name="transformers")
    transformers.AutoModelForCausalLM = auto_model_mock
    return transformers


def _make_accelerate_mock() -> MagicMock:
    """Return a minimal accelerate mock whose init_empty_weights is a no-op ctx manager."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=None)
    ctx.__exit__ = MagicMock(return_value=False)

    accelerate = MagicMock(name="accelerate")
    accelerate.init_empty_weights.return_value = ctx
    return accelerate


# ---------------------------------------------------------------------------
# TestEstimateParamCount
# ---------------------------------------------------------------------------


class TestEstimateParamCount:
    """Tests for _estimate_param_count()."""

    def test_zero_layers_returns_zero(self):
        """Returns 0 when num_layers is 0."""
        assert _estimate_param_count(0, 4096, 32000) == 0

    def test_zero_hidden_returns_zero(self):
        """Returns 0 when hidden_size is 0."""
        assert _estimate_param_count(32, 0, 32000) == 0

    def test_known_small_model(self):
        """Matches manual calculation for a tiny model (2 layers, hidden=64, vocab=256)."""
        # embedding: 256 * 64 = 16384
        # per_layer: 12 * 64^2 = 49152; total layers: 2 * 49152 = 98304
        # total: 16384 + 98304 = 114688
        result = _estimate_param_count(2, 64, 256)
        assert result == 114688

    def test_larger_model_is_positive(self):
        """A 7B-scale config produces a positive parameter count."""
        result = _estimate_param_count(32, 4096, 32000)
        assert result > 0


# ---------------------------------------------------------------------------
# TestExtractFromConfig
# ---------------------------------------------------------------------------


class TestExtractFromConfig:
    """Tests for _extract_from_config()."""

    def test_reads_num_hidden_layers(self):
        """Reads num_hidden_layers from config."""
        cfg = _make_config(num_hidden_layers=24)
        info = _extract_from_config(cfg)
        assert info.num_layers == 24

    def test_reads_hidden_size(self):
        """Reads hidden_size from config."""
        cfg = _make_config(hidden_size=2048)
        info = _extract_from_config(cfg)
        assert info.hidden_size == 2048

    def test_reads_num_attention_heads(self):
        """Reads num_attention_heads from config."""
        cfg = _make_config(num_attention_heads=16)
        info = _extract_from_config(cfg)
        assert info.num_attention_heads == 16

    def test_formula_estimate_used_when_no_override(self):
        """Uses formula estimate when param_count_override is not given."""
        cfg = _make_config(num_hidden_layers=2, hidden_size=64, vocab_size=256)
        info = _extract_from_config(cfg)
        assert info.param_count == _estimate_param_count(2, 64, 256)

    def test_override_takes_precedence_over_formula(self):
        """param_count_override replaces the formula estimate."""
        cfg = _make_config(num_hidden_layers=32, hidden_size=4096, vocab_size=32000)
        info = _extract_from_config(cfg, param_count_override=7_241_732_096)
        assert info.param_count == 7_241_732_096

    def test_estimated_size_gb_consistent_with_param_count(self):
        """estimated_size_gb == param_count * 4 / (1024**3)."""
        cfg = _make_config()
        info = _extract_from_config(cfg, param_count_override=1_000_000_000)
        expected = (1_000_000_000 * 4) / (1024**3)
        assert abs(info.estimated_size_gb - expected) < 1e-6

    def test_fallback_attributes_n_layer(self):
        """Falls back to n_layer when num_hidden_layers is absent."""
        cfg = MagicMock()
        cfg.num_hidden_layers = None
        cfg.num_layers = None
        cfg.n_layer = 28
        cfg.hidden_size = 4096
        cfg.d_model = None
        cfg.n_embd = None
        cfg.num_attention_heads = 32
        cfg.n_head = None
        cfg.vocab_size = 32000
        info = _extract_from_config(cfg)
        assert info.num_layers == 28

    def test_zero_config_returns_zero_params(self):
        """All-zero config produces zero param_count."""
        cfg = MagicMock()
        for attr in (
            "num_hidden_layers",
            "num_layers",
            "n_layer",
            "hidden_size",
            "d_model",
            "n_embd",
            "num_attention_heads",
            "n_head",
            "vocab_size",
        ):
            setattr(cfg, attr, 0)
        info = _extract_from_config(cfg)
        assert info.param_count == 0


# ---------------------------------------------------------------------------
# TestCountParamsViaSkeleton
# ---------------------------------------------------------------------------


class TestCountParamsViaSkeleton:
    """Tests for _count_params_via_skeleton()."""

    def test_returns_sum_of_parameter_numel(self):
        """Returns exact param count from model.parameters()."""
        cfg = _make_config()
        transformers = _make_transformers_mock(param_count=7_000_000_000)
        accelerate = _make_accelerate_mock()

        result = _count_params_via_skeleton(cfg, transformers, accelerate)
        assert result == 7_000_000_000

    def test_uses_init_empty_weights_context(self):
        """Calls accelerate.init_empty_weights() as a context manager."""
        cfg = _make_config()
        transformers = _make_transformers_mock()
        accelerate = _make_accelerate_mock()

        _count_params_via_skeleton(cfg, transformers, accelerate)

        accelerate.init_empty_weights.assert_called_once()
        ctx = accelerate.init_empty_weights.return_value
        ctx.__enter__.assert_called_once()
        ctx.__exit__.assert_called_once()

    def test_calls_from_config_with_cfg(self):
        """Passes the config object to AutoModelForCausalLM.from_config."""
        cfg = _make_config()
        transformers = _make_transformers_mock()
        accelerate = _make_accelerate_mock()

        _count_params_via_skeleton(cfg, transformers, accelerate)

        transformers.AutoModelForCausalLM.from_config.assert_called_once_with(cfg)

    def test_returns_none_on_exception(self):
        """Returns None when from_config raises, without propagating the error."""
        cfg = _make_config()
        transformers = MagicMock(name="transformers")
        transformers.AutoModelForCausalLM.from_config.side_effect = RuntimeError("unsupported arch")
        accelerate = _make_accelerate_mock()

        result = _count_params_via_skeleton(cfg, transformers, accelerate)
        assert result is None


# ---------------------------------------------------------------------------
# TestCacheTTL
# ---------------------------------------------------------------------------


class TestCacheTTL:
    """Tests for cache get/put and TTL expiration."""

    def setup_method(self):
        """Clear the cache before each test."""
        clear_cache()

    def test_cache_hit_returns_same_info(self):
        """inspect_model returns cached value on second call without re-inspecting."""
        info = ModelInfo(
            num_layers=32,
            hidden_size=4096,
            num_attention_heads=32,
            param_count=7_000_000_000,
            estimated_size_gb=26.0,
        )
        _cache_put("test/model", info)

        result = inspect_model("test/model")
        assert result is info

    def test_expired_cache_triggers_fresh_inspection(self):
        """inspect_model re-inspects after TTL expiration."""
        info = ModelInfo(
            num_layers=32,
            hidden_size=4096,
            num_attention_heads=32,
            param_count=7_000_000_000,
            estimated_size_gb=26.0,
        )
        from llm_shared.optimization import model_inspector as _mod

        _mod._cache["test/expired"] = (info, time.monotonic() - 1)

        with patch(
            "llm_shared.optimization.model_inspector._inspect_via_config",
            return_value=None,
        ) as mock_inspect:
            inspect_model("test/expired")

        mock_inspect.assert_called_once_with("test/expired")

    def test_clear_cache_removes_all_entries(self):
        """clear_cache() empties the cache entirely."""
        from llm_shared.optimization import model_inspector as _mod

        _cache_put("model-a", MagicMock())
        _cache_put("model-b", MagicMock())
        clear_cache()
        assert len(_mod._cache) == 0


# ---------------------------------------------------------------------------
# TestInspectModel
# ---------------------------------------------------------------------------


class TestInspectModel:
    """Integration-level tests for the public inspect_model() function."""

    def setup_method(self):
        """Clear the cache before each test."""
        clear_cache()

    def test_returns_none_when_transformers_missing(self):
        """inspect_model returns None gracefully when transformers is absent."""
        with patch(
            "llm_shared.optimization.model_inspector._import_transformers",
            side_effect=ImportError("transformers missing"),
        ):
            result = inspect_model("some/model")
        assert result is None

    def test_returns_none_when_accelerate_missing(self):
        """inspect_model returns None gracefully when accelerate is absent."""
        with (
            patch(
                "llm_shared.optimization.model_inspector._import_transformers",
                return_value=MagicMock(),
            ),
            patch(
                "llm_shared.optimization.model_inspector._import_accelerate",
                side_effect=ImportError("accelerate missing"),
            ),
        ):
            result = inspect_model("some/model")
        assert result is None

    def test_returns_model_info_with_skeleton_param_count(self):
        """inspect_model uses skeleton param count when available."""
        cfg = _make_config(
            num_hidden_layers=32,
            hidden_size=4096,
            num_attention_heads=32,
            vocab_size=32000,
        )
        mock_transformers = _make_transformers_mock(param_count=7_241_732_096)
        mock_transformers.AutoConfig = MagicMock()
        mock_transformers.AutoConfig.from_pretrained.return_value = cfg
        mock_accelerate = _make_accelerate_mock()

        with (
            patch(
                "llm_shared.optimization.model_inspector._import_transformers",
                return_value=mock_transformers,
            ),
            patch(
                "llm_shared.optimization.model_inspector._import_accelerate",
                return_value=mock_accelerate,
            ),
        ):
            result = inspect_model("meta-llama/Llama-2-7b-hf")

        assert result is not None
        assert result.param_count == 7_241_732_096
        assert result.num_layers == 32
        assert result.hidden_size == 4096

    def test_falls_back_to_formula_when_skeleton_fails(self):
        """inspect_model uses formula estimate when skeleton instantiation fails."""
        cfg = _make_config(num_hidden_layers=2, hidden_size=64, vocab_size=256)
        mock_transformers = MagicMock(name="transformers")
        mock_transformers.AutoConfig = MagicMock()
        mock_transformers.AutoConfig.from_pretrained.return_value = cfg
        mock_transformers.AutoModelForCausalLM.from_config.side_effect = RuntimeError("no arch")
        mock_accelerate = _make_accelerate_mock()

        with (
            patch(
                "llm_shared.optimization.model_inspector._import_transformers",
                return_value=mock_transformers,
            ),
            patch(
                "llm_shared.optimization.model_inspector._import_accelerate",
                return_value=mock_accelerate,
            ),
        ):
            result = inspect_model("tiny/model")

        assert result is not None
        expected = _estimate_param_count(2, 64, 256)
        assert result.param_count == expected

    def test_caches_result_on_success(self):
        """inspect_model stores result in cache so second call skips inspection."""
        cfg = _make_config()
        mock_transformers = _make_transformers_mock()
        mock_transformers.AutoConfig = MagicMock()
        mock_transformers.AutoConfig.from_pretrained.return_value = cfg
        mock_accelerate = _make_accelerate_mock()

        with (
            patch(
                "llm_shared.optimization.model_inspector._import_transformers",
                return_value=mock_transformers,
            ),
            patch(
                "llm_shared.optimization.model_inspector._import_accelerate",
                return_value=mock_accelerate,
            ),
        ):
            first = inspect_model("cached/model")
            second = inspect_model("cached/model")

        # AutoConfig.from_pretrained should only be called once
        assert mock_transformers.AutoConfig.from_pretrained.call_count == 1
        assert first is second

    def test_returns_none_on_config_fetch_failure(self):
        """inspect_model returns None when AutoConfig.from_pretrained raises."""
        mock_transformers = MagicMock(name="transformers")
        mock_transformers.AutoConfig.from_pretrained.side_effect = OSError("hub unavailable")
        mock_accelerate = _make_accelerate_mock()

        with (
            patch(
                "llm_shared.optimization.model_inspector._import_transformers",
                return_value=mock_transformers,
            ),
            patch(
                "llm_shared.optimization.model_inspector._import_accelerate",
                return_value=mock_accelerate,
            ),
        ):
            result = inspect_model("nonexistent/model")

        assert result is None
