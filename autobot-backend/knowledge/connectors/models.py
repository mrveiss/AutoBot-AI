# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Source Connector Data Models

Issue #1254: Defines the dataclass models used across the connector framework —
SourceInfo, ContentResult, ChangeInfo, ConnectorConfig, ConnectorStatus, SyncResult.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class SourceInfo:
    """Describes a single discoverable source within a connector.

    A source is any addressable unit of content — a file, a URL, a database row.
    """

    source_id: str
    name: str
    path: str  # file path, URL, table name, etc.
    content_type: str  # "text/plain", "application/pdf", etc.
    size_bytes: int
    last_modified: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentResult:
    """Holds fetched content for a single source."""

    source_id: str
    content: str
    content_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunks: List[str] = field(default_factory=list)  # pre-chunked if applicable


@dataclass
class ChangeInfo:
    """Represents a detected change in a source since the last sync."""

    source_id: str
    change_type: str  # "added", "modified", "deleted"
    timestamp: datetime
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorConfig:
    """Configuration for a connector instance.

    Stored in Redis under key ``connector:{connector_id}``.
    """

    connector_id: str
    connector_type: str  # matches AbstractConnector.connector_type
    name: str
    config: Dict[str, Any]  # type-specific config keys
    enabled: bool = True
    verification_mode: str = "collaborative"  # "autonomous" or "collaborative"
    schedule_cron: Optional[str] = None  # cron-like expression; None = manual only
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_sync_at: Optional[datetime] = None
    include_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)


@dataclass
class ConnectorStatus:
    """Runtime status for a connector."""

    connector_id: str
    is_healthy: bool
    last_sync_at: Optional[datetime]
    last_sync_status: str  # "success", "failed", "running", "never"
    documents_indexed: int
    last_error: Optional[str] = None


@dataclass
class SyncResult:
    """Summary of a completed (or failed) sync operation."""

    connector_id: str
    started_at: datetime
    completed_at: Optional[datetime]
    status: str  # "success", "failed", "partial"
    added: int = 0
    updated: int = 0
    deleted: int = 0
    errors: List[str] = field(default_factory=list)
