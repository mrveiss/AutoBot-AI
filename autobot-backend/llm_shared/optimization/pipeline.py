# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
End-to-end LayerInference pipeline orchestrator.

Chains all optimization modules into a usable generation pipeline in the
correct order:

  1. Inspect model architecture via empty-weight config loading.
  2. Detect quantization strategy (HfQuantizerWrapper / bitsandbytes config).
  3. Select attention backend (BetterTransformer / SDPA / vanilla).
  4. Create KV cache with MetaDeviceEvictionManager for layer-by-layer passes.
  5. Execute layer-by-layer generation with GPU memory cleanup between layers.

Use :class:`LayerInferencePipeline` for a single-object interface.  Call
:meth:`prepare` once per model, then :meth:`execute` for each generation
request.

Issue #3140: Assemble end-to-end LayerInference pipeline.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

from .attention_backend import (
    AttentionBackendSelector,
)
from .attention_backend import ModelConfig as AttentionModelConfig
from .hf_quantizer import HfQuantizerWrapper
from .kv_cache import KVCacheConfig, KVCacheManager, LayerKVCache
from .layer_inference import LayerInferenceConfig, LayerInferenceEngine
from .meta_eviction import MetaDeviceEvictionManager, clean_memory

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Pipeline configuration
# ---------------------------------------------------------------------------

#: Default KV-cache head dimension when the model config does not expose it.
_DEFAULT_HEAD_DIM = 128

#: Default number of KV heads when the model config does not expose it.
_DEFAULT_NUM_HEADS = 32


@dataclass
class PipelineConfig:
    """Configuration for :class:`LayerInferencePipeline`.

    Issue #3140.

    Attributes:
        model_name: HuggingFace model identifier or local path.
        device: Torch device string, e.g. ``"cuda"`` or ``"cpu"``.
        compression: Weight compression hint passed to :class:`LayerInferenceConfig`.
        max_seq_len: Maximum sequence length to support.
        batch_size: Batch size for cache allocation.
        cache_dir: Optional directory for cached model weights.
    """

    model_name: str
    device: str = "cpu"
    compression: str = "none"
    max_seq_len: int = 2048
    batch_size: int = 1
    cache_dir: str | None = None

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not self.model_name:
            raise ValueError("model_name must not be empty")
        if self.max_seq_len < 1:
            raise ValueError("max_seq_len must be >= 1")
        if self.batch_size < 1:
            raise ValueError("batch_size must be >= 1")


# ---------------------------------------------------------------------------
# Pipeline state produced by prepare()
# ---------------------------------------------------------------------------


@dataclass
class PreparedPipeline:
    """Fully assembled inference components returned by :meth:`LayerInferencePipeline.prepare`.

    Issue #3140.

    Attributes:
        engine: Configured :class:`LayerInferenceEngine`.
        quantizer: :class:`HfQuantizerWrapper` built from the model config.
        attention_backend: Selected backend enum value from :mod:`attention_backend`.
        kv_cache: Allocated :class:`LayerKVCache` sized for the model.
        eviction_manager: :class:`MetaDeviceEvictionManager` tracking evictions.
        model_cfg: Raw model configuration dictionary.
        from_pretrained_kwargs: kwargs for ``AutoModelForCausalLM.from_pretrained``.
    """

    engine: LayerInferenceEngine
    quantizer: HfQuantizerWrapper
    attention_backend: Any
    kv_cache: LayerKVCache
    eviction_manager: MetaDeviceEvictionManager
    model_cfg: Dict[str, Any]
    from_pretrained_kwargs: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Main pipeline class
# ---------------------------------------------------------------------------


