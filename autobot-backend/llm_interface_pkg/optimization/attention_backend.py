# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Attention backend selector with tiered fallback chain.

Selects and applies the best available attention backend for a given model
and hardware environment.  Three tiers are tried in order:

  Tier 1 — BetterTransformer  (optimum)
  Tier 2 — SDPA               (torch >= 2.0)
  Tier 3 — Vanilla            (always available)

A compile-time blocklist prevents BetterTransformer from being applied to
model families that are known to be incompatible.  Each tier catches
exceptions, frees GPU memory, and falls through to the next tier so callers
always receive a usable backend.

Heavy third-party libraries (optimum, torch) are imported lazily so the
module loads cleanly even when those packages are absent.

Issue #1951: Attention backend fallback chain.
"""

import gc
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy import helpers
# ---------------------------------------------------------------------------


def _import_torch() -> Any:
    """Lazily import torch; raises ImportError with guidance if absent."""
    try:
        import torch  # noqa: PLC0415

        return torch
    except ImportError as exc:
        raise ImportError(
            "torch is required for attention backend selection. "
            "Install with: pip install torch>=2.0.0"
        ) from exc


def _import_better_transformer() -> Any:
    """Lazily import BetterTransformer from optimum; returns None if absent."""
    try:
        from optimum.bettertransformer import BetterTransformer  # noqa: PLC0415

        return BetterTransformer
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class AttentionBackend(str, Enum):
    """Available attention backend tiers.

    Values reflect capability tiers from highest (fastest) to lowest (most
    compatible).  The string values are stable identifiers safe for logging
    and serialisation.
    """

    BETTER_TRANSFORMER = "better_transformer"
    SDPA = "sdpa"
    VANILLA = "vanilla"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class ModelConfig:
    """Minimal model description used for backend selection.

    Attributes:
        model_name: Repository slug or local path (e.g. ``mistralai/Mixtral-8x7B``).
        model_type: Architecture identifier as reported by the model config
            (e.g. ``mixtral``, ``mistral``, ``llama``).
        torch_dtype: Torch dtype string (e.g. ``float16``, ``bfloat16``).
            None means the model default will be used.
    """

    model_name: str = ""
    model_type: str = ""
    torch_dtype: Optional[str] = None
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------


class AttentionBackendSelector:
    """Select and apply the best available attention backend for a model.

    Selection follows a strict tier order:
      1. BetterTransformer  (requires ``optimum``, blocked for some models)
      2. SDPA               (requires ``torch >= 2.0``)
      3. Vanilla            (always available)

    Each ``select_backend`` call is stateless; the same selector instance can
    be reused for multiple models without side-effects.

    Issue #1951.
    """

    # Model families known to be incompatible with BetterTransformer.
    # Entries are matched case-insensitively against ModelConfig.model_type
    # and ModelConfig.model_name.
    _bt_blocklist: List[str] = [
        "mixtral",
        "mistral",
        "qwen",
        "qwen2",
        "chatglm",
        "chatglm2",
        "chatglm3",
        "internlm",
        "baichuan",
        "yi",
    ]

    def select_backend(self, model_config: ModelConfig) -> AttentionBackend:
        """Determine the highest available backend tier for *model_config*.

        Tries each tier in order.  A tier is skipped when:
        - The required library is absent, or
        - The model appears in the BetterTransformer blocklist (Tier 1 only).

        Args:
            model_config: Description of the model to be optimised.

        Returns:
            The highest tier that is both available and compatible.
        """
        if self._can_use_better_transformer(model_config):
            logger.info(
                "AttentionBackend: selected BetterTransformer for %s",
                model_config.model_name or model_config.model_type,
            )
            return AttentionBackend.BETTER_TRANSFORMER

        if self._can_use_sdpa():
            logger.info(
                "AttentionBackend: selected SDPA for %s",
                model_config.model_name or model_config.model_type,
            )
            return AttentionBackend.SDPA

        logger.info(
            "AttentionBackend: falling back to vanilla for %s",
            model_config.model_name or model_config.model_type,
        )
        return AttentionBackend.VANILLA

    def apply_backend(self, model: Any, backend: AttentionBackend) -> Any:
        """Apply *backend* to *model*, falling through on any failure.

        Each tier is attempted.  If it raises, GPU memory is freed and the
        next tier is tried.  This mirrors the tier priority from
        :meth:`select_backend` so callers receive a consistently optimised
        model regardless of environment specifics.

        Args:
            model: A HuggingFace ``PreTrainedModel`` (or compatible) instance.
            backend: The backend tier returned by :meth:`select_backend`.

        Returns:
            The model, potentially transformed in-place or replaced by a
            BetterTransformer-wrapped copy.
        """
        if backend == AttentionBackend.BETTER_TRANSFORMER:
            result = self._try_apply_better_transformer(model)
            if result is not None:
                return result
            logger.warning("BetterTransformer application failed; falling back to SDPA")

        if backend in (AttentionBackend.BETTER_TRANSFORMER, AttentionBackend.SDPA):
            result = self._try_apply_sdpa(model)
            if result is not None:
                return result
            logger.warning("SDPA application failed; falling back to vanilla")

        logger.info("AttentionBackend: using vanilla (no transformation applied)")
        return model

    def get_available_backends(self) -> List[AttentionBackend]:
        """Return all backends available on the current system.

        The list is ordered from highest capability to lowest.

        Returns:
            List of :class:`AttentionBackend` values that can be used.
        """
        available: List[AttentionBackend] = []

        if _import_better_transformer() is not None:
            available.append(AttentionBackend.BETTER_TRANSFORMER)

        if self._can_use_sdpa():
            available.append(AttentionBackend.SDPA)

        available.append(AttentionBackend.VANILLA)
        return available

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_blocklisted(self, model_config: ModelConfig) -> bool:
        """Return True if the model must not use BetterTransformer."""
        candidates = [
            (model_config.model_type or "").lower(),
            (model_config.model_name or "").lower(),
        ]
        for entry in self._bt_blocklist:
            token = entry.lower()
            for candidate in candidates:
                if token in candidate:
                    logger.debug(
                        "BetterTransformer blocklist: '%s' matched by '%s'",
                        candidate,
                        token,
                    )
                    return True
        return False

    def _can_use_better_transformer(self, model_config: ModelConfig) -> bool:
        """Return True when BetterTransformer is available and not blocklisted."""
        if self._is_blocklisted(model_config):
            return False
        return _import_better_transformer() is not None

    @staticmethod
    def _can_use_sdpa() -> bool:
        """Return True when PyTorch exposes scaled_dot_product_attention."""
        try:
            torch = _import_torch()
            return hasattr(torch.nn.functional, "scaled_dot_product_attention")
        except ImportError:
            return False

    def _try_apply_better_transformer(self, model: Any) -> Optional[Any]:
        """Attempt BetterTransformer conversion; return None on failure."""
        bt_cls = _import_better_transformer()
        if bt_cls is None:
            return None
        try:
            transformed = bt_cls.transform(model, keep_original_model=False)
            logger.info("BetterTransformer transformation applied successfully")
            return transformed
        except Exception as exc:  # noqa: BLE001
            logger.warning("BetterTransformer.transform raised: %s", exc)
            _free_memory()
            return None

    @staticmethod
    def _try_apply_sdpa(model: Any) -> Optional[Any]:
        """Attempt to enable SDPA on the model; return None on failure."""
        try:
            torch = _import_torch()
            if not hasattr(torch.nn.functional, "scaled_dot_product_attention"):
                return None
            if hasattr(model, "to"):
                # Trigger SDPA path via model config when available
                if hasattr(model, "config") and hasattr(
                    model.config, "attn_implementation"
                ):
                    model.config.attn_implementation = "sdpa"
                logger.info("SDPA attention implementation selected")
                return model
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("SDPA application raised: %s", exc)
            _free_memory()
            return None


# ---------------------------------------------------------------------------
# Memory cleanup helper
# ---------------------------------------------------------------------------


def _free_memory() -> None:
    """Run Python GC and attempt to free CUDA memory if available."""
    gc.collect()
    try:
        torch = _import_torch()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.debug("CUDA cache cleared after backend fallback")
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_selector: Optional[AttentionBackendSelector] = None


def get_attention_backend_selector() -> AttentionBackendSelector:
    """Return the module-level :class:`AttentionBackendSelector` singleton.

    Creates the instance on first call; thread-safe for read-only use after
    initial creation.

    Issue #1951.

    Returns:
        The singleton :class:`AttentionBackendSelector`.
    """
    global _selector  # noqa: PLW0603
    if _selector is None:
        _selector = AttentionBackendSelector()
    return _selector


__all__ = [
    "AttentionBackend",
    "AttentionBackendSelector",
    "ModelConfig",
    "get_attention_backend_selector",
]
