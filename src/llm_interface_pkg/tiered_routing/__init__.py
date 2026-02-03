# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tiered Routing Package - Intelligent model tier selection based on task complexity.

Issue #748: Tiered Model Distribution Implementation.

This package provides:
- TaskComplexityScorer: Rule-based complexity scoring for requests
- TieredModelRouter: Routes requests to appropriate model tiers
- Configuration and metrics for monitoring

Usage:
    from src.llm_interface_pkg.tiered_routing import (
        TieredModelRouter,
        get_tiered_router,
        TierConfig,
    )

    # Using singleton
    router = get_tiered_router()
    model, result = router.route(messages)

    # Or with custom config
    config = TierConfig(complexity_threshold=4.0)
    router = TieredModelRouter(config)
"""

from .complexity_scorer import TaskComplexityScorer
from .tier_config import (
    ComplexityResult,
    TierConfig,
    TierLogging,
    TierMetrics,
    TierModels,
)
from .tier_router import TieredModelRouter, get_tiered_router

__all__ = [
    # Main classes
    "TieredModelRouter",
    "TaskComplexityScorer",
    # Configuration
    "TierConfig",
    "TierModels",
    "TierLogging",
    # Results and metrics
    "ComplexityResult",
    "TierMetrics",
    # Factory function
    "get_tiered_router",
]
