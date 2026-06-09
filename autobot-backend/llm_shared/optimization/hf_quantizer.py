# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
HfQuantizer integration for pre-quantized GPTQ/AWQ models.

Provides detection, wrapping, and per-parameter loading for models that are
already stored in a quantized format (GPTQ, AWQ, BitsAndBytes).  Heavy
third-party libraries (transformers, auto_gptq, autoawq) are imported lazily
so the module loads cleanly even when those packages are absent.

Issue #1954: HfQuantizer integration for pre-quantized GPTQ/AWQ models.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lazy import helpers
# ---------------------------------------------------------------------------


def _import_transformers() -> Any:
    """Lazily import transformers; raises ImportError with guidance if absent."""
    try:
        import transformers  # noqa: PLC0415

        return transformers
    except ImportError as exc:
        raise ImportError(
            "transformers is required for HfQuantizer support. " "Install with: pip install transformers>=4.40.0"
        ) from exc


def _import_auto_gptq() -> Any:
    """Lazily import auto_gptq; raises ImportError with guidance if absent."""
    try:
        import auto_gptq  # noqa: PLC0415

        return auto_gptq
    except ImportError as exc:
        raise ImportError(
            "auto_gptq is required for GPTQ model support. " "Install with: pip install auto-gptq"
        ) from exc


def _import_autoawq() -> Any:
    """Lazily import autoawq; raises ImportError with guidance if absent."""
    try:
        import awq  # noqa: PLC0415

        return awq
    except ImportError as exc:
        raise ImportError("autoawq is required for AWQ model support. " "Install with: pip install autoawq") from exc


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class QuantizationType(str, Enum):
    """Quantization format used by a pre-quantized model.

    Values map to the strings found in HuggingFace model config files under
    the ``quantization_config.quant_type`` or ``quantization_config.load_in_*``
    keys.
    """

    GPTQ = "gptq"
    AWQ = "awq"
    BITSANDBYTES = "bitsandbytes"
    NONE = "none"


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def detect_quantization(model_config: Dict[str, Any]) -> QuantizationType:
    """Detect the quantization type from a HuggingFace model configuration dict.

    The function inspects the ``quantization_config`` sub-dict (populated when
    a model is saved with ``save_pretrained`` after quantization) as well as the
    top-level ``model_type`` field as a secondary signal.

    Args:
        model_config: The model's configuration dictionary.  Typically loaded
            from ``config.json`` via ``AutoConfig.from_pretrained(...).to_dict()``.

    Returns:
        The detected QuantizationType, or QuantizationType.NONE when no
        recognisable quantization configuration is present.
    """
    quant_cfg: Dict[str, Any] = model_config.get("quantization_config", {}) or {}

    if not quant_cfg:
        logger.debug("No quantization_config key found — treating as NONE")
        return QuantizationType.NONE

    quant_type: str = str(quant_cfg.get("quant_type", "")).lower()
    bits: int = int(quant_cfg.get("bits", 0))

    detected = _detect_from_quant_config(quant_cfg, quant_type, bits)
    logger.info(
        "Detected quantization type: %s (bits=%d, quant_type=%r)",
        detected,
        bits,
        quant_type,
    )
    return detected


def _detect_from_quant_config(
    quant_cfg: Dict[str, Any],
    quant_type: str,
    bits: int,
) -> QuantizationType:
    """Determine QuantizationType from the parsed quantization_config fields.

    Args:
        quant_cfg: The raw quantization_config dictionary.
        quant_type: Lower-cased value of quant_cfg['quant_type'] (may be empty).
        bits: Integer bits value from quant_cfg['bits'] (0 if absent).

    Returns:
        The matched QuantizationType.
    """
    # Explicit quant_type field is the most reliable signal
    if "gptq" in quant_type:
        return QuantizationType.GPTQ
    if "awq" in quant_type:
        return QuantizationType.AWQ

    # BitsAndBytes uses load_in_4bit / load_in_8bit keys
    if quant_cfg.get("load_in_4bit") or quant_cfg.get("load_in_8bit"):
        return QuantizationType.BITSANDBYTES

    # Some GPTQ configs omit quant_type and only have bits + group_size
    if bits in (2, 3, 4, 8) and "group_size" in quant_cfg:
        logger.debug("Inferred GPTQ from bits=%d + group_size presence", bits)
        return QuantizationType.GPTQ

    return QuantizationType.NONE


