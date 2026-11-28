# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-source code-analysis cache access (#22198, #22363).

``analytics_state["code_analysis_cache"]`` maps ``source_id`` to that source's
last analysis. A single process-wide entry served whichever source ran last to
every other source. Readers go through ``get_cached_analysis`` and scans through
``run_source_analysis`` so no route can spell the global read again.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends

from api.codebase_analytics.endpoints.shared import require_source_access
from api.schemas_analytics import CodeAnalysisRequest
from api.source_scope import require_source_id

#: Route-level guard for every route that reads or fills a source's cache entry.
SOURCE_SCOPED = [Depends(require_source_access)]


def get_cached_analysis(state: dict, source_id: str) -> "dict[str, Any] | None":
    """The cached analysis of ONE source, or None; never another source's."""
    source = require_source_id(source_id, "code-analysis cache read")
    return state.get("code_analysis_cache", {}).get(source)


def cached_source_count(state: dict) -> int:
    """How many sources have a cached analysis; a count, never ids (they would disclose other users' sources)."""
    return len(state.get("code_analysis_cache", {}))


async def run_source_analysis(controller, source_id: str, scan_root: Path, analysis_type: str, **options):
    """Analyse the source's own checkout and cache the result under that source."""
    source = require_source_id(source_id, "code-analysis request")
    request = CodeAnalysisRequest(analysis_type=analysis_type, target_path=str(scan_root), **options)
    return await controller.perform_code_analysis(request, source)
