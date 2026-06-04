# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Strategy registry — selects the active routing strategy from SSOT config.

Issue #6595: Cost-aware and latency-aware routing strategies.

Config key: ``backend.llm.routing_strategy``
Valid values: ``complexity`` (default) | ``cost`` | ``latency``

Adding a new strategy requires only one new file implementing RoutingStrategy;
no changes to this module needed unless you want config-driven selection.
"""

from typing import Dict, List, Tuple

from autobot_shared.logging_manager import get_logger

from .base_strategy import RoutingStrategy
from .complexity_router import ComplexityRouter
from .cost_router import CostRouter
from .latency_router import LatencyRouter
from .long_context_router import LongContextRouter
from .tier_config import ComplexityResult, TierConfig

logger = get_logger(__name__)

_STRATEGY_MAP: Dict[str, type] = {
    "complexity": ComplexityRouter,
    "cost": CostRouter,
    "latency": LatencyRouter,
    "long_context": LongContextRouter,
}

_DEFAULT_STRATEGY = "complexity"

_active_router: RoutingStrategy | None = None


def get_active_router(
    config: TierConfig | None = None,
    force_new: bool = False,
) -> RoutingStrategy:
    """
    Return the singleton router selected by SSOT config.

    Strategy is resolved from ``backend.llm.routing_strategy`` (or env var
    ``AUTOBOT_LLM_ROUTING_STRATEGY``).  Falls back to ``complexity`` when
    the configured value is unrecognised.
    """
    global _active_router

    if _active_router is not None and not force_new:
        return _active_router

    cfg = config or TierConfig.from_config()
    strategy_name = _resolve_strategy_name(cfg)
    strategy_cls = _STRATEGY_MAP.get(strategy_name)

    if strategy_cls is None:
        logger.warning(
            "Unknown routing strategy %r; falling back to 'complexity'",
            strategy_name,
        )
        strategy_cls = ComplexityRouter

    _active_router = strategy_cls(cfg)
    logger.info("LLM routing strategy: %s (%s)", strategy_name, strategy_cls.__name__)
    return _active_router


def _resolve_strategy_name(config: TierConfig) -> str:
    import os

    # Env-var override takes precedence (useful in tests / deployment)
    env_val = os.environ.get("AUTOBOT_LLM_ROUTING_STRATEGY", "").strip().lower()
    if env_val:
        return env_val

    # SSOT config
    try:
        from config.registry import ConfigRegistry

        return ConfigRegistry.get("backend.llm.routing_strategy", _DEFAULT_STRATEGY)
    except Exception:
        return _DEFAULT_STRATEGY


def route(
    messages: List[Dict],
    requested_model: str | None = None,
) -> Tuple[str, ComplexityResult]:
    """Convenience wrapper — routes via the active strategy singleton."""
    return get_active_router().route(messages, requested_model)


__all__ = ["get_active_router", "route"]
