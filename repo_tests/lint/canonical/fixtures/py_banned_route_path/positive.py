# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Positive fixture: era-marker route paths — three violations (decorator ×2, include_router ×1)."""

router = object()  # placeholder; only decorators are parsed


@router.post("/goal/enhanced")
async def goal_enhanced():
    pass


@router.get("/search/unified")
def search_unified():
    pass


# Surface 2: include_router with era-marker prefix (detected everywhere).
def setup_routes(app):
    app.include_router(router, prefix="/consolidated-data")
