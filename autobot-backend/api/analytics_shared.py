# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared helpers for analytics API modules (Issue #3440).

Contains utilities reused across analytics_quality, analytics_evolution,
analytics_code_review, and analytics_code_generation.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def resolve_source_or_404(source_id: Optional[str]) -> None:
    """Raise HTTP 404 if source_id is provided but not found.

    Uses lazy imports of resolve_source_root and HTTPException to avoid
    loading the full codebase_analytics package at module import time.
    """
    if source_id is None:
        return
    from api.codebase_analytics.endpoints.shared import resolve_source_root
    from fastapi import HTTPException

    source_root = await resolve_source_root(source_id)
    if source_root is None:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found")