# ---------------------------------------------------------------------------
# HfQuantizerWrapper
# ---------------------------------------------------------------------------


@dataclass
class QuantizerConfig:
    """Configuration for HfQuantizerWrapper.

    Attributes:
        quantization_type: The quantization format to target.
        device_map: HuggingFace device_map string (e.g. ``"auto"``).
        trust_remote_code: Whether to trust remote model code.
        torch_dtype: Optional torch dtype string (e.g. ``"float16"``).
    """

    quantization_type: QuantizationType = QuantizationType.NONE
    device_map: str = "auto"
    trust_remote_code: bool = False
    torch_dtype: str | None = "float16"
    extra_kwargs: Dict[str, Any] = field(default_factory=dict)


class HfQuantizerWrapper:
    """Wrapper that applies the correct HuggingFace quantizer for a model config.

    Use :meth:`from_config` to construct an instance from a raw model config
    dictionary.  Call :meth:`preprocess_model` to obtain the ``from_pretrained``
    kwargs needed to load the quantized model with the appropriate quantizer
    activated.

    Issue #1954.
    """

    def __init__(self, config: QuantizerConfig) -> None:
        """Initialise the wrapper.

        Args:
            config: Quantizer configuration controlling loading behaviour.
        """
        self._config = config
        logger.debug("HfQuantizerWrapper initialised for %s", config.quantization_type)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, model_config: Dict[str, Any], **overrides: Any) -> "HfQuantizerWrapper":
        """Build a wrapper by auto-detecting quantization from model_config.

        Args:
            model_config: Model configuration dict (e.g. from AutoConfig).
            **overrides: Optional QuantizerConfig field overrides.

        Returns:
            HfQuantizerWrapper ready to preprocess the model.
        """
        quant_type = detect_quantization(model_config)
        cfg = QuantizerConfig(quantization_type=quant_type, **overrides)
        return cls(cfg)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def preprocess_model(self) -> Dict[str, Any]:
        """Return ``from_pretrained`` kwargs for loading this quantized model.

        The returned dict should be unpacked into ``AutoModelForCausalLM.from_pretrained``
        (or equivalent).  For GPTQ/AWQ models this sets the appropriate
        ``quantization_config`` object; for BitsAndBytes it returns the standard
        ``BitsAndBytesConfig``; for NONE it returns minimal loading kwargs.

        Returns:
            Dict of kwargs suitable for ``from_pretrained``.

        Raises:
            ImportError: If the required quantization library is not installed.
        """
        handlers = {
            QuantizationType.GPTQ: self._preprocess_gptq,
            QuantizationType.AWQ: self._preprocess_awq,
            QuantizationType.BITSANDBYTES: self._preprocess_bitsandbytes,
            QuantizationType.NONE: self._preprocess_none,
        }
        handler = handlers[self._config.quantization_type]
        kwargs = handler()
        if self._config.quantization_type == QuantizationType.BITSANDBYTES:
            # load_in_4bit / load_in_8bit are already consumed into
            # BitsAndBytesConfig inside _preprocess_bitsandbytes.  Passing
            # them again as bare top-level kwargs alongside quantization_config
            # causes HuggingFace to raise ValueError.  Strip them here so any
            # other (non-BNB) extra_kwargs still flow through.
            passthrough = {
                k: v for k, v in self._config.extra_kwargs.items() if k not in ("load_in_4bit", "load_in_8bit")
            }
            kwargs.update(passthrough)
        else:
            kwargs.update(self._config.extra_kwargs)
        logger.info(
            "preprocess_model produced kwargs for %s: %s",
            self._config.quantization_type,
            list(kwargs.keys()),
        )
        return kwargs

    def check_quantized_param(self, param_name: str, param_data: Any) -> Tuple[bool, str]:
        """Check whether a named parameter belongs to a quantized layer.

        Args:
            param_name: Fully-qualified parameter name (e.g. ``"model.layers.0.self_attn.q_proj.qweight"``).
            param_data: The raw tensor or value for the parameter.

        Returns:
            A ``(is_quantized, reason)`` tuple.  ``is_quantized`` is True when
            the parameter name matches a known quantized-layer suffix for the
            configured quantization type.
        """
        checkers = {
            QuantizationType.GPTQ: _GPTQ_QUANTIZED_SUFFIXES,
            QuantizationType.AWQ: _AWQ_QUANTIZED_SUFFIXES,
            QuantizationType.BITSANDBYTES: _BNB_QUANTIZED_SUFFIXES,
            QuantizationType.NONE: set(),
        }
        suffixes = checkers.get(self._config.quantization_type, set())
        for suffix in suffixes:
            if param_name.endswith(suffix):
                return (
                    True,
                    f"param matches quantized suffix '{suffix}' for {self._config.quantization_type}",
                )
        return False, "param does not match any quantized suffix"

    def create_quantized_param(self, param_name: str, param_data: Any) -> Any:
        """Wrap or convert a raw parameter for use in a quantized layer.

        For GPTQ/AWQ this is typically a no-op because the loaders handle
        dequantization internally.  The method exists so callers have a
        uniform interface regardless of quantization type.

        Args:
            param_name: Fully-qualified parameter name.
            param_data: The parameter data (tensor or buffer).

        Returns:
            The (possibly wrapped) parameter data.
        """
        is_quantized, reason = self.check_quantized_param(param_name, param_data)
        if not is_quantized:
            logger.debug("create_quantized_param: %s — passing through (%s)", param_name, reason)
            return param_data

        creator = {
            QuantizationType.GPTQ: _create_gptq_param,
            QuantizationType.AWQ: _create_awq_param,
            QuantizationType.BITSANDBYTES: _create_bnb_param,
        }.get(self._config.quantization_type)

        if creator is None:
            return param_data

        result = creator(param_name, param_data)
        logger.debug(
            "create_quantized_param: %s processed for %s",
            param_name,
            self._config.quantization_type,
        )
        return result

    # ------------------------------------------------------------------
    # Private preprocessing helpers
    # ------------------------------------------------------------------

    def _preprocess_gptq(self) -> Dict[str, Any]:
        """Build from_pretrained kwargs for GPTQ models.

        Requires: transformers >= 4.40 (GPTQConfig is bundled).
        """
        transformers = _import_transformers()
        gptq_config = transformers.GPTQConfig(bits=4, disable_exllama=False)
        return {
            "quantization_config": gptq_config,
            "device_map": self._config.device_map,
            "trust_remote_code": self._config.trust_remote_code,
        }

    def _preprocess_awq(self) -> Dict[str, Any]:
        """Build from_pretrained kwargs for AWQ models.

        Requires: autoawq package.
        """
        awq = _import_autoawq()  # validates library is present
        _ = awq  # library import validates availability; kwargs come from transformers
        transformers = _import_transformers()
        awq_config = transformers.AwqConfig(version="gemm")
        return {
            "quantization_config": awq_config,
            "device_map": self._config.device_map,
            "trust_remote_code": self._config.trust_remote_code,
        }

    def _preprocess_bitsandbytes(self) -> Dict[str, Any]:
        """Build from_pretrained kwargs for BitsAndBytes models.

        Reads ``load_in_4bit`` / ``load_in_8bit`` from ``extra_kwargs`` so
        callers can distinguish int4 from int8 without adding fields to
        :class:`QuantizerConfig`.  Defaults to ``load_in_4bit=True`` when
        neither key is present (original behaviour).
        """
        transformers = _import_transformers()
        bnb_kwargs: Dict[str, Any] = {"load_in_4bit": True}
        if self._config.extra_kwargs.get("load_in_8bit"):
            bnb_kwargs = {"load_in_8bit": True}
        elif self._config.extra_kwargs.get("load_in_4bit") is not None:
            bnb_kwargs = {"load_in_4bit": bool(self._config.extra_kwargs["load_in_4bit"])}
        bnb_config = transformers.BitsAndBytesConfig(**bnb_kwargs)
        return {
            "quantization_config": bnb_config,
            "device_map": self._config.device_map,
            "trust_remote_code": self._config.trust_remote_code,
        }

    def _preprocess_none(self) -> Dict[str, Any]:
        """Return base kwargs when no quantization is applied."""
        kwargs: Dict[str, Any] = {"device_map": self._config.device_map}
        if self._config.torch_dtype:
            kwargs["torch_dtype"] = self._config.torch_dtype
        return kwargs


