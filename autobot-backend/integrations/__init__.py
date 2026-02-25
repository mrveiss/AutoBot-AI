# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
External Tool Integrations Package (Issue #61)

Provides integrations with external tools and services:
- Database management (PostgreSQL, MySQL, MongoDB)
- Cloud providers (AWS, Azure, GCP)
- CI/CD (Jenkins, GitLab CI, CircleCI)
- Project management (Jira, Trello, Asana)
- Communication (Slack, Teams, Discord)
- Version control (GitLab, Bitbucket)
- Monitoring (Datadog, New Relic)
"""

from integrations.base import BaseIntegration, IntegrationConfig, IntegrationStatus

__all__ = [
    "BaseIntegration",
    "IntegrationConfig",
    "IntegrationStatus",
]
