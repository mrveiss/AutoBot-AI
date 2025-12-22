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
    report,
    api_endpoints,  # Issue #527: API Endpoint Checker
    environment,    # Issue #538: Environment analysis
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
router.include_router(report.router)
router.include_router(api_endpoints.router)  # Issue #527: API Endpoint Checker
router.include_router(environment.router)    # Issue #538: Environment analysis
