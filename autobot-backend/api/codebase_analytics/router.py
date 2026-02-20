# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Main router combining all codebase analytics endpoints
"""

from fastapi import APIRouter

# Issue #244: Cross-Language Pattern Detector
# Issue #208: Code Pattern Detection & Optimization
from .endpoints import api_endpoints  # Issue #527: API Endpoint Checker
from .endpoints import environment  # Issue #538: Environment analysis
from .endpoints import ownership  # Issue #248: Code Ownership and Expertise Map
from .endpoints import (
    cache,
    call_graph,
    charts,
    cross_language_patterns,
    declarations,
    dependencies,
    duplicates,
    import_tree,
    indexing,
    pattern_analysis,
    report,
    stats,
)

# Create main router — prefix provided by analytics_routers.py registry (#1027)
router = APIRouter(tags=["codebase-analytics"])

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
router.include_router(environment.router)  # Issue #538: Environment analysis
router.include_router(
    cross_language_patterns.router
)  # Issue #244: Cross-Language Patterns
router.include_router(pattern_analysis.router)  # Issue #208: Code Pattern Detection
router.include_router(ownership.router)  # Issue #248: Code Ownership and Expertise Map
