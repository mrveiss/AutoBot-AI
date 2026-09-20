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
- mock        — MockConnector (local JSON fixtures, zero network) — Issue #10538, feature-flagged
- scheduler  — ConnectorScheduler (asyncio task-based)

Issue #10538: The Slack/Confluence/Jira connectors are registered only when
``AUTOBOT_FEATURE_KB_ENTERPRISE_CONNECTORS=true`` (default disabled — see
``autobot_shared/feature_flags.py``). Until enabled, their connector types
are absent from ``ConnectorRegistry`` and cannot be instantiated.

Issue #10538: MockConnector is registered only when
``AUTOBOT_FEATURE_KB_MOCK_CONNECTOR=true`` (default disabled). It never
makes a network call — the gate exists solely to keep a "mock" entry out of
the production ``GET /knowledge_base/connector_types`` listing by default;
enable it in dev/CI to exercise the sync() pipeline offline.

Issue #17138: No connector module is imported by this package any more --
each is imported lazily, on first use, by ``registry.ConnectorRegistry``
(``_ensure_loaded``/``_ensure_all_loaded``), which is also where the two
feature-flag checks above are now evaluated. Importing this package (or any
sibling module such as ``credential_store``) no longer pulls in every
connector's own third-party dependency.

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

# #17138: no `import knowledge.connectors.<concrete connector>` here any
# more. Each one pulls in its own third-party dependency (aiohttp for
# gdrive, defusedxml for nextcloud, ...), and Python always runs a package's
# __init__ before any of its submodules -- so anything that imported ONLY
# knowledge.connectors.credential_store (a sibling module with no connector
# dependency of its own) paid for every connector's imports too. The
# registry now resolves and imports a connector's module lazily, on first
# use, in registry.py's own _ensure_loaded/_ensure_all_loaded -- see its
# module docstring. The #10538 feature-flag gate for the
# enterprise/mock connectors moved there with it, since the gate has to be
# checked at resolve time now instead of at package-import time.
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
