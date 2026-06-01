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
- Knowledge/productivity (Notion) — Issue #4099
"""

from integrations.base import BaseIntegration, IntegrationConfig, IntegrationStatus
from integrations.github_integration import GitHubIntegration
from integrations.microsoft365_integration import Microsoft365Integration
from integrations.notion_integration import NotionIntegration
from integrations.rate_limiter import IntegrationRateLimiter
from integrations.slack_integration import SlackChannelMapping, SlackNotificationIntegration

__all__ = [
    "BaseIntegration",
    "GitHubIntegration",
    "IntegrationConfig",
    "IntegrationRateLimiter",
    "Microsoft365Integration",
    "IntegrationStatus",
    "Microsoft365Integration",
    "NotionIntegration",
    "SlackChannelMapping",
    "SlackNotificationIntegration",
]
