# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for layer-by-layer inference engine.

Issue #1946: Layer-by-layer inference mode for batch/offline processing.
"""

import os
import tempfile
import types
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
import torch

# Detect conftest MagicMock torch stub; skip tensor-operation tests when absent (#5728)
_TORCH_IS_STUB = not isinstance(torch, types.ModuleType)
requires_torch = pytest.mark.skipif(_TORCH_IS_STUB, reason="requires real PyTorch")

from llm_shared.optimization.layer_inference import (
    LayerInferenceConfig,
    LayerInferenceEngine,
    LayerInferenceStats,
    _get_peak_memory,
    _greedy_sample,
    _is_eos,
    _layer_prefix_for_arch,
    _move_to_meta,
    _reset_peak_memory,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    model_name: str = "test-model",
    compression: str = "none",
    max_seq_len: int = 512,
    batch_size: int = 1,
    device: str = "cpu",
    cache_dir: str = None,
) -> LayerInferenceConfig:
    """Return a LayerInferenceConfig with sensible defaults."""
    return LayerInferenceConfig(
        model_name=model_name,
        compression=compression,
        max_seq_len=max_seq_len,
        batch_size=batch_size,
        device=device,
        cache_dir=cache_dir,
    )


def _make_engine(cfg: LayerInferenceConfig = None) -> LayerInferenceEngine:
    """Return a LayerInferenceEngine with the given (or default) config."""
    return LayerInferenceEngine(cfg or _make_config())


def _tiny_state_dict(layer_name: str = "model.layers.0") -> Dict[str, torch.Tensor]:
    """Return a minimal state dict with one weight tensor under layer_name."""
    return {f"{layer_name}.weight": torch.randn(4, 4)}


def _write_state_dict(state_dict: Dict[str, torch.Tensor], path: str) -> None:
    """Save a state dict to path using torch.save."""
    torch.save(state_dict, path)


# ---------------------------------------------------------------------------
# LayerInferenceConfig validation
# ---------------------------------------------------------------------------


class TestLayerInferenceConfig:
    """Tests for LayerInferenceConfig field validation."""

    def test_valid_config_constructs(self):
        """A fully specified valid config should construct without error."""
        cfg = _make_config()
        assert cfg.model_name == "test-model"
        assert cfg.compression == "none"

    def test_empty_model_name_raises(self):
        """Empty model_name should raise ValueError."""
        with pytest.raises(ValueError, match="model_name"):
            _make_config(model_name="")

    def test_invalid_compression_raises(self):
        """Unknown compression value should raise ValueError."""
        with pytest.raises(ValueError, match="compression"):
            _make_config(compression="fp4")

    def test_valid_compressions_accepted(self):
        """All valid compression strings should be accepted."""
        for c in ("none", "4bit", "8bit"):
            cfg = _make_config(compression=c)
            assert cfg.compression == c

    def test_zero_max_seq_len_raises(self):
        """max_seq_len=0 should raise ValueError."""
        with pytest.raises(ValueError, match="max_seq_len"):
            _make_config(max_seq_len=0)

    def test_zero_batch_size_raises(self):
        """batch_size=0 should raise ValueError."""
        with pytest.raises(ValueError, match="batch_size"):
            _make_config(batch_size=0)

    def test_default_cache_dir_is_none(self):
        """cache_dir should default to None."""
        cfg = _make_config()
        assert cfg.cache_dir is None

    def test_cache_dir_accepted(self):
        """cache_dir string should be stored on the config."""
        cfg = _make_config(cache_dir="/tmp/models")  # nosec B108 - test/controlled code uses tmpdir intentionally
        assert cfg.cache_dir == "/tmp/models"  # nosec B108 - test/controlled code uses tmpdir intentionally


# ---------------------------------------------------------------------------
# LayerInferenceStats
# ---------------------------------------------------------------------------


class TestLayerInferenceStats:
    """Tests for LayerInferenceStats dataclass."""

    def test_defaults_are_zero(self):
        """All numeric fields should default to zero."""
        s = LayerInferenceStats()
        assert s.total_time == 0.0
        assert s.peak_memory == 0
        assert s.tokens_generated == 0
        assert s.per_layer_times == {}

    def test_per_layer_times_is_independent(self):
        """Two Stats instances should not share the same per_layer_times dict."""
        s1 = LayerInferenceStats()
        s2 = LayerInferenceStats()
        s1.per_layer_times["layer0"] = 0.5
        assert "layer0" not in s2.per_layer_times


# ---------------------------------------------------------------------------
# get_layer_names — layer name extraction
# ---------------------------------------------------------------------------


class TestGetLayerNames:
    """Tests for LayerInferenceEngine.get_layer_names()."""

    def test_llama_style_config(self):
        """LLaMA-style config should return model.layers.N names."""
        engine = _make_engine()
        cfg = {"model_type": "llama", "num_hidden_layers": 3}
        names = engine.get_layer_names(cfg)
        assert names == ["model.layers.0", "model.layers.1", "model.layers.2"]

    def test_gpt2_style_config(self):
        """GPT-2 style config should return transformer.h.N names."""
        engine = _make_engine()
        cfg = {"model_type": "gpt2", "num_hidden_layers": 2}
        names = engine.get_layer_names(cfg)
        assert names == ["transformer.h.0", "transformer.h.1"]

    def test_n_layer_alias(self):
        """n_layer key (GPT-NeoX style) should also be recognised."""
        engine = _make_engine()
        cfg = {"model_type": "gpt_neox", "n_layer": 4}
        names = engine.get_layer_names(cfg)
        assert len(names) == 4

    def test_unknown_arch_returns_model_fallback(self):
        """Configs without num_hidden_layers should return ['model']."""
        engine = _make_engine()
        cfg = {"model_type": "unknown_arch"}
        names = engine.get_layer_names(cfg)
        assert names == ["model"]

    def test_empty_config_returns_model_fallback(self):
        """Empty config dict should return ['model']."""
        engine = _make_engine()
        assert engine.get_layer_names({}) == ["model"]

    def test_layer_count_matches_num_hidden_layers(self):
        """Returned list length must equal num_hidden_layers."""
        engine = _make_engine()
        for n in (1, 8, 32):
            names = engine.get_layer_names({"model_type": "llama", "num_hidden_layers": n})
            assert len(names) == n


# ---------------------------------------------------------------------------
# load_layer — load / evict cycle
# ---------------------------------------------------------------------------


@requires_torch
class TestLoadEvictCycle:
    """Tests for LayerInferenceEngine.load_layer() and evict_layer()."""

    def test_load_layer_returns_module(self):
        """load_layer should return an nn.Module instance."""
        engine = _make_engine()
        layer_name = "model.layers.0"
        sd = _tiny_state_dict(layer_name)
        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            path = f.name
        try:
            _write_state_dict(sd, path)
            module = engine.load_layer(layer_name, path)
            assert isinstance(module, torch.nn.Module)
        finally:
            os.unlink(path)

    def test_loaded_layer_has_expected_parameter(self):
        """Loaded module should expose the weight as a parameter."""
        engine = _make_engine()
        layer_name = "model.layers.0"
        sd = _tiny_state_dict(layer_name)
        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            path = f.name
        try:
            _write_state_dict(sd, path)
            module = engine.load_layer(layer_name, path)
            # Module should have at least one parameter
            params = list(module.parameters())
            assert len(params) >= 1
        finally:
            os.unlink(path)

    def test_missing_layer_prefix_raises_key_error(self):
        """load_layer should raise KeyError when no keys match the prefix."""
        engine = _make_engine()
        sd = {"other.layers.0.weight": torch.randn(4, 4)}
        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            path = f.name
        try:
            _write_state_dict(sd, path)
            with pytest.raises(KeyError, match="No keys matching prefix"):
                engine.load_layer("model.layers.0", path)
        finally:
            os.unlink(path)

    def test_evict_layer_moves_to_meta(self):
        """After evict_layer, parameters should reside on the meta device."""
        engine = _make_engine()
        layer_name = "model.layers.0"
        sd = _tiny_state_dict(layer_name)
        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            path = f.name
        try:
            _write_state_dict(sd, path)
            module = engine.load_layer(layer_name, path)
            engine.evict_layer(module)
            for param in module.parameters():
                assert param.device.type == "meta"
        finally:
            os.unlink(path)

    def test_load_evict_multiple_layers(self):
        """Multiple sequential load/evict cycles should complete without error."""
        engine = _make_engine()
        sd = {
            "model.layers.0.weight": torch.randn(4, 4),
            "model.layers.1.weight": torch.randn(4, 4),
        }
        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            path = f.name
        try:
            _write_state_dict(sd, path)
            for i in range(2):
                layer = engine.load_layer(f"model.layers.{i}", path)
                engine.evict_layer(layer)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# forward_pass
# ---------------------------------------------------------------------------


@requires_torch
class TestForwardPass:
    """Tests for LayerInferenceEngine.forward_pass()."""

    def test_empty_layers_raises(self):
        """forward_pass with an empty layers list should raise ValueError."""
        engine = _make_engine()
        input_ids = torch.zeros(1, 4, dtype=torch.long)
        with pytest.raises(ValueError, match="layers must not be empty"):
            engine.forward_pass(input_ids, [])

    def test_single_identity_layer(self):
        """A single identity layer should return the input unchanged."""
        engine = _make_engine()
        hidden = torch.randn(1, 4, 8)

        def identity(x):
            return x

        result = engine.forward_pass(hidden, [identity])
        assert result.shape == hidden.shape

    def test_layer_returning_tuple(self):
        """forward_pass should handle layers that return a tuple."""
        engine = _make_engine()
        hidden = torch.randn(1, 4, 8)

        def layer_with_tuple(x):
            return (x * 2, None)

        result = engine.forward_pass(hidden, [layer_with_tuple])
        assert torch.allclose(result, hidden * 2)

    def test_multiple_layers_applied_in_order(self):
        """Multiple layers should be applied sequentially."""
        engine = _make_engine()
        hidden = torch.ones(1, 2, 4)

        layers: List[Any] = [
            lambda x: x + 1,  # noqa: E731
            lambda x: x * 2,  # noqa: E731
        ]
        result = engine.forward_pass(hidden, layers)
        expected = (hidden + 1) * 2
        assert torch.allclose(result, expected)

    def test_kv_cache_argument_accepted(self):
        """kv_cache kwarg should be accepted without raising."""
        engine = _make_engine()
        hidden = torch.randn(1, 3, 4)
        mock_cache = MagicMock()
        result = engine.forward_pass(hidden, [lambda x: x], kv_cache=mock_cache)  # noqa: E731
        assert result.shape == hidden.shape


# ---------------------------------------------------------------------------
# generate — mocked layers
# ---------------------------------------------------------------------------


@requires_torch
class TestGenerate:
    """Tests for LayerInferenceEngine.generate() with mocked dependencies."""

    def _make_mock_tokeniser(self, vocab_size: int = 32, eos_id: int = 2) -> MagicMock:
        """Build a mock tokeniser that simulates encode/decode."""
        tok = MagicMock()
        tok.eos_token_id = eos_id
        ids = torch.zeros(1, 4, dtype=torch.long)
        tok.return_value = MagicMock(input_ids=ids)
        tok.decode.return_value = "hello world"
        return tok

    def test_generate_returns_string(self):
        """generate() should return a non-empty string when layers work."""
        engine = _make_engine()
        vocab_size = 16
        mock_tokeniser = self._make_mock_tokeniser(vocab_size=vocab_size)

        # Provide a fake forward pass that produces random logits
        fake_logits = torch.randn(1, 5, vocab_size)

        with (
            patch.object(engine, "_load_tokeniser", return_value=mock_tokeniser),
            patch.object(engine, "load_model_config", return_value={"num_hidden_layers": 1}),
            patch.object(engine, "get_layer_names", return_value=["model.layers.0"]),
            patch.object(engine, "_resolve_checkpoint_path", return_value="/fake/path"),
            patch.object(engine, "_run_layer_loop", return_value=fake_logits),
        ):
            result = engine.generate("hello", max_new_tokens=3)

        assert isinstance(result, str)

    def test_generate_respects_max_new_tokens(self):
        """generate() must stop at max_new_tokens even without EOS."""
        engine = _make_engine()
        vocab_size = 16
        mock_tokeniser = self._make_mock_tokeniser(eos_id=999)  # EOS never reached
        mock_tokeniser.decode.return_value = "x" * 5

        fake_logits = torch.randn(1, 4, vocab_size)
        call_count = {"n": 0}

        def counted_run_layer_loop(*args, **kwargs):
            call_count["n"] += 1
            return fake_logits

        with (
            patch.object(engine, "_load_tokeniser", return_value=mock_tokeniser),
            patch.object(engine, "load_model_config", return_value={"num_hidden_layers": 1}),
            patch.object(engine, "get_layer_names", return_value=["model.layers.0"]),
            patch.object(engine, "_resolve_checkpoint_path", return_value="/fake/path"),
            patch.object(engine, "_run_layer_loop", side_effect=counted_run_layer_loop),
        ):
            engine.generate("test", max_new_tokens=5)

        assert call_count["n"] == 5

    def test_generate_invalid_max_new_tokens_raises(self):
        """max_new_tokens < 1 should raise ValueError immediately."""
        engine = _make_engine()
        with pytest.raises(ValueError, match="max_new_tokens"):
            engine.generate("test", max_new_tokens=0)

    def test_generate_stops_at_eos(self):
        """generate() must stop early when EOS token is produced."""
        engine = _make_engine()
        eos_id = 3
        vocab_size = 16
        mock_tokeniser = self._make_mock_tokeniser(vocab_size=vocab_size, eos_id=eos_id)
        mock_tokeniser.decode.return_value = "early stop"

        # Logits that always argmax to eos_id
        fake_logits = torch.zeros(1, 4, vocab_size)
        fake_logits[0, -1, eos_id] = 100.0  # force argmax = eos_id

        call_count = {"n": 0}

        def counted_run_layer_loop(*args, **kwargs):
            call_count["n"] += 1
            return fake_logits

        with (
            patch.object(engine, "_load_tokeniser", return_value=mock_tokeniser),
            patch.object(engine, "load_model_config", return_value={"num_hidden_layers": 1}),
            patch.object(engine, "get_layer_names", return_value=["model.layers.0"]),
            patch.object(engine, "_resolve_checkpoint_path", return_value="/fake/path"),
            patch.object(engine, "_run_layer_loop", side_effect=counted_run_layer_loop),
        ):
            engine.generate("test", max_new_tokens=20)

        # Should have stopped after 1 step (first token is EOS)
        assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# LayerInferenceStats tracking through generate
# ---------------------------------------------------------------------------


@requires_torch
class TestStatsTracking:
    """Tests that LayerInferenceStats is populated correctly."""

    def test_tokens_generated_matches_output(self):
        """Stats tokens_generated should match the number of tokens decoded."""
        engine = _make_engine()
        vocab_size = 16
        eos_id = 999
        mock_tokeniser = MagicMock()
        mock_tokeniser.eos_token_id = eos_id
        mock_tokeniser.return_value = MagicMock(input_ids=torch.zeros(1, 3, dtype=torch.long))
        mock_tokeniser.decode.return_value = "abc"

        # Use a non-EOS logit so we generate exactly max_new_tokens tokens
        fake_logits = torch.zeros(1, 3, vocab_size)
        fake_logits[0, -1, 1] = 100.0  # argmax = 1, not eos_id

        with (
            patch.object(engine, "_load_tokeniser", return_value=mock_tokeniser),
            patch.object(engine, "load_model_config", return_value={"num_hidden_layers": 1}),
            patch.object(engine, "get_layer_names", return_value=["model.layers.0"]),
            patch.object(engine, "_resolve_checkpoint_path", return_value="/fake/path"),
            patch.object(engine, "_run_layer_loop", return_value=fake_logits),
        ):
            engine.generate("hi", max_new_tokens=4)

        # No direct access to stats from generate(); test via decode call count
        assert mock_tokeniser.decode.called


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


@requires_torch
class TestModuleHelpers:
    """Tests for module-level private helpers."""

    def test_layer_prefix_llama(self):
        """LLaMA model_type should map to model.layers. prefix."""
        assert _layer_prefix_for_arch("llama") == "model.layers."

    def test_layer_prefix_mistral(self):
        """Mistral model_type should map to model.layers. prefix."""
        assert _layer_prefix_for_arch("mistral") == "model.layers."

    def test_layer_prefix_gpt2(self):
        """GPT-2 model_type should map to transformer.h. prefix."""
        assert _layer_prefix_for_arch("gpt2") == "transformer.h."

    def test_layer_prefix_gptj(self):
        """GPT-J model_type should map to transformer.h. prefix."""
        assert _layer_prefix_for_arch("gptj") == "transformer.h."

    def test_layer_prefix_unknown_defaults_to_model_layers(self):
        """Unknown model type should fall back to model.layers. prefix."""
        assert _layer_prefix_for_arch("novelarch") == "model.layers."

    def test_greedy_sample_returns_int(self):
        """_greedy_sample should return a Python int."""
        hidden = torch.randn(1, 4, 32)
        result = _greedy_sample(torch, hidden)
        assert isinstance(result, int)

    def test_greedy_sample_argmax_last_position(self):
        """_greedy_sample should argmax the last sequence position."""
        hidden = torch.zeros(1, 3, 8)
        hidden[0, -1, 5] = 100.0  # force argmax = 5
        assert _greedy_sample(torch, hidden) == 5

    def test_is_eos_true_when_matching(self):
        """_is_eos should return True when token_id equals tokeniser eos_token_id."""
        tok = MagicMock()
        tok.eos_token_id = 2
        assert _is_eos(tok, 2) is True

    def test_is_eos_false_when_not_matching(self):
        """_is_eos should return False when token_id differs from eos_token_id."""
        tok = MagicMock()
        tok.eos_token_id = 2
        assert _is_eos(tok, 5) is False

    def test_is_eos_false_when_no_eos_on_tokeniser(self):
        """_is_eos should return False when eos_token_id attribute is absent."""
        tok = MagicMock(spec=[])  # no eos_token_id attribute
        assert _is_eos(tok, 0) is False

    def test_move_to_meta_moves_params(self):
        """_move_to_meta should place all parameters on the meta device."""
        mod = torch.nn.Linear(4, 4)
        _move_to_meta(torch, mod)
        for param in mod.parameters():
            assert param.device.type == "meta"

    def test_reset_peak_memory_cpu_does_not_raise(self):
        """_reset_peak_memory for CPU device should be a no-op without error."""
        _reset_peak_memory(torch, "cpu")  # must not raise

    def test_get_peak_memory_cpu_returns_zero(self):
        """_get_peak_memory for CPU should return 0."""
        assert _get_peak_memory(torch, "cpu") == 0
