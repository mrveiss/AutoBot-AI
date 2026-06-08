# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tiered Model Router - backward-compat shim.

Issue #748: Original complexity-based routing.
Issue #6595: Strategy registry introduced — ComplexityRouter is now the
  canonical class.  TieredModelRouter is retained as an alias so existing
  call sites work unchanged.
"""

from typing import Optional

from .complexity_router import ComplexityRouter
from .tier_config import TierConfig

# Backward-compat alias — new code should use ComplexityRouter directly.
TieredModelRouter = ComplexityRouter

_router_instance: Optional[ComplexityRouter] = None


def get_tiered_router(
    config: TierConfig | None = None,
    force_new: bool = False,
) -> ComplexityRouter:
    """Return the complexity-router singleton (backward-compat helper)."""
    global _router_instance
    if _router_instance is None or force_new:
        _router_instance = ComplexityRouter(config)
    return _router_instance


__all__ = [
    "TieredModelRouter",
    "get_tiered_router",
]
