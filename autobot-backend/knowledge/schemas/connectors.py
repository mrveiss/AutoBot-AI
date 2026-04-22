# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Response schemas for the knowledge connector endpoints (Issue #5317)."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class ConnectorTypeEntry(BaseModel):
    """Single entry in the connector_types list."""

    model_config = ConfigDict(extra="allow")

    connector_type: str
    tier: int


class ConnectorTypesResponse(BaseModel):
    """GET /knowledge_base/connector_types."""

    model_config = ConfigDict(extra="allow")

    connector_types: List[ConnectorTypeEntry]
    total: int


class ConnectorStatusDict(BaseModel):
    """Status sub-object returned inside connector list / detail responses."""

    model_config = ConfigDict(extra="allow")

    connector_id: str
    is_healthy: bool
    last_sync_at: Optional[str] = None
    last_sync_status: Optional[str] = None
    documents_indexed: Optional[int] = None
    last_error: Optional[str] = None
    scheduled: Optional[bool] = None
    error: Optional[str] = None


class ConnectorConfigDict(BaseModel):
    """Config sub-object returned inside connector list / detail responses."""

    model_config = ConfigDict(extra="allow")

    connector_id: str
    connector_type: str
    name: str
    config: Dict[str, Any]
    enabled: bool
    verification_mode: str
    schedule_cron: Optional[str] = None
    created_at: str
    last_sync_at: Optional[str] = None
    include_patterns: List[str]
    exclude_patterns: List[str]
    tier: int


class ConnectorEntry(BaseModel):
    """One element of the connectors list."""

    model_config = ConfigDict(extra="allow")

    config: ConnectorConfigDict
    status: ConnectorStatusDict


class ConnectorsListResponse(BaseModel):
    """GET /knowledge_base/connectors."""

    model_config = ConfigDict(extra="allow")

    connectors: List[ConnectorEntry]
    total: int


class ConnectorCreateResponse(BaseModel):
    """POST /knowledge_base/connectors (201)."""

    model_config = ConfigDict(extra="allow")

    connector_id: str
    config: ConnectorConfigDict


class ConnectorsHealthResponse(BaseModel):
    """GET /knowledge_base/connectors/health."""

    model_config = ConfigDict(extra="allow")

    healthy: List[str]
    unavailable: List[str]
    errors: Dict[str, str]
    checked_at: str


class ConnectorDetailResponse(BaseModel):
    """GET /knowledge_base/connectors/{connector_id}."""

    model_config = ConfigDict(extra="allow")

    config: ConnectorConfigDict
    status: ConnectorStatusDict


class ConnectorUpdateResponse(BaseModel):
    """PUT /knowledge_base/connectors/{connector_id}."""

    model_config = ConfigDict(extra="allow")

    connector_id: str
    config: ConnectorConfigDict


class ConnectorTestResponse(BaseModel):
    """POST /knowledge_base/connectors/{connector_id}/test."""

    model_config = ConfigDict(extra="allow")

    connector_id: str
    healthy: bool


class ConnectorSyncResponse(BaseModel):
    """POST /knowledge_base/connectors/{connector_id}/sync."""

    model_config = ConfigDict(extra="allow")

    connector_id: str
    status: str
    incremental: bool


class ConnectorHistoryEntry(BaseModel):
    """Single history record stored per sync run."""

    model_config = ConfigDict(extra="allow")

    connector_id: str
    started_at: str
    completed_at: Optional[str] = None
    status: Optional[str] = None
    added: Optional[int] = None
    updated: Optional[int] = None
    deleted: Optional[int] = None
    errors: Optional[int] = None


class ConnectorHistoryResponse(BaseModel):
    """GET /knowledge_base/connectors/{connector_id}/history."""

    model_config = ConfigDict(extra="allow")

    connector_id: str
    history: List[ConnectorHistoryEntry]
    total: int
