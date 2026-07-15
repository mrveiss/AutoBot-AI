# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Negative fixture: descriptive + domain-adjective paths — no violations."""

router = object()


@router.post("/goal/orchestrated")
async def goal_orchestrated():
    pass


@router.get("/search/multi-source")
def search_multi_source():
    pass


@router.get("/advanced-stats")
def advanced_stats():
    """Domain adjective, not an era-marker synonym-swap — allowed."""


# include_router with descriptive / domain-adjective prefixes — not flagged.
def setup_routes(app):
    app.include_router(router, prefix="/reporting")
    app.include_router(router, prefix="/advanced-stats")
