# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Equivalence of the shared taxonomies to the tables they replaced (#13049)."""

import pytest

from ..model_param_registry import _MODEL_TYPE_MAP
from .kv_cache import KVCacheConfig
from .layer_inference import (
    LayerInferenceConfig,
    _embedding_name_for_arch,
    _head_name_for_arch,
    _layer_prefix_for_arch,
)
from .pipeline import PipelineConfig
from .taxonomy import Compression, Dtype

#: The kv_cache._DTYPE_BYTES literal as it stood before #13049, frozen here.
_OLD_DTYPE_BYTES = {"fp16": 2, "bf16": 2, "fp32": 4, "float16": 2, "bfloat16": 2, "float32": 4}
_OLD_COMPRESSIONS = ("4bit", "8bit", "none")
_BAD_DTYPES = ("int8", "", "FP16", "fp64", "float64", " fp16", None)


def _kv(dtype):
    return KVCacheConfig(num_layers=1, num_heads=1, head_dim=1, max_seq_len=1, dtype=dtype)


@pytest.mark.parametrize(("spelling", "nbytes"), sorted(_OLD_DTYPE_BYTES.items()))
def test_every_old_spelling_keeps_its_width_and_stays_as_given(spelling, nbytes):
    cfg = _kv(spelling)
    assert cfg.dtype == spelling and cfg.dtype_bytes == nbytes
    assert Dtype.parse(spelling).nbytes == nbytes


@pytest.mark.parametrize("bad", _BAD_DTYPES)
def test_every_old_rejection_is_still_rejected_with_the_same_message(bad):
    expected = f"Unsupported dtype '{bad}'. Choose from: {sorted(_OLD_DTYPE_BYTES)}"
    with pytest.raises(ValueError) as exc:
        _kv(bad)
    assert str(exc.value) == expected


def test_the_stored_values_are_unchanged():
    assert [d.value for d in Dtype] == ["fp16", "bf16", "fp32"]
    assert [d.torch_name for d in Dtype] == ["float16", "bfloat16", "float32"]
    assert [c.value for c in Compression] == ["4bit", "8bit", "none"]


@pytest.mark.parametrize("mode", _OLD_COMPRESSIONS)
def test_pipeline_accepts_every_mode_layer_inference_accepts(mode):
    assert PipelineConfig(model_name="m", compression=mode).compression == mode


def test_contrast_pair_pipeline_rejects_at_the_field_the_caller_set():
    PipelineConfig(model_name="m", compression="8bit")
    with pytest.raises(ValueError, match=r"compression must be one of \['4bit', '8bit', 'none'\], got 'fp4'"):
        PipelineConfig(model_name="m", compression="fp4")


# --- layer-name layout (#13049 C1): frozen pre-refactor behaviour -------------------------

_OLD_GPT2_STYLE = frozenset({"gpt2", "gptj", "gpt_neo", "gpt_neox"})


def _old_layout(model_type):
    if model_type in _OLD_GPT2_STYLE:
        return "transformer.h.", "transformer.wte", "lm_head"
    return "model.layers.", "model.embed_tokens", "lm_head"


#: Every model_type the registry classifies, plus unrecognised and edge spellings.
_MODEL_TYPE_CORPUS = sorted(
    set(_MODEL_TYPE_MAP) | _OLD_GPT2_STYLE | {"", "novelarch", "GPT2", "gpt-neox", "mamba", "gpt2 "}
)


@pytest.mark.parametrize("model_type", _MODEL_TYPE_CORPUS)
def test_layout_is_identical_for_every_known_model_type(model_type):
    got = (
        _layer_prefix_for_arch(model_type),
        _embedding_name_for_arch(model_type),
        _head_name_for_arch(model_type),
    )
    assert got == _old_layout(model_type)


def test_contrast_pair_gpt2_style_differs_from_llama_style():
    assert _layer_prefix_for_arch("gpt2") != _layer_prefix_for_arch("llama")


@pytest.mark.parametrize("mode", ["4bit", "8bit", "none", "fp4", "", "NONE", "4-bit"])
def test_layer_inference_compression_accepts_and_rejects_as_before(mode):
    ok = mode in _OLD_COMPRESSIONS
    if ok:
        assert LayerInferenceConfig(model_name="m", compression=mode).compression == mode
        return
    with pytest.raises(ValueError) as exc:
        LayerInferenceConfig(model_name="m", compression=mode)
    assert str(exc.value) == f"compression must be one of {sorted(_OLD_COMPRESSIONS)}, got '{mode}'"
