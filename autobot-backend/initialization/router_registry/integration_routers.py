# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Integration Router Loader

This module handles loading of integration-related API routers.
These routers provide integrations with external services and platforms
including cloud providers, CI/CD systems, databases, communication tools, etc.

Issue #4203: Consolidates integration routers into a dedicated registry module.
"""

import importlib
from typing import List, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


# Issue #4203: Router configurations as data instead of repetitive code blocks
# Format: (module_path, prefix, tags, name)
INTEGRATION_ROUTER_CONFIGS: List[Tuple[str, str, List[str], str]] = [
    # Cloud integrations
    (
        "api.integration_cloud",
        "/integrations/cloud",
        ["integrations-cloud"],
        "integration_cloud",
    ),
    # CI/CD integrations
    (
        "api.integration_cicd",
        "/integrations/cicd",
        ["integrations-cicd"],
        "integration_cicd",
    ),
    # Database integrations
    (
        "api.integration_database",
        "/integrations/database",
        ["integrations-database"],
        "integration_database",
    ),
    # Project management integrations
    (
        "api.integration_project_management",
        "/integrations/project-management",
        ["integrations-project-management"],
        "integration_project_management",
    ),
    # Communication integrations
    (
        "api.integration_communication",
        "/integrations/communication",
        ["integrations-communication"],
        "integration_communication",
    ),
    # Version control integrations
    (
        "api.integration_version_control",
        "/integrations/version-control",
        ["integrations-version-control"],
        "integration_version_control",
    ),
    # Monitoring integrations
    (
        "api.integration_monitoring",
        "/integrations/monitoring",
        ["integrations-monitoring"],
        "integration_monitoring",
    ),
    # GitHub-specific integrations
    (
        "api.integration_github",
        "/integrations/github",
        ["integrations-github"],
        "integration_github",
    ),
    # Telegram bot integration (MVA-2928 / GH#9006)
    (
        "api.telegram_bot",
        "",  # No prefix - endpoints are /telegram/webhook and /telegram/config
        ["telegram-bot"],
        "telegram_bot",
    ),
]


def _load_single_integration_router(module_path: str, prefix: str, tags: List[str], name: str) -> Tuple | None:
    """
    Load a single integration router with graceful fallback.

    Issue #4203: Extracted helper for loading individual routers to eliminate
    repetitive try/except blocks and enable data-driven router loading.

    Args:
        module_path: Full Python module path (e.g., 'api.integration_cloud')
        prefix: URL prefix for the router (e.g., '/integrations/cloud')
        tags: List of OpenAPI tags for the router
        name: Human-readable name for logging

    Returns:
        Tuple of (router, prefix, tags, name) if successful, None otherwise
    """
    try:
        module = importlib.import_module(module_path)
        router = getattr(module, "router")
        logger.info("✅ Optional router loaded: %s", name)
        return (router, prefix, tags, name)
    except ImportError as e:
        logger.warning("⚠️ Optional router not available: %s - %s", name, e)
        return None
    except AttributeError as e:
        logger.warning("⚠️ Router not found in module %s: %s - %s", module_path, name, e)
        return None


def load_integration_routers() -> List[Tuple]:
    """
    Dynamically load integration API routers with graceful fallback.

    Issue #4203: Refactored to use data-driven configuration pattern.
    Consolidates all integration_* routers into a dedicated module.

    These routers provide integrations with external services and platforms:
    - Cloud providers (AWS, Azure, GCP)
    - CI/CD systems (GitHub Actions, Jenkins, GitLab CI)
    - Databases (SQL, NoSQL)
    - Project management tools (Jira, Asana, Linear)
    - Communication platforms (Slack, Teams, Discord)
    - Version control (GitHub, GitLab, Bitbucket)
    - Monitoring and observability (Prometheus, Datadog)

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              Only includes routers that successfully imported.
    """
    optional_routers = []

    for module_path, prefix, tags, name in INTEGRATION_ROUTER_CONFIGS:
        result = _load_single_integration_router(module_path, prefix, tags, name)
        if result:
            optional_routers.append(result)

    logger.info(
        "🔗 Loaded %s/%s integration routers",
        len(optional_routers),
        len(INTEGRATION_ROUTER_CONFIGS),
    )
    return optional_routers
