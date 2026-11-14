# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for api/log_forwarding.py (#5912, #6042), moved out of schemas_system.py (#18734).

The response models declare every field the routes return, so the published OpenAPI
contract is the shape the frontends read.
"""

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# log_forwarding.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------


LogFwdType = Literal["seq", "elasticsearch", "loki", "syslog", "webhook", "file"]
LogFwdScope = Literal["global", "per_host"]
LogFwdSyslogProtocol = Literal["udp", "tcp", "tcp_tls"]


class LogForwardingDestinationItem(BaseModel):
    """One destination in list/detail responses (#18734).

    `DestinationConfig.to_dict_sanitized()` (scripts/logging/log_forwarder.py) plus the
    health fields. Every field is declared so the OpenAPI contract, and the frontends'
    generated types, carry the real shape. Credentials arrive masked and are named
    `*_masked`: a response model never names a stored credential (#17865).
    """

    name: str
    type: LogFwdType
    enabled: bool
    url: str | None = None
    api_key_masked: str | None = Field(None, description="The stored API key as '****' + its last 4 characters")
    username: str | None = None
    password_masked: str | None = Field(None, description="'****' when a password is stored")
    index: str | None = None
    file_path: str | None = None
    min_level: str
    batch_size: int
    batch_timeout: float
    retry_count: int
    retry_delay: float
    scope: LogFwdScope
    target_hosts: List[str] = Field(default_factory=list)
    syslog_protocol: LogFwdSyslogProtocol
    ssl_verify: bool
    ssl_ca_cert: str | None = None
    ssl_client_cert: str | None = None
    ssl_client_key: str | None = None
    healthy: bool
    last_error: str | None = None
    sent_count: int
    failed_count: int


class LogForwardingDestinationsListResponse(BaseModel):
    """Response for GET /log-forwarding/destinations — returns a list directly."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# log_forwarding.py remaining schemas (#6042)
# ---------------------------------------------------------------------------


class LogFwdDestinationCreate(BaseModel):
    name: str = Field(..., description="Unique name for the destination")
    type: str = Field(
        ...,
        description="Destination type: seq, elasticsearch, loki, syslog, webhook, file",
    )
    enabled: bool = Field(True, description="Whether the destination is enabled")
    url: str | None = Field(None, description="URL/host for the destination")
    api_key: str | None = Field(None, description="API key for authentication")
    username: str | None = Field(None, description="Username for authentication")
    password: str | None = Field(None, description="Password for authentication")
    index: str | None = Field("autobot-logs", description="Index name (Elasticsearch)")
    file_path: str | None = Field(None, description="File path (file destination)")
    min_level: str = Field("Information", description="Minimum log level to forward")
    batch_size: int = Field(10, ge=1, le=1000, description="Batch size for sending")
    batch_timeout: float = Field(5.0, ge=0.1, le=60.0, description="Batch timeout in seconds")
    retry_count: int = Field(3, ge=0, le=10, description="Number of retries on failure")
    retry_delay: float = Field(1.0, ge=0.1, le=30.0, description="Delay between retries")
    scope: str = Field("global", description="Scope: global (all hosts) or per_host")
    target_hosts: List[str] = Field(default_factory=list, description="Target hosts for per_host scope")
    syslog_protocol: str = Field("udp", description="Syslog protocol: udp, tcp, tcp_tls")
    ssl_verify: bool = Field(True, description="Verify SSL certificates for TLS")
    ssl_ca_cert: str | None = Field(None, description="Path to CA certificate")
    ssl_client_cert: str | None = Field(None, description="Path to client certificate")
    ssl_client_key: str | None = Field(None, description="Path to client key")


class LogFwdDestinationUpdate(BaseModel):
    enabled: bool | None = None
    url: str | None = None
    api_key: str | None = None
    username: str | None = None
    password: str | None = None
    index: str | None = None
    file_path: str | None = None
    min_level: str | None = None
    batch_size: int | None = None
    batch_timeout: float | None = None
    retry_count: int | None = None
    retry_delay: float | None = None
    scope: str | None = None
    target_hosts: List[str] | None = None
    syslog_protocol: str | None = None
    ssl_verify: bool | None = None
    ssl_ca_cert: str | None = None
    ssl_client_cert: str | None = None
    ssl_client_key: str | None = None


class LogFwdDestinationResponse(BaseModel):
    name: str
    type: str
    enabled: bool
    url: str | None
    index: str | None
    file_path: str | None
    min_level: str
    batch_size: int
    batch_timeout: float
    scope: str
    target_hosts: List[str]
    syslog_protocol: str
    ssl_verify: bool
    healthy: bool
    last_error: str | None
    sent_count: int
    failed_count: int


class LogFwdMessageResponse(BaseModel):
    message: str


class LogFwdCreateUpdateResponse(BaseModel):
    message: str
    destination: Dict[str, Any]


class LogFwdTestResponse(BaseModel):
    name: str
    healthy: bool
    last_error: str | None = None
    message: str


class LogFwdTestAllResponse(BaseModel):
    results: Dict[str, bool]  # destination name -> healthy
    total: int
    healthy: int
    unhealthy: int


class LogFwdDestinationStatusItem(BaseModel):
    name: str
    type: str
    enabled: bool
    healthy: bool
    last_error: str | None = None
    sent_count: int
    failed_count: int
    scope: str


class LogFwdStatusResponse(BaseModel):
    running: bool
    hostname: str
    queue_size: int
    destinations: List[LogFwdDestinationStatusItem]
    total_destinations: int
    enabled_destinations: int
    healthy_destinations: int
    total_sent: int
    total_failed: int


class LogFwdDestinationTypesResponse(BaseModel):
    types: List[Any]
    scopes: List[Any]
    log_levels: List[str]
    syslog_protocols: List[Any]


class LogFwdKnownHostItem(BaseModel):
    hostname: str
    ip: str | None = None
    description: str


class LogFwdKnownHostsResponse(BaseModel):
    hosts: List[LogFwdKnownHostItem]
    current_hostname: str


class LogFwdAutoStartResponse(BaseModel):
    auto_start: bool
    message: str
