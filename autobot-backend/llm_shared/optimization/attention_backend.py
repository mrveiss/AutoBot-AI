# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Attention backend selector with architecture-family dispatch.

Selects and applies the best available attention backend for a given model
and hardware environment, routing first on architecture family and then on
available library tiers.

Architecture-family dispatch (Issue #7350, kernels wired in Issue #10724)
  transformer      — tiered flash/sdpa/eager path (BetterTransformer → SDPA → Vanilla)
  state_space      — SSM_SCAN: Mamba-style selective scan (ssm_kernels.SSMScanKernel)
  linear_attention — LINEAR_ATTN: O(L) feature-map linear attention
  hybrid           — HYBRID: Jamba-style per-layer routing (ssm_kernels.HybridRouter)

The dispatch table (ARCH_DISPATCH_TABLE) is data-driven: adding a new architecture
family requires only an entry in the table and a handler method.  select_backend()
does not need modification.

Transformer tier fallback chain (Issue #1951, unchanged)
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
Issue #7350: Architecture-family dispatch table.
"""

import gc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from llm_shared.types import ArchitectureFamily

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lazy import helpers
# ---------------------------------------------------------------------------


def _import_torch() -> Any:
    """Lazily import torch; raises ImportError with guidance if absent."""
    try:
        import torch  # noqa: PLC0415

        return torch
    except (ImportError, RuntimeError) as exc:
        raise ImportError(
            "torch is required for attention backend selection. " "Install with: pip install torch>=2.0.0"
        ) from exc


def _import_better_transformer() -> Any:
    """Lazily import BetterTransformer from optimum; returns None if absent."""
    try:
        from optimum.bettertransformer import BetterTransformer  # noqa: PLC0415

        return BetterTransformer
    except (ImportError, RuntimeError):
        return None


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class AttentionBackend(str, Enum):
    """Available sequence-mixer backend tiers.

    Values reflect capability tiers from highest (fastest) to lowest (most
    compatible).  The string values are stable identifiers safe for logging
    and serialisation.

    Transformer tiers (BETTER_TRANSFORMER / SDPA / VANILLA) select an
    attention implementation.  Non-attention families select a concrete kernel
    from :mod:`ssm_kernels`:
      SSM_SCAN    — Mamba-style selective scan (state-space models).
      LINEAR_ATTN — feature-map linear attention (O(L)).
      HYBRID      — Jamba-style per-layer routing (attention + SSM).

    NOT_APPLICABLE remains only as a genuine fallback for an architecture
    family that has no registered kernel.  Issue #7350, Issue #10724.
    """

    BETTER_TRANSFORMER = "better_transformer"
    SDPA = "sdpa"
    VANILLA = "vanilla"
    SSM_SCAN = "ssm_scan"
    LINEAR_ATTN = "linear_attn"
    HYBRID = "hybrid"
    NOT_APPLICABLE = "not_applicable"


# Backends dispatched to ssm_kernels rather than a HuggingFace attention
# transform.  apply_backend() leaves the loaded model object untouched for
# these (the kernel consumes tensors, not the model wrapper).  Issue #10724.
_NON_ATTENTION_BACKENDS = frozenset(
    {
        AttentionBackend.SSM_SCAN,
        AttentionBackend.LINEAR_ATTN,
        AttentionBackend.HYBRID,
        AttentionBackend.NOT_APPLICABLE,
    }
)


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
        architecture_family: High-level architecture family from ``ArchitectureFamily``.
            Defaults to ``TRANSFORMER`` for backwards compatibility.
            Issue #7347/#7350: positive family signal for non-attention routing.
    """

    model_name: str = ""
    model_type: str = ""
    torch_dtype: str | None = None
    architecture_family: ArchitectureFamily = ArchitectureFamily.TRANSFORMER
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Architecture-family dispatch table  (Issue #7350)
# ---------------------------------------------------------------------------

# Maps each ArchitectureFamily to the handler method name on
# AttentionBackendSelector.  Extend this dict at startup (or via plugin) to
# register a new family — select_backend() needs no modification.
ARCH_DISPATCH_TABLE: dict[ArchitectureFamily, str] = {
    ArchitectureFamily.TRANSFORMER: "_handle_transformer",
    ArchitectureFamily.STATE_SPACE: "_handle_ssm",
    ArchitectureFamily.LINEAR_ATTENTION: "_handle_linear_attention",
    ArchitectureFamily.HYBRID: "_handle_hybrid",
}


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------


class AttentionBackendSelector:
    """Select and apply the best available attention backend for a model.

    Architecture-family dispatch (Issue #7350):
      The module-level ``ARCH_DISPATCH_TABLE`` maps each ``ArchitectureFamily``
      to a handler method on this class.  ``select_backend`` looks up the
      handler and delegates — adding a new family requires only a new table
      entry plus a corresponding method; ``select_backend`` is never touched.

    Transformer tier fallback (Issue #1951):
      1. BetterTransformer  (requires ``optimum``, blocked for some models)
      2. SDPA               (requires ``torch >= 2.0``)
      3. Vanilla            (always available)

    Each ``select_backend`` call is stateless; the same selector instance can
    be reused for multiple models without side-effects.
    """

    # Per-class copy of the dispatch table.  Tests may patch this without
    # affecting the module-level ARCH_DISPATCH_TABLE.
    _arch_dispatch: ClassVar[dict[ArchitectureFamily, str]] = ARCH_DISPATCH_TABLE

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

        Dispatches on ``model_config.architecture_family`` via
        ``_arch_dispatch`` (sourced from module-level ``ARCH_DISPATCH_TABLE``).
        Unknown families fall back to the transformer path with a WARNING so
        operators know to register the new family in the table.

        Emits a structured ``arch_dispatch_event`` log entry on every call.
        Issue #7350.

        Args:
            model_config: Description of the model to be optimised.

        Returns:
            The backend selected by the architecture-family handler.
        """
        family = model_config.architecture_family
        handler_name = self._arch_dispatch.get(family)
        if handler_name is None:
            logger.warning(
                "arch_dispatch_event: unknown architecture_family=%s for %s — "
                "falling back to transformer path; add to ARCH_DISPATCH_TABLE to suppress",
                family.value if hasattr(family, "value") else family,
                model_config.model_name or model_config.model_type or "(unknown)",
            )
            handler_name = "_handle_transformer"

        handler = getattr(self, handler_name, self._handle_transformer)
        result = handler(model_config)

        logger.info(
            "arch_dispatch_event architecture_family=%s selected_backend=%s model=%s",
            family.value if hasattr(family, "value") else family,
            result.value,
            model_config.model_name or model_config.model_type or "(unknown)",
        )
        return result

    def apply_backend(self, model: Any, backend: AttentionBackend) -> Any:
        """Apply *backend* to *model*, falling through on any failure.

        Non-attention backends (``SSM_SCAN``, ``LINEAR_ATTN``, ``HYBRID``) and
        ``NOT_APPLICABLE`` return the model unchanged: they run through the
        dedicated kernels in :mod:`ssm_kernels`, not a HuggingFace attention
        transform.  Issue #7350, Issue #10724.

        Each transformer tier is attempted.  If it raises, GPU memory is freed
        and the next tier is tried.  This mirrors the tier priority from
        :meth:`select_backend` so callers receive a consistently optimised
        model regardless of environment specifics.

        Args:
            model: A HuggingFace ``PreTrainedModel`` (or compatible) instance.
            backend: The backend tier returned by :meth:`select_backend`.

        Returns:
            The model, potentially transformed in-place or replaced by a
            BetterTransformer-wrapped copy.
        """
        if backend in _NON_ATTENTION_BACKENDS:
            return model

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
    # Architecture-family handlers  (Issue #7350)
    # ------------------------------------------------------------------

    def _handle_transformer(self, model_config: ModelConfig) -> AttentionBackend:
        """Transformer: tiered flash/sdpa/eager selection (unchanged from #1951)."""
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

    def _handle_ssm(self, model_config: ModelConfig) -> AttentionBackend:
        """State-space / Mamba: route to the SSM selective-scan kernel.

        SSM models use a recurrent scan (``ssm_kernels.SSMScanKernel``), not
        scaled-dot-product attention — FlashAttention must not be invoked.
        Issue #10724.
        """
        logger.debug(
            "SSM selective-scan kernel selected for %s",
            model_config.model_name or model_config.model_type or "(unknown)",
        )
        return AttentionBackend.SSM_SCAN

    def _handle_linear_attention(self, model_config: ModelConfig) -> AttentionBackend:
        """Linear-attention: route to the O(L) feature-map linear-attn kernel.

        Selects ``ssm_kernels.LinearAttentionKernel``.  Issue #10724.
        """
        logger.debug(
            "Linear-attention kernel selected for %s",
            model_config.model_name or model_config.model_type or "(unknown)",
        )
        return AttentionBackend.LINEAR_ATTN

    def _handle_hybrid(self, model_config: ModelConfig) -> AttentionBackend:
        """Hybrid (Jamba-style): route to the per-layer hybrid dispatcher.

        Attention layers → transformer path; SSM layers → SSM scan kernel,
        coordinated by ``ssm_kernels.HybridRouter``.  Issue #10724.
        """
        logger.debug(
            "Hybrid per-layer routing selected for %s",
            model_config.model_name or model_config.model_type or "(unknown)",
        )
        return AttentionBackend.HYBRID

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
        except (ImportError, RuntimeError):
            return False

    def _try_apply_better_transformer(self, model: Any) -> Any | None:
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
    def _try_apply_sdpa(model: Any) -> Any | None:
        """Attempt to enable SDPA on the model; return None on failure."""
        try:
            torch = _import_torch()
            if not hasattr(torch.nn.functional, "scaled_dot_product_attention"):
                return None
            if hasattr(model, "to"):
                # Trigger SDPA path via model config when available
                if hasattr(model, "config") and hasattr(model.config, "attn_implementation"):
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
    except (ImportError, RuntimeError):
        pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_get_selector = lazy_singleton(AttentionBackendSelector)


def get_attention_backend_selector() -> AttentionBackendSelector:
    """Return the module-level :class:`AttentionBackendSelector` singleton.

    Creates the instance on first call; thread-safe via double-checked lock.

    Issue #1951.

    Returns:
        The singleton :class:`AttentionBackendSelector`.
    """
    return _get_selector()


__all__ = [
    "ARCH_DISPATCH_TABLE",
    "AttentionBackend",
    "AttentionBackendSelector",
    "ModelConfig",
    "get_attention_backend_selector",
]
