# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Main router combining all codebase analytics endpoints
"""

from fastapi import APIRouter

from .endpoints import (
    indexing,
    stats,
    charts,
    dependencies,
    import_tree,
    call_graph,
    declarations,
    duplicates,
    cache,
)

# Create main router with common prefix and tags
router = APIRouter(prefix="/codebase", tags=["codebase-analytics"])

# Include all endpoint routers
router.include_router(indexing.router)
router.include_router(stats.router)
router.include_router(charts.router)
router.include_router(dependencies.router)
router.include_router(import_tree.router)
router.include_router(call_graph.router)
router.include_router(declarations.router)
router.include_router(duplicates.router)
router.include_router(cache.router)
