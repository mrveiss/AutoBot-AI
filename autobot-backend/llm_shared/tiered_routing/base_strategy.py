# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RoutingStrategy Protocol — pluggable interface for LLM routing strategies.

Issue #6595: Cost-aware and latency-aware routing strategies.

New strategies implement this Protocol and register themselves in registry.py.
Adding a strategy = one new file; no edits to existing routers required.
"""

from typing import Dict, List, Protocol, Tuple, runtime_checkable

from .tier_config import ComplexityResult


@runtime_checkable
class RoutingStrategy(Protocol):
    """
    Protocol that every routing strategy must satisfy.

    ``route()`` must be synchronous so it can be called from both sync and
    async paths without awaiting.  Strategies that need Redis do their I/O
    in a separate async refresh task (see LatencyRouter).
    """

    def route(
        self,
        messages: List[Dict],
        requested_model: str | None = None,
    ) -> Tuple[str, ComplexityResult]:
        """
        Select a model for the given request.

        Args:
            messages: Conversation messages to analyse.
            requested_model: Model originally requested by the caller.

        Returns:
            (selected_model, result) where result carries score/reasoning.
        """
        ...

    def get_metrics(self) -> Dict:
        """Return a dict of strategy-specific metrics for monitoring."""
        ...


__all__ = ["RoutingStrategy"]
