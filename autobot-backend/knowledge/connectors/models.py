# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Source Connector Data Models

Issue #1254: Defines the dataclass models used across the connector framework —
SourceInfo, ContentResult, ChangeInfo, ConnectorConfig, ConnectorStatus, SyncResult.
Issue #8145: Added auth_type field to ConnectorConfig for API introspection.
Issue #8146: Added resumed_from_checkpoint to SyncResult.
Issue #8152: Added config_version field to ConnectorConfig.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from autobot_shared.time_utils import now_utc


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

    The ``config`` dict is type-specific.  For ``external_adapter`` connectors
    (Issue #8150) the following keys are recognised:

    * ``entrypoint`` (str) — path to the connector package's main.py
    * ``source_config`` (dict) — credentials / settings passed as --config JSON
    * ``selected_streams`` (list[str]) — streams to ingest; empty = all streams
    * ``field_map`` (dict) — per-stream mapping to title/body/metadata fields;
      unmapped fields are serialized as JSON and appended to content
    * ``state_key`` (str) — Redis key for the STATE checkpoint; defaults to
      ``connector:{connector_id}:external_state``
    """

    connector_id: str
    connector_type: str  # matches AbstractConnector.connector_type
    name: str
    config: Dict[str, Any]  # type-specific config keys
    enabled: bool = True
    verification_mode: str = "collaborative"  # "autonomous" or "collaborative"
    schedule_cron: str | None = None  # cron-like expression; None = manual only
    created_at: datetime = field(default_factory=now_utc)
    last_sync_at: datetime | None = None
    include_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    # Issue #4421: readiness tier copied from the connector class at instance-
    # creation time (0 = zero-config, 1 = free key/env var, 2 = credentials).
    tier: int = 0
    # Issue #8145: auth type string derived from connector_class.auth_schema().__name__,
    # or None for connectors that declare no typed auth.
    auth_type: str | None = None
    # Issue #8148: max parallel source fetches; None = use connector class default.
    max_concurrency: int | None = None
    # Issue #8152: schema version — used by ConnectorRegistry.create() to detect
    # and apply config migrations before instantiation.
    config_version: int = 1
    # ADR-007: ID of the SecretsService secret holding sensitive credential fields.
    # None for connectors without auth (tier=0) or pre-migration connectors.
    secret_id: str | None = None
    # ADR-007: user/owner identifier for cross-user isolation checks.
    owner_id: str | None = None


@dataclass
class ConnectorStatus:
    """Runtime status for a connector."""

    connector_id: str
    is_healthy: bool
    last_sync_at: datetime | None
    last_sync_status: str  # "success", "failed", "running", "never"
    documents_indexed: int
    last_error: str | None = None


@dataclass
class SyncResult:
    """Summary of a completed (or failed) sync operation."""

    connector_id: str
    started_at: datetime
    completed_at: datetime | None
    status: str  # "success", "failed", "partial"
    added: int = 0
    updated: int = 0
    deleted: int = 0
    errors: List[str] = field(default_factory=list)
    # Issue #8146: True when sync resumed from a Redis checkpoint instead of
    # starting from scratch (crash-recovery path).
    resumed_from_checkpoint: bool = False
    # Issue #8149: per-source progress counters for live job state tracking.
    sources_total: int = 0
    sources_done: int = 0
    sources_failed: int = 0