# ---------------------------------------------------------------------------
# Known quantized parameter suffixes (used by check_quantized_param)
# ---------------------------------------------------------------------------

# GPTQ packs weights into `qweight` and stores scales/zeros alongside
_GPTQ_QUANTIZED_SUFFIXES = frozenset({".qweight", ".qzeros", ".scales", ".g_idx", ".bias"})

# AWQ uses similar packed representation
_AWQ_QUANTIZED_SUFFIXES = frozenset({".qweight", ".qzeros", ".scales", ".bias"})

# BitsAndBytes stores quantization state in these sub-tensors
_BNB_QUANTIZED_SUFFIXES = frozenset({".weight", ".bias", ".SCB", ".weight_format"})


# ---------------------------------------------------------------------------
# Per-parameter creation helpers
# ---------------------------------------------------------------------------


def _create_gptq_param(param_name: str, param_data: Any) -> Any:
    """Pass GPTQ quantized parameters through unchanged.

    GPTQ loaders (ExLlama / auto_gptq) handle dequantization internally.
    This hook exists for uniformity and future extension.

    Args:
        param_name: Parameter name.
        param_data: Raw parameter data.

    Returns:
        Unchanged param_data.
    """
    logger.debug("GPTQ param pass-through: %s", param_name)
    return param_data


