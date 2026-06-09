# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tiered Routing Package — pluggable LLM routing strategies.

Issue #748: Complexity-based routing.
Issue #6595: Strategy registry with cost-aware and latency-aware alternatives.

Usage (registry / config-driven):
    from llm_shared.tiered_routing import route, get_active_router
    model, result = route(messages)

Usage (specific strategy):
    from llm_shared.tiered_routing import ComplexityRouter, CostRouter, LatencyRouter

Backward-compat (original class name):
    from llm_shared.tiered_routing import TieredModelRouter, get_tiered_router
"""

from .base_strategy import RoutingStrategy
from .complexity_router import ComplexityRouter
from .complexity_scorer import TaskComplexityScorer
from .cost_router import CostRouter
from .latency_router import LatencyRouter
from .long_context_router import LONG_CONTEXT_MIN_WINDOW, LONG_CONTEXT_PROMPT_THRESHOLD, LongContextRouter
from .registry import get_active_router, route
from .tier_config import (
    ComplexityResult,
    TierConfig,
    TierLogging,
    TierMetrics,
    TierModels,
)
from .tier_router import TieredModelRouter, get_tiered_router

__all__ = [
    # Protocol
    "RoutingStrategy",
    # Strategies
    "ComplexityRouter",
    "CostRouter",
    "LatencyRouter",
    "LongContextRouter",
    # Registry
    "get_active_router",
    "route",
    # Complexity scoring
    "TaskComplexityScorer",
    # Configuration
    "TierConfig",
    "TierModels",
    "TierLogging",
    # Results and metrics
    "ComplexityResult",
    "TierMetrics",
    # Long-context constants
    "LONG_CONTEXT_PROMPT_THRESHOLD",
    "LONG_CONTEXT_MIN_WINDOW",
    # Backward-compat
    "TieredModelRouter",
    "get_tiered_router",
]
