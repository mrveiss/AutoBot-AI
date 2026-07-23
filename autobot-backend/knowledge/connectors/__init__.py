# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Source Connector Framework

Issue #1254: Pluggable connector architecture for ingesting external content
into the knowledge base.

Packages:
- models     — SourceInfo, ContentResult, ChangeInfo, ConnectorConfig, …
- base       — AbstractConnector (ABC)
- registry   — ConnectorRegistry singleton
- file_server — FileServerConnector (NFS/SMB/local mounts)
- web_crawler — WebCrawlerConnector (Playwright-based)
- database   — DatabaseConnector (SQLAlchemy)
- external_adapter — ExternalConnectorAdapter (subprocess/stdout JSON protocol)
- gdrive     — GoogleDriveConnector (Google Drive API v3)
- gitlab      — GitLabConnector (GitLab v4 API) / GiteaConnector (Gitea + Forgejo v1 API)
- nextcloud   — NextcloudConnector (Nextcloud WebDAV)
- slack       — SlackConnector (Slack Web API) — Issue #10538, feature-flagged
- confluence  — ConfluenceConnector (Atlassian Confluence REST API) — Issue #10538, feature-flagged
- jira        — JiraConnector (Atlassian Jira REST API v3) — Issue #10538, feature-flagged
- scheduler  — ConnectorScheduler (asyncio task-based)

Issue #10538: The Slack/Confluence/Jira connectors are registered only when
``AUTOBOT_FEATURE_KB_ENTERPRISE_CONNECTORS=true`` (default disabled — see
``autobot_shared/feature_flags.py``). Until enabled, their connector types
are absent from ``ConnectorRegistry`` and cannot be instantiated.

Example usage::

    from knowledge.connectors import ConnectorRegistry, ConnectorConfig
    from datetime import datetime

    cfg = ConnectorConfig(
        connector_id="docs-nfs",
        connector_type="file_server",
        name="Documentation NFS Share",
        config={
            "base_path": "/mnt/docs",
            "include_patterns": ["**/*.md", "**/*.txt"],
            "exclude_patterns": ["**/node_modules/**"],
        },
    )
    connector = ConnectorRegistry.create(cfg)
    result = await connector.sync()
"""

# Trigger registration of built-in connector types
import knowledge.connectors.database  # noqa: F401
import knowledge.connectors.external_adapter  # noqa: F401
import knowledge.connectors.file_server  # noqa: F401
import knowledge.connectors.gdrive  # noqa: F401  # GH#9003
import knowledge.connectors.gitlab  # noqa: F401
import knowledge.connectors.nextcloud  # noqa: F401
import knowledge.connectors.notion  # noqa: F401
import knowledge.connectors.onedrive  # noqa: F401  # GH#9004
import knowledge.connectors.web_crawler  # noqa: F401
from autobot_shared.feature_flags import is_feature_enabled
from knowledge.connectors.base import AbstractConnector
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ConnectorStatus,
    ContentResult,
    SourceInfo,
    SyncResult,
)
from knowledge.connectors.registry import CATEGORY_MAP, ConnectorRegistry

# Issue #10538: Slack/Confluence/Jira ship disabled by default — these
# connectors reach third-party SaaS APIs and no credentials are configured
# out of the box. Gate their import (and therefore their
# @ConnectorRegistry.register side effect) behind the subsystem flag so
# nothing in this module makes them creatable unless explicitly enabled.
if is_feature_enabled("kb_enterprise_connectors"):
    import knowledge.connectors.confluence  # noqa: F401
    import knowledge.connectors.jira  # noqa: F401
    import knowledge.connectors.slack  # noqa: F401

__all__ = [
    "AbstractConnector",
    "CATEGORY_MAP",
    "ChangeInfo",
    "ConnectorConfig",
    "ConnectorRegistry",
    "ConnectorStatus",
    "ContentResult",
    "SourceInfo",
    "SyncResult",
]