def _create_awq_param(param_name: str, param_data: Any) -> Any:
    """Pass AWQ quantized parameters through unchanged.

    AWQ loaders handle dequantization internally.

    Args:
        param_name: Parameter name.
        param_data: Raw parameter data.

    Returns:
        Unchanged param_data.
    """
    logger.debug("AWQ param pass-through: %s", param_name)
    return param_data


def _create_bnb_param(param_name: str, param_data: Any) -> Any:
    """Pass BitsAndBytes quantized parameters through unchanged.

    BnB handles quantization state management via its own layer types.

    Args:
        param_name: Parameter name.
        param_data: Raw parameter data.

    Returns:
        Unchanged param_data.
    """
    logger.debug("BitsAndBytes param pass-through: %s", param_name)
    return param_data


# ---------------------------------------------------------------------------
# QuantizedLayerLoader
# ---------------------------------------------------------------------------


@dataclass
class LayerLoadResult:
    """Result of loading a single quantized layer.

    Attributes:
        layer_name: The layer/module name that was processed.
        param_count: Number of parameters processed.
        quantized_count: Number of parameters identified as quantized.
        quantization_type: Quantization format used.
    """

    layer_name: str
    param_count: int
    quantized_count: int
    quantization_type: QuantizationType


class QuantizedLayerLoader:
    """Per-layer parameter handler for pre-quantized models.

    Iterates over named parameters in a model layer and applies the correct
    ``create_quantized_param`` path for each one.  Designed to be called inside
    a custom ``state_dict`` loading hook.

    Issue #1954.
    """

    def __init__(self, wrapper: HfQuantizerWrapper) -> None:
        """Initialise with a pre-configured HfQuantizerWrapper.

        Args:
            wrapper: Wrapper that knows the target quantization type.
        """
        self._wrapper = wrapper

    def load_layer_with_quantization(
        self,
        layer_name: str,
        named_params: List[Tuple[str, Any]],
    ) -> Tuple[Dict[str, Any], LayerLoadResult]:
        """Process all named parameters belonging to a single layer.

        Args:
            layer_name: Human-readable layer identifier (e.g. ``"model.layers.0"``).
            named_params: List of ``(param_name, param_data)`` pairs for the layer.

        Returns:
            A tuple of:
            - ``processed``: dict mapping param_name to processed parameter.
            - ``result``: :class:`LayerLoadResult` describing what happened.
        """
        processed: Dict[str, Any] = {}
        quantized_count = 0

        for param_name, param_data in named_params:
            is_quantized, _ = self._wrapper.check_quantized_param(param_name, param_data)
            if is_quantized:
                quantized_count += 1
            processed[param_name] = self._wrapper.create_quantized_param(param_name, param_data)

        result = LayerLoadResult(
            layer_name=layer_name,
            param_count=len(named_params),
            quantized_count=quantized_count,
            quantization_type=self._wrapper._config.quantization_type,
        )
        logger.debug(
            "Layer %s: %d params, %d quantized (%s)",
            layer_name,
            result.param_count,
            result.quantized_count,
            result.quantization_type,
        )
        return processed, result


__all__ = [
    # Enumerations
    "QuantizationType",
    # Detection
    "detect_quantization",
    # Wrapper
    "HfQuantizerWrapper",
    "QuantizerConfig",
    # Loader
    "QuantizedLayerLoader",
    "LayerLoadResult",
]