class LayerInferencePipeline:
    """End-to-end LayerInference pipeline that chains all optimization modules.

    Usage::

        pipeline = LayerInferencePipeline(PipelineConfig(model_name="..."))
        prepared = pipeline.prepare()
        result = pipeline.execute("Hello, world!", prepared, max_new_tokens=64)

    Issue #3140.

    Args:
        config: Pipeline configuration.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self._config = config
        self._attn_selector = AttentionBackendSelector()
        self._kv_manager = KVCacheManager()
        logger.info(
            "LayerInferencePipeline created: model=%s device=%s",
            config.model_name,
            config.device,
        )

    @property
    def config(self) -> PipelineConfig:
        """Pipeline configuration."""
        return self._config

    def prepare(self) -> PreparedPipeline:
        """Inspect model and assemble all inference components.

        Steps:
          1. Build :class:`LayerInferenceEngine` and load the model config.
          2. Detect quantization and build :class:`HfQuantizerWrapper`.
          3. Select the attention backend for the model architecture.
          4. Allocate a :class:`LayerKVCache` sized from the model config.
          5. Create a fresh :class:`MetaDeviceEvictionManager`.

        Issue #3140.

        Returns:
            :class:`PreparedPipeline` holding all assembled components.

        Raises:
            ImportError: If transformers is not installed.
            OSError: If the model config cannot be fetched.
        """
        t0 = time.monotonic()
        engine = self._build_engine()
        model_cfg = engine.load_model_config(self._config.model_name)

        quantizer = self._try_build_quantizer(model_cfg)
        attn_backend = self._try_select_attention(model_cfg)
        kv_cache = self._try_allocate_kv_cache(model_cfg)
        eviction_manager = MetaDeviceEvictionManager()

        from_pretrained_kwargs = {}
        if quantizer is not None:
            from_pretrained_kwargs = quantizer.preprocess_model()

        prepared = PreparedPipeline(
            engine=engine,
            quantizer=quantizer,
            attention_backend=attn_backend,
            kv_cache=kv_cache,
            eviction_manager=eviction_manager,
            model_cfg=model_cfg,
            from_pretrained_kwargs=from_pretrained_kwargs,
        )
        self._log_prepare_result(prepared, time.monotonic() - t0)
        return prepared

    def execute(
        self,
        prompt: str,
        prepared: PreparedPipeline,
        max_new_tokens: int = 64,
    ) -> str:
        """Generate text using the assembled pipeline.

        Delegates to :meth:`LayerInferenceEngine.generate` and flushes GPU
        memory via :func:`clean_memory` after the generation loop.

        Issue #3140.

        Args:
            prompt: Input text to continue.
            prepared: Components returned by :meth:`prepare`.
            max_new_tokens: Maximum new tokens to produce.

        Returns:
            Generated text string (prompt not included).
        """
        logger.info(
            "LayerInferencePipeline.execute: model=%s max_new_tokens=%d",
            self._config.model_name,
            max_new_tokens,
        )
        result = prepared.engine.generate(prompt, max_new_tokens=max_new_tokens)
        clean_memory()
        logger.debug("LayerInferencePipeline.execute: memory cleaned after generation")
        return result

    def _log_prepare_result(self, prepared: PreparedPipeline, elapsed: float) -> None:
        """Log the outcome of prepare() in a single info line."""
        quant_type = "none"
        if prepared.quantizer is not None:
            quant_type = str(getattr(prepared.quantizer, "_config", None))
        kv_layers = prepared.kv_cache.config.num_layers if prepared.kv_cache else 0
        logger.info(
            "Pipeline.prepare: done in %.3fs quant=%s attn=%s kv_layers=%d",
            elapsed,
            quant_type,
            prepared.attention_backend,
            kv_layers,
        )

    def _try_build_quantizer(self, model_cfg):
        """Build quantizer with graceful fallback to None."""
        try:
            return self._build_quantizer(model_cfg)
        except Exception as exc:
            logger.warning("Quantizer unavailable, skipping: %s", exc)
            return None

    def _try_select_attention(self, model_cfg):
        """Select attention backend with graceful fallback to None."""
        try:
            return self._select_attention_backend(model_cfg)
        except Exception as exc:
            logger.warning("Attention backend selection failed, using default: %s", exc)
            return None

    def _try_allocate_kv_cache(self, model_cfg):
        """Allocate KV cache with graceful fallback to None."""
        try:
            return self._allocate_kv_cache(model_cfg)
        except Exception as exc:
            logger.warning("KV cache allocation failed, skipping: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Private construction helpers (each <=30 lines)
    # ------------------------------------------------------------------

    def _build_engine(self) -> LayerInferenceEngine:
        """Construct a :class:`LayerInferenceEngine` from pipeline config.

        Issue #3140.
        """
        engine_cfg = LayerInferenceConfig(
            model_name=self._config.model_name,
            compression=self._config.compression,
            max_seq_len=self._config.max_seq_len,
            batch_size=self._config.batch_size,
            device=self._config.device,
            cache_dir=self._config.cache_dir,
        )
        return LayerInferenceEngine(engine_cfg)

    def _build_quantizer(self, model_cfg: Dict[str, Any]) -> HfQuantizerWrapper:
        """Auto-detect quantization from model config and return wrapper.

        Issue #3140.
        """
        quantizer = HfQuantizerWrapper.from_config(
            model_cfg,
            device_map="auto" if self._config.device == "cuda" else "cpu",
        )
        logger.debug(
            "Quantizer built: type=%s",
            quantizer._config.quantization_type,
        )
        return quantizer

    def _select_attention_backend(self, model_cfg: Dict[str, Any]) -> Any:
        """Select the best attention backend for the model architecture.

        Issue #3140.
        """
        attn_model_cfg = AttentionModelConfig(
            model_name=self._config.model_name,
            model_type=str(model_cfg.get("model_type", "")),
        )
        backend = self._attn_selector.select_backend(attn_model_cfg)
        logger.debug("Attention backend selected: %s", backend)
        return backend

    def _derive_kv_dims(self, model_cfg: Dict[str, Any]) -> Dict[str, int]:
        """Extract KV cache dimensions from model config with safe defaults.

        Issue #3140.
        """
        num_layers = model_cfg.get("num_hidden_layers") or model_cfg.get("n_layer") or model_cfg.get("num_layers") or 1
        num_heads = (
            model_cfg.get("num_key_value_heads")
            or model_cfg.get("num_attention_heads")
            or model_cfg.get("n_head")
            or _DEFAULT_NUM_HEADS
        )
        hidden_size = model_cfg.get("hidden_size") or model_cfg.get("n_embd") or (_DEFAULT_HEAD_DIM * int(num_heads))
        head_dim = int(hidden_size) // int(num_heads)
        return {
            "num_layers": int(num_layers),
            "num_heads": int(num_heads),
            "head_dim": max(1, head_dim),
        }

    def _allocate_kv_cache(self, model_cfg: Dict[str, Any]) -> LayerKVCache:
        """Allocate a :class:`LayerKVCache` sized for the model.

        Issue #3140.
        """
        dims = self._derive_kv_dims(model_cfg)
        kv_cfg = KVCacheConfig(
            num_layers=dims["num_layers"],
            num_heads=dims["num_heads"],
            head_dim=dims["head_dim"],
            max_seq_len=self._config.max_seq_len,
            dtype="fp16",
            device=self._config.device,
            batch_size=self._config.batch_size,
        )
        cache = self._kv_manager.create_cache(kv_cfg)
        logger.debug(
            "KV cache allocated: layers=%d heads=%d head_dim=%d",
            dims["num_layers"],
            dims["num_heads"],
            dims["head_dim"],
        )
        return cache


__all__ = [
    "LayerInferencePipeline",
    "PipelineConfig",
    "PreparedPipeline",
]
