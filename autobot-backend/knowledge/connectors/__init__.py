# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
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
- scheduler  — ConnectorScheduler (asyncio task-based)

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
import knowledge.connectors.file_server  # noqa: F401
import knowledge.connectors.web_crawler  # noqa: F401
from knowledge.connectors.base import AbstractConnector
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ConnectorStatus,
    ContentResult,
    SourceInfo,
    SyncResult,
)
from knowledge.connectors.registry import ConnectorRegistry

__all__ = [
    "AbstractConnector",
    "ChangeInfo",
    "ConnectorConfig",
    "ConnectorRegistry",
    "ConnectorStatus",
    "ContentResult",
    "SourceInfo",
    "SyncResult",
]
