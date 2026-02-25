# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Search Analytics Module

Issue #381: Extracted from search.py god class refactoring.
Contains search analytics tracking functionality.
"""

import logging
import threading
from typing import List, Optional

from models.task_context import SearchAnalyticsContext

logger = logging.getLogger(__name__)


class SearchAnalytics:
    """
    Tracks search analytics for performance monitoring.

    Records search queries, result counts, durations, and filters applied.
    """

    def track_analytics(
        self,
        query: str,
        result_count: int,
        duration_ms: int,
        session_id: Optional[str],
        mode: str,
        tags: Optional[List[str]],
        category: Optional[str],
        query_expansion: bool,
        relevance_scoring: bool,
        track_analytics: bool,
    ) -> None:
        """
        Track search analytics.

        Issue #281: Extracted from enhanced_search_v2 for clarity.
        Issue #375: Delegates to track_analytics_ctx using
        SearchAnalyticsContext for backward compatibility.

        Args:
            query: Original query
            result_count: Number of results found
            duration_ms: Search duration in milliseconds
            session_id: Session ID for tracking
            mode: Search mode used
            tags: Tags applied
            category: Category filter applied
            query_expansion: Whether query expansion was enabled
            relevance_scoring: Whether relevance scoring was enabled
            track_analytics: Whether to track analytics
        """
        # Issue #375: Create context and delegate
        ctx = SearchAnalyticsContext(
            query=query,
            result_count=result_count,
            duration_ms=duration_ms,
            session_id=session_id,
            mode=mode,
            tags=tags,
            category=category,
            query_expansion=query_expansion,
            relevance_scoring=relevance_scoring,
            track_analytics=track_analytics,
        )
        self.track_analytics_ctx(ctx)

    def track_analytics_ctx(self, ctx: SearchAnalyticsContext) -> None:
        """
        Track search analytics using context.

        Issue #375: Refactored from 10-parameter signature to accept a single
        SearchAnalyticsContext object.

        Args:
            ctx: SearchAnalyticsContext containing all analytics parameters.
        """
        if not ctx.track_analytics:
            return

        from knowledge.search_quality import get_search_analytics

        analytics = get_search_analytics()
        analytics.record_search(
            query=ctx.query,
            result_count=ctx.result_count,
            duration_ms=ctx.duration_ms,
            session_id=ctx.session_id,
            filters={
                "mode": ctx.mode,
                "tags": ctx.tags,
                "category": ctx.category,
                "query_expansion": ctx.query_expansion,
                "relevance_scoring": ctx.relevance_scoring,
            },
        )


# Module-level instance for convenience (thread-safe, Issue #613)
_analytics = None
_analytics_lock = threading.Lock()


def get_analytics() -> SearchAnalytics:
    """Get the shared SearchAnalytics instance (thread-safe).

    Uses double-check locking pattern to ensure thread safety while
    minimizing lock contention after initialization (Issue #613).
    """
    global _analytics
    if _analytics is None:
        with _analytics_lock:
            # Double-check after acquiring lock
            if _analytics is None:
                _analytics = SearchAnalytics()
    return _analytics
