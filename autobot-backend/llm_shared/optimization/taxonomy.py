# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared element-dtype and weight-compression taxonomies (#13049 C2, C3).

One definition each, for the whole ``llm_shared.optimization`` package. Both are
``str`` enums, so a member compares equal to its raw string and every existing
string-typed field, log line and caller keeps working unchanged.

The architecture-family taxonomy (#13049 C1) is NOT defined here: it lives in
``autobot_shared.model_taxonomy.ArchitectureFamily`` (re-exported by
``llm_shared.types``).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict

from autobot_shared.model_taxonomy import ArchitectureFamily, UnsupportedArchitectureError

from ..model_param_registry import family_for_model_type


class Dtype(str, Enum):
    """Element dtype. ``.value`` is the short spelling used by the KV cache."""

    FP16 = "fp16"
    BF16 = "bf16"
    FP32 = "fp32"

    @property
    def torch_name(self) -> str:
        """The ``torch.<name>`` spelling (``float16`` ...) for the torch boundary."""
        return _TORCH_NAMES[self]

    @property
    def nbytes(self) -> int:
        """Bytes per element."""
        return _BYTES[self]

    @classmethod
    def parse(cls, spelling: str) -> "Dtype":
        """Resolve either vocabulary (``fp16`` or ``float16``); ValueError if unknown."""
        try:
            return _SPELLINGS[spelling]
        except (KeyError, TypeError):
            raise ValueError(f"Unsupported dtype '{spelling}'. Choose from: {sorted(_SPELLINGS)}") from None


_TORCH_NAMES: Dict[Dtype, str] = {
    Dtype.FP16: "float16",
    Dtype.BF16: "bfloat16",
    Dtype.FP32: "float32",
}
_BYTES: Dict[Dtype, int] = {Dtype.FP16: 2, Dtype.BF16: 2, Dtype.FP32: 4}
_SPELLINGS: Dict[str, Dtype] = {
    **{d.value: d for d in Dtype},
    **{name: d for d, name in _TORCH_NAMES.items()},
}


class Compression(str, Enum):
    """Weight compression mode shared by ``LayerInferenceConfig`` and ``PipelineConfig``."""

    BIT4 = "4bit"
    BIT8 = "8bit"
    NONE = "none"

    @classmethod
    def validate(cls, value: str) -> str:
        """Return ``value`` unchanged when it is a known mode, else raise ValueError."""
        if value not in {m.value for m in cls}:
            raise ValueError(f"compression must be one of {sorted(m.value for m in cls)}, got '{value}'")
        return value


@dataclass(frozen=True)
class LayerLayout:
    """Module names a checkpoint family uses for its layer stack, embedding and head."""

    layer_prefix: str
    embedding: str
    head: str


#: Architectures that nest transformer blocks under ``transformer.`` and name
#: their token embedding ``wte`` (#13032).
GPT2_STYLE_MODEL_TYPES = frozenset({"gpt2", "gptj", "gpt_neo", "gpt_neox"})
_GPT2_LAYOUT = LayerLayout("transformer.h.", "transformer.wte", "lm_head")
#: LLaMA, Mistral, Falcon, Qwen, Gemma, Phi, etc. Also what every unrecognised
#: ``model_type`` resolves to (unchanged fallback).
_LLAMA_LAYOUT = LayerLayout("model.layers.", "model.embed_tokens", "lm_head")
#: Families whose checkpoints are a transformer-style layer stack. Every other
#: *known* family (state-space, linear-attention, hybrid) has no such layout.
_LAYERED_FAMILIES = frozenset({ArchitectureFamily.TRANSFORMER, ArchitectureFamily.MOE})


def layer_layout_for(model_type: str) -> LayerLayout:
    """Layer layout for a lower-cased HuggingFace ``model_type``.

    Raises ``UnsupportedArchitectureError`` for a known non-transformer family
    (mamba, jamba, rwkv, retnet, ...): layer-by-layer loading would otherwise
    silently apply LLaMA names to a checkpoint that has none of them (#13049 C1).
    An unrecognised ``model_type`` keeps the LLaMA fallback.
    """
    family = family_for_model_type(model_type)
    if family is not None and family not in _LAYERED_FAMILIES:
        raise UnsupportedArchitectureError(
            model_type,
            f"model_type '{model_type}' is a {family.value} architecture; layer-by-layer "
            "inference only supports transformer-style layer stacks",
        )
    return _GPT2_LAYOUT if model_type in GPT2_STYLE_MODEL_TYPES else _LLAMA_LAYOUT
