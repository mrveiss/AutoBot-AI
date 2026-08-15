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

from typing import List, Tuple

from .loader import load_router_group, load_single_router


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
    # Telegram bot integration is registered in core_routers (MVA-2074); do NOT
    # add it here too — duplicate include_router double-mounts /telegram/* routes
    # and OpenAPI operations (GH#9006).
    # WhatsApp Business API channel (GH#9007)
    (
        "api.whatsapp",
        "",  # No prefix - endpoints are /whatsapp/webhook and /whatsapp/config
        ["whatsapp"],
        "whatsapp",
    ),
]


def _load_single_integration_router(module_path: str, prefix: str, tags: List[str], name: str) -> Tuple | None:
    """Load one router. Kept as this module's named entry point (#14207).

    The body moved to :func:`loader.load_single_router` so all seven
    registries record results in one place, instead of six of them
    swallowing the failure with nothing but a WARNING.
    """
    return load_single_router("integration", module_path, prefix, tags, name)


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
    return load_router_group("integration", INTEGRATION_ROUTER_CONFIGS)
