# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for HfQuantizer integration.

Covers: detection logic, GPTQ/AWQ/BnB routing, parameter checking,
per-parameter creation, layer loading, and missing-library fallback.

Issue #1954: HfQuantizer integration for pre-quantized GPTQ/AWQ models.
"""

from unittest.mock import MagicMock, patch

import pytest

from llm_shared.optimization.hf_quantizer import (
    _AWQ_QUANTIZED_SUFFIXES,
    _GPTQ_QUANTIZED_SUFFIXES,
    HfQuantizerWrapper,
    LayerLoadResult,
    QuantizationType,
    QuantizedLayerLoader,
    QuantizerConfig,
    detect_quantization,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transformers_mock() -> MagicMock:
    """Return a minimal mock of the transformers module."""
    mock = MagicMock(name="transformers")
    mock.GPTQConfig.return_value = MagicMock(name="GPTQConfig_instance")
    mock.AwqConfig.return_value = MagicMock(name="AwqConfig_instance")
    mock.BitsAndBytesConfig.return_value = MagicMock(name="BitsAndBytesConfig_instance")
    return mock


# ---------------------------------------------------------------------------
# TestDetectQuantization
# ---------------------------------------------------------------------------


class TestDetectQuantization:
    """Tests for the detect_quantization() function."""

    def test_empty_config_returns_none(self):
        """No quantization_config key → NONE."""
        result = detect_quantization({})
        assert result == QuantizationType.NONE

    def test_null_quantization_config_returns_none(self):
        """Explicit None value for quantization_config → NONE."""
        result = detect_quantization({"quantization_config": None})
        assert result == QuantizationType.NONE

    def test_gptq_via_quant_type(self):
        """quant_type='gptq' → GPTQ."""
        cfg = {"quantization_config": {"quant_type": "gptq", "bits": 4}}
        assert detect_quantization(cfg) == QuantizationType.GPTQ

    def test_gptq_case_insensitive(self):
        """quant_type='GPTQ' (upper-case) → GPTQ."""
        cfg = {"quantization_config": {"quant_type": "GPTQ", "bits": 4}}
        assert detect_quantization(cfg) == QuantizationType.GPTQ

    def test_awq_via_quant_type(self):
        """quant_type='awq' → AWQ."""
        cfg = {"quantization_config": {"quant_type": "awq", "bits": 4}}
        assert detect_quantization(cfg) == QuantizationType.AWQ

    def test_bitsandbytes_load_in_4bit(self):
        """load_in_4bit=True → BITSANDBYTES."""
        cfg = {"quantization_config": {"load_in_4bit": True}}
        assert detect_quantization(cfg) == QuantizationType.BITSANDBYTES

    def test_bitsandbytes_load_in_8bit(self):
        """load_in_8bit=True → BITSANDBYTES."""
        cfg = {"quantization_config": {"load_in_8bit": True}}
        assert detect_quantization(cfg) == QuantizationType.BITSANDBYTES

    def test_gptq_inferred_from_bits_and_group_size(self):
        """bits=4 + group_size present, no quant_type → inferred as GPTQ."""
        cfg = {"quantization_config": {"bits": 4, "group_size": 128}}
        assert detect_quantization(cfg) == QuantizationType.GPTQ

    def test_gptq_inferred_bits_3(self):
        """bits=3 + group_size → inferred as GPTQ."""
        cfg = {"quantization_config": {"bits": 3, "group_size": 64}}
        assert detect_quantization(cfg) == QuantizationType.GPTQ

    def test_unknown_config_returns_none(self):
        """Unrecognised quantization_config fields → NONE."""
        cfg = {"quantization_config": {"some_unknown_key": "value"}}
        assert detect_quantization(cfg) == QuantizationType.NONE

    def test_bits_without_group_size_returns_none(self):
        """bits alone (no group_size, no quant_type) → NONE (not enough signal)."""
        cfg = {"quantization_config": {"bits": 4}}
        assert detect_quantization(cfg) == QuantizationType.NONE


# ---------------------------------------------------------------------------
# TestHfQuantizerWrapperFromConfig
# ---------------------------------------------------------------------------


class TestHfQuantizerWrapperFromConfig:
    """Tests for HfQuantizerWrapper.from_config()."""

    def test_from_config_gptq(self):
        """from_config auto-detects GPTQ type."""
        model_config = {"quantization_config": {"quant_type": "gptq", "bits": 4}}
        wrapper = HfQuantizerWrapper.from_config(model_config)
        assert wrapper._config.quantization_type == QuantizationType.GPTQ

    def test_from_config_awq(self):
        """from_config auto-detects AWQ type."""
        model_config = {"quantization_config": {"quant_type": "awq"}}
        wrapper = HfQuantizerWrapper.from_config(model_config)
        assert wrapper._config.quantization_type == QuantizationType.AWQ

    def test_from_config_none(self):
        """from_config falls back to NONE for unquantized model."""
        wrapper = HfQuantizerWrapper.from_config({})
        assert wrapper._config.quantization_type == QuantizationType.NONE

    def test_from_config_accepts_overrides(self):
        """from_config passes extra kwargs to QuantizerConfig."""
        model_config = {"quantization_config": {"quant_type": "gptq"}}
        wrapper = HfQuantizerWrapper.from_config(model_config, device_map="cpu", trust_remote_code=True)
        assert wrapper._config.device_map == "cpu"
        assert wrapper._config.trust_remote_code is True


# ---------------------------------------------------------------------------
# TestPreprocessModel
# ---------------------------------------------------------------------------


class TestPreprocessModel:
    """Tests for HfQuantizerWrapper.preprocess_model()."""

    def _gptq_wrapper(self) -> HfQuantizerWrapper:
        cfg = QuantizerConfig(quantization_type=QuantizationType.GPTQ)
        return HfQuantizerWrapper(cfg)

    def _awq_wrapper(self) -> HfQuantizerWrapper:
        cfg = QuantizerConfig(quantization_type=QuantizationType.AWQ)
        return HfQuantizerWrapper(cfg)

    def _bnb_wrapper(self) -> HfQuantizerWrapper:
        cfg = QuantizerConfig(quantization_type=QuantizationType.BITSANDBYTES)
        return HfQuantizerWrapper(cfg)

    def _none_wrapper(self) -> HfQuantizerWrapper:
        cfg = QuantizerConfig(quantization_type=QuantizationType.NONE, torch_dtype="float16")
        return HfQuantizerWrapper(cfg)

    # ---- GPTQ ----

    def test_gptq_preprocess_returns_quantization_config(self):
        """GPTQ preprocessing must include quantization_config key."""
        mock_tf = _make_transformers_mock()
        with patch(
            "llm_shared.optimization.hf_quantizer._import_transformers",
            return_value=mock_tf,
        ):
            kwargs = self._gptq_wrapper().preprocess_model()
        assert "quantization_config" in kwargs
        assert "device_map" in kwargs

    def test_gptq_preprocess_constructs_gptq_config(self):
        """GPTQ preprocessing calls GPTQConfig with bits=4."""
        mock_tf = _make_transformers_mock()
        with patch(
            "llm_shared.optimization.hf_quantizer._import_transformers",
            return_value=mock_tf,
        ):
            self._gptq_wrapper().preprocess_model()
        mock_tf.GPTQConfig.assert_called_once_with(bits=4, disable_exllama=False)

    # ---- AWQ ----

    def test_awq_preprocess_returns_quantization_config(self):
        """AWQ preprocessing must include quantization_config key."""
        mock_tf = _make_transformers_mock()
        mock_awq = MagicMock(name="awq")
        with (
            patch(
                "llm_shared.optimization.hf_quantizer._import_transformers",
                return_value=mock_tf,
            ),
            patch(
                "llm_shared.optimization.hf_quantizer._import_autoawq",
                return_value=mock_awq,
            ),
        ):
            kwargs = self._awq_wrapper().preprocess_model()
        assert "quantization_config" in kwargs

    def test_awq_preprocess_constructs_awq_config(self):
        """AWQ preprocessing calls AwqConfig with version='gemm'."""
        mock_tf = _make_transformers_mock()
        mock_awq = MagicMock(name="awq")
        with (
            patch(
                "llm_shared.optimization.hf_quantizer._import_transformers",
                return_value=mock_tf,
            ),
            patch(
                "llm_shared.optimization.hf_quantizer._import_autoawq",
                return_value=mock_awq,
            ),
        ):
            self._awq_wrapper().preprocess_model()
        mock_tf.AwqConfig.assert_called_once_with(version="gemm")

    # ---- BitsAndBytes ----

    def test_bnb_preprocess_returns_quantization_config(self):
        """BitsAndBytes preprocessing must include quantization_config key."""
        mock_tf = _make_transformers_mock()
        with patch(
            "llm_shared.optimization.hf_quantizer._import_transformers",
            return_value=mock_tf,
        ):
            kwargs = self._bnb_wrapper().preprocess_model()
        assert "quantization_config" in kwargs

    def test_bnb_preprocess_constructs_bnb_config(self):
        """BitsAndBytes preprocessing calls BitsAndBytesConfig(load_in_4bit=True)."""
        mock_tf = _make_transformers_mock()
        with patch(
            "llm_shared.optimization.hf_quantizer._import_transformers",
            return_value=mock_tf,
        ):
            self._bnb_wrapper().preprocess_model()
        mock_tf.BitsAndBytesConfig.assert_called_once_with(load_in_4bit=True)

    # ---- NONE ----

    def test_none_preprocess_returns_device_map(self):
        """No-quantization preprocessing must include device_map key."""
        kwargs = self._none_wrapper().preprocess_model()
        assert "device_map" in kwargs
        assert "quantization_config" not in kwargs

    def test_none_preprocess_includes_torch_dtype(self):
        """No-quantization preprocessing must include torch_dtype when set."""
        kwargs = self._none_wrapper().preprocess_model()
        assert kwargs.get("torch_dtype") == "float16"

    # ---- extra_kwargs propagation ----

    def test_extra_kwargs_propagated(self):
        """extra_kwargs in QuantizerConfig must appear in preprocess_model output."""
        cfg = QuantizerConfig(
            quantization_type=QuantizationType.NONE,
            extra_kwargs={"revision": "main"},
        )
        wrapper = HfQuantizerWrapper(cfg)
        kwargs = wrapper.preprocess_model()
        assert kwargs.get("revision") == "main"


# ---------------------------------------------------------------------------
# TestCheckQuantizedParam
# ---------------------------------------------------------------------------


class TestCheckQuantizedParam:
    """Tests for HfQuantizerWrapper.check_quantized_param()."""

    def _wrapper(self, qtype: QuantizationType) -> HfQuantizerWrapper:
        return HfQuantizerWrapper(QuantizerConfig(quantization_type=qtype))

    # ---- GPTQ ----

    @pytest.mark.parametrize("suffix", sorted(_GPTQ_QUANTIZED_SUFFIXES))
    def test_gptq_recognises_quantized_suffixes(self, suffix: str):
        """GPTQ wrapper must identify known quantized-parameter suffixes."""
        wrapper = self._wrapper(QuantizationType.GPTQ)
        is_q, reason = wrapper.check_quantized_param(f"model.layers.0.self_attn.q_proj{suffix}", None)
        assert is_q is True
        assert suffix in reason

    def test_gptq_non_quantized_param(self):
        """GPTQ wrapper must not flag normal parameters."""
        wrapper = self._wrapper(QuantizationType.GPTQ)
        is_q, _ = wrapper.check_quantized_param("model.embed_tokens.weight", None)
        assert is_q is False

    # ---- AWQ ----

    @pytest.mark.parametrize("suffix", sorted(_AWQ_QUANTIZED_SUFFIXES))
    def test_awq_recognises_quantized_suffixes(self, suffix: str):
        """AWQ wrapper must identify known quantized-parameter suffixes."""
        wrapper = self._wrapper(QuantizationType.AWQ)
        is_q, _ = wrapper.check_quantized_param(f"model.layers.0.mlp.gate_proj{suffix}", None)
        assert is_q is True

    # ---- NONE ----

    def test_none_never_quantized(self):
        """NONE wrapper must return is_quantized=False for all params."""
        wrapper = self._wrapper(QuantizationType.NONE)
        for suffix in (".qweight", ".scales", ".weight", ".bias"):
            is_q, _ = wrapper.check_quantized_param(f"model.layers.0.weight{suffix}", None)
            assert is_q is False


# ---------------------------------------------------------------------------
# TestCreateQuantizedParam
# ---------------------------------------------------------------------------


class TestCreateQuantizedParam:
    """Tests for HfQuantizerWrapper.create_quantized_param()."""

    def test_gptq_quantized_param_passthrough(self):
        """GPTQ create_quantized_param returns original data unchanged."""
        wrapper = HfQuantizerWrapper(QuantizerConfig(quantization_type=QuantizationType.GPTQ))
        sentinel = object()
        result = wrapper.create_quantized_param("model.layers.0.q_proj.qweight", sentinel)
        assert result is sentinel

    def test_awq_quantized_param_passthrough(self):
        """AWQ create_quantized_param returns original data unchanged."""
        wrapper = HfQuantizerWrapper(QuantizerConfig(quantization_type=QuantizationType.AWQ))
        sentinel = object()
        result = wrapper.create_quantized_param("model.layers.0.q_proj.qweight", sentinel)
        assert result is sentinel

    def test_non_quantized_param_passthrough(self):
        """Non-quantized params are always returned unchanged regardless of type."""
        wrapper = HfQuantizerWrapper(QuantizerConfig(quantization_type=QuantizationType.GPTQ))
        sentinel = object()
        result = wrapper.create_quantized_param("model.embed_tokens.weight", sentinel)
        assert result is sentinel


# ---------------------------------------------------------------------------
# TestQuantizedLayerLoader
# ---------------------------------------------------------------------------


class TestQuantizedLayerLoader:
    """Tests for QuantizedLayerLoader.load_layer_with_quantization()."""

    def _loader(self, qtype: QuantizationType) -> QuantizedLayerLoader:
        cfg = QuantizerConfig(quantization_type=qtype)
        wrapper = HfQuantizerWrapper(cfg)
        return QuantizedLayerLoader(wrapper)

    def test_returns_all_params_in_processed(self):
        """Every input param must appear in the returned processed dict."""
        loader = self._loader(QuantizationType.GPTQ)
        params = [
            ("model.layers.0.q_proj.qweight", object()),
            ("model.layers.0.q_proj.scales", object()),
            ("model.layers.0.q_proj.bias", object()),
        ]
        processed, result = loader.load_layer_with_quantization("model.layers.0", params)
        assert set(processed.keys()) == {p[0] for p in params}

    def test_quantized_count_correct_for_gptq(self):
        """LayerLoadResult.quantized_count matches GPTQ suffix hits."""
        loader = self._loader(QuantizationType.GPTQ)
        params = [
            ("model.layers.0.q_proj.qweight", None),  # quantized
            ("model.layers.0.q_proj.scales", None),  # quantized
            ("model.layers.0.q_proj.other_field", None),  # NOT quantized
        ]
        _, result = loader.load_layer_with_quantization("model.layers.0", params)
        assert result.quantized_count == 2
        assert result.param_count == 3

    def test_layer_result_fields(self):
        """LayerLoadResult contains correct metadata."""
        loader = self._loader(QuantizationType.AWQ)
        params = [("model.layers.1.q_proj.qzeros", None)]
        _, result = loader.load_layer_with_quantization("model.layers.1", params)
        assert result.layer_name == "model.layers.1"
        assert isinstance(result, LayerLoadResult)
        assert result.quantization_type == QuantizationType.AWQ

    def test_empty_params_produces_empty_processed(self):
        """An empty parameter list produces an empty processed dict and zero counts."""
        loader = self._loader(QuantizationType.NONE)
        processed, result = loader.load_layer_with_quantization("model.lm_head", [])
        assert processed == {}
        assert result.param_count == 0
        assert result.quantized_count == 0

    def test_none_type_no_quantized_params(self):
        """NONE quantization type: no params classified as quantized."""
        loader = self._loader(QuantizationType.NONE)
        params = [
            ("model.layers.0.weight", object()),
            ("model.layers.0.bias", object()),
        ]
        _, result = loader.load_layer_with_quantization("model.layers.0", params)
        assert result.quantized_count == 0


# ---------------------------------------------------------------------------
# TestMissingLibraryFallback
# ---------------------------------------------------------------------------


class TestMissingLibraryFallback:
    """Tests that ImportError is raised (not swallowed) when libs are absent."""

    def test_gptq_preprocess_raises_on_missing_transformers(self):
        """preprocess_model(GPTQ) must raise ImportError if transformers absent."""
        cfg = QuantizerConfig(quantization_type=QuantizationType.GPTQ)
        wrapper = HfQuantizerWrapper(cfg)

        def _raise(*_a, **_kw):
            raise ImportError("transformers not installed")

        with patch(
            "llm_shared.optimization.hf_quantizer._import_transformers",
            side_effect=_raise,
        ):
            with pytest.raises(ImportError, match="transformers"):
                wrapper.preprocess_model()

    def test_awq_preprocess_raises_on_missing_autoawq(self):
        """preprocess_model(AWQ) must raise ImportError if autoawq absent."""
        cfg = QuantizerConfig(quantization_type=QuantizationType.AWQ)
        wrapper = HfQuantizerWrapper(cfg)
        mock_tf = _make_transformers_mock()

        def _raise(*_a, **_kw):
            raise ImportError("autoawq not installed")

        with (
            patch(
                "llm_shared.optimization.hf_quantizer._import_transformers",
                return_value=mock_tf,
            ),
            patch(
                "llm_shared.optimization.hf_quantizer._import_autoawq",
                side_effect=_raise,
            ),
        ):
            with pytest.raises(ImportError, match="autoawq"):
                wrapper.preprocess_model()

    def test_bnb_preprocess_raises_on_missing_transformers(self):
        """preprocess_model(BNB) must raise ImportError if transformers absent."""
        cfg = QuantizerConfig(quantization_type=QuantizationType.BITSANDBYTES)
        wrapper = HfQuantizerWrapper(cfg)

        def _raise(*_a, **_kw):
            raise ImportError("transformers not installed")

        with patch(
            "llm_shared.optimization.hf_quantizer._import_transformers",
            side_effect=_raise,
        ):
            with pytest.raises(ImportError, match="transformers"):
                wrapper.preprocess_model()


# ---------------------------------------------------------------------------
# TestBitsAndBytesExtraKwargs (#3179)
# ---------------------------------------------------------------------------


class TestBitsAndBytesExtraKwargs:
    """Tests for BitsAndBytes preprocessing with extra_kwargs (#3179).

    Verifies that load_in_4bit / load_in_8bit flow from extra_kwargs into
    BitsAndBytesConfig rather than being hard-coded or accepted as a
    QuantizerConfig field.
    """

    def test_int4_extra_kwargs_calls_bnb_with_load_in_4bit(self):
        """extra_kwargs={"load_in_4bit": True} must set load_in_4bit on BitsAndBytesConfig."""
        mock_tf = _make_transformers_mock()
        cfg = QuantizerConfig(
            quantization_type=QuantizationType.BITSANDBYTES,
            extra_kwargs={"load_in_4bit": True},
        )
        wrapper = HfQuantizerWrapper(cfg)
        with patch(
            "llm_shared.optimization.hf_quantizer._import_transformers",
            return_value=mock_tf,
        ):
            wrapper.preprocess_model()
        mock_tf.BitsAndBytesConfig.assert_called_once_with(load_in_4bit=True)

    def test_int8_extra_kwargs_calls_bnb_with_load_in_8bit(self):
        """extra_kwargs={"load_in_8bit": True} must set load_in_8bit on BitsAndBytesConfig."""
        mock_tf = _make_transformers_mock()
        cfg = QuantizerConfig(
            quantization_type=QuantizationType.BITSANDBYTES,
            extra_kwargs={"load_in_8bit": True},
        )
        wrapper = HfQuantizerWrapper(cfg)
        with patch(
            "llm_shared.optimization.hf_quantizer._import_transformers",
            return_value=mock_tf,
        ):
            wrapper.preprocess_model()
        mock_tf.BitsAndBytesConfig.assert_called_once_with(load_in_8bit=True)

    def test_no_extra_kwargs_defaults_to_load_in_4bit(self):
        """No extra_kwargs must fall back to load_in_4bit=True (default behaviour)."""
        mock_tf = _make_transformers_mock()
        cfg = QuantizerConfig(quantization_type=QuantizationType.BITSANDBYTES)
        wrapper = HfQuantizerWrapper(cfg)
        with patch(
            "llm_shared.optimization.hf_quantizer._import_transformers",
            return_value=mock_tf,
        ):
            wrapper.preprocess_model()
        mock_tf.BitsAndBytesConfig.assert_called_once_with(load_in_4bit=True)

    def test_quantizer_config_rejects_load_in_4bit_field(self):
        """QuantizerConfig must raise TypeError if load_in_4bit is passed directly (#3179)."""
        with pytest.raises(TypeError, match="load_in_4bit"):
            QuantizerConfig(  # type: ignore[call-arg]
                quantization_type=QuantizationType.BITSANDBYTES,
                load_in_4bit=True,
            )
