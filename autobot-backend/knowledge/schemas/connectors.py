# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Response schemas for the knowledge connector endpoints (Issue #5317)."""

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


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
    last_sync_at: str | None = None
    last_sync_status: str | None = None
    documents_indexed: int | None = None
    last_error: str | None = None
    scheduled: bool | None = None


class ConnectorConfigDict(BaseModel):
    """Config sub-object returned inside connector list / detail responses."""

    model_config = ConfigDict(extra="allow")

    connector_id: str
    connector_type: str
    name: str
    config: Dict[str, Any]
    enabled: bool
    verification_mode: str
    schedule_cron: str | None = None
    created_at: str
    last_sync_at: str | None = None
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
    completed_at: str | None = None
    status: str | None = None
    added: int | None = None
    updated: int | None = None
    deleted: int | None = None
    errors: int | None = None


class ConnectorHistoryResponse(BaseModel):
    """GET /knowledge_base/connectors/{connector_id}/history."""

    model_config = ConfigDict(extra="allow")

    connector_id: str
    history: List[ConnectorHistoryEntry]
    total: int


class CreateConnectorRequest(BaseModel):
    """Request body for POST /knowledge_base/connectors."""

    connector_type: str = Field(..., description="One of: file_server, web_crawler, database")
    name: str = Field(..., min_length=1, max_length=128)
    config: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    verification_mode: str = "collaborative"
    schedule_cron: str | None = None
    include_patterns: List[str] = Field(default_factory=list)
    exclude_patterns: List[str] = Field(default_factory=list)


class UpdateConnectorRequest(BaseModel):
    """Request body for PUT /knowledge_base/connectors/{id}."""

    name: str | None = Field(None, min_length=1, max_length=128)
    config: Dict[str, Any] | None = None
    enabled: bool | None = None
    verification_mode: str | None = None
    schedule_cron: str | None = None
    include_patterns: List[str] | None = None
    exclude_patterns: List[str] | None = None
