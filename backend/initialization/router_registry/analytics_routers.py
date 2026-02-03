# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analytics Router Loader

This module handles loading of analytics-related API routers.
These routers provide code analytics, performance analysis, and AI-powered insights.

Issue #281: Refactored from 338 lines of repetitive try/except blocks to
data-driven configuration pattern for improved maintainability.
"""

import importlib
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


# Issue #281: Router configurations as data instead of repetitive code blocks
# Format: (module_path, prefix, tags, name)
ANALYTICS_ROUTER_CONFIGS: List[Tuple[str, str, List[str], str]] = [
    # Core analytics
    ("backend.api.analytics", "/analytics", ["analytics"], "analytics"),
    ("backend.api.codebase_analytics", "/analytics", ["codebase-analytics"], "codebase_analytics"),
    ("backend.api.analytics_reporting", "", ["analytics-reporting", "analytics"], "analytics_reporting"),  # Issue #708: renamed from analytics_unified
    # Code analysis
    ("backend.api.analytics_evolution", "/evolution", ["code-evolution", "analytics"], "analytics_evolution"),  # Issue #570: Fix prefix
    ("backend.api.analytics_debt", "/debt", ["technical-debt", "analytics"], "analytics_debt"),  # Issue #570: Fix prefix
    ("backend.api.analytics_quality", "/quality", ["code-quality", "analytics"], "analytics_quality"),  # Issue #570: Fix prefix
    ("backend.api.analytics_code_review", "/code-review", ["code-review", "analytics"], "analytics_code_review"),  # Issue #570: Fix prefix
    ("backend.api.analytics_precommit", "/precommit", ["precommit", "analytics"], "analytics_precommit"),  # Issue #570: Fix prefix
    # AI/ML analytics
    ("backend.api.analytics_bug_prediction", "/analytics", ["bug-prediction", "analytics"], "analytics_bug_prediction"),
    ("backend.api.analytics_llm_patterns", "/llm-patterns", ["llm-patterns", "analytics"], "analytics_llm_patterns"),  # Issue #710: Fix prefix to match frontend
    ("backend.api.analytics_code_generation", "/code-generation", ["code-generation", "analytics"], "analytics_code_generation"),  # Issue #570: Fix prefix
    ("backend.api.analytics_embedding_patterns", "/embedding-analytics", ["embedding-analytics", "analytics"], "analytics_embedding_patterns"),
    # Performance and logging - Issue #710: Fix prefixes to match frontend
    ("backend.api.analytics_performance", "/performance", ["performance", "analytics"], "analytics_performance"),
    ("backend.api.analytics_log_patterns", "/log-patterns", ["log-patterns", "analytics"], "analytics_log_patterns"),
    ("backend.api.analytics_conversation", "/conversation-flow", ["conversation-flow", "analytics"], "analytics_conversation"),
    # Advanced analysis
    ("backend.api.analytics_cfg", "/cfg-analytics", ["cfg", "analytics"], "analytics_cfg"),
    ("backend.api.analytics_dfa", "/dfa-analytics", ["dfa", "analytics"], "analytics_dfa"),
    ("backend.api.analytics_architecture", "/architecture", ["architecture", "analytics", "patterns"], "analytics_architecture"),
    # Learning and patterns
    ("backend.api.analytics_pattern_learning", "/pattern-learning", ["pattern-learning", "analytics", "self-improving"], "analytics_pattern_learning"),
    ("backend.api.analytics_continuous_learning", "/continuous-learning", ["continuous-learning", "analytics", "learning"], "analytics_continuous_learning"),
    # Advanced analytics - Issue #59
    ("backend.api.analytics_maintenance", "", ["analytics-maintenance", "analytics", "bi"], "analytics_maintenance"),  # Issue #708: renamed from analytics_advanced
]


def _load_single_analytics_router(
    module_path: str,
    prefix: str,
    tags: List[str],
    name: str
) -> Tuple | None:
    """
    Load a single analytics router with graceful fallback.

    Issue #281: Extracted helper for loading individual routers to eliminate
    repetitive try/except blocks and enable data-driven router loading.

    Args:
        module_path: Full Python module path (e.g., 'backend.api.analytics')
        prefix: URL prefix for the router (e.g., '/analytics')
        tags: List of OpenAPI tags for the router
        name: Human-readable name for logging

    Returns:
        Tuple of (router, prefix, tags, name) if successful, None otherwise
    """
    try:
        module = importlib.import_module(module_path)
        router = getattr(module, 'router')
        logger.info("✅ Optional router loaded: %s", name)
        return (router, prefix, tags, name)
    except ImportError as e:
        logger.warning("⚠️ Optional router not available: %s - %s", name, e)
        return None
    except AttributeError as e:
        logger.warning("⚠️ Router not found in module %s: %s - %s", module_path, name, e)
        return None


def load_analytics_routers() -> List[Tuple]:
    """
    Dynamically load analytics API routers with graceful fallback.

    Issue #281: Refactored to use data-driven configuration pattern.
    Original implementation had 20 repetitive try/except blocks (~338 lines).
    Now uses ANALYTICS_ROUTER_CONFIGS list and _load_single_analytics_router helper.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              Only includes routers that successfully imported.
    """
    optional_routers = []

    for module_path, prefix, tags, name in ANALYTICS_ROUTER_CONFIGS:
        result = _load_single_analytics_router(module_path, prefix, tags, name)
        if result:
            optional_routers.append(result)

    logger.info("📊 Loaded %s/%s analytics routers", len(optional_routers), len(ANALYTICS_ROUTER_CONFIGS))
    return optional_routers
