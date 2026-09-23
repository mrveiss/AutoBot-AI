# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request/response schemas for the external MCP server admin CRUD (#11542)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from autobot_shared.auth.permissions import Role

_VALID_ROLE_NAMES = frozenset(r.value for r in Role)


def _check_allowed_roles(roles: list[str] | None) -> list[str] | None:
    if roles is None:
        return None
    unknown = [r for r in roles if r not in _VALID_ROLE_NAMES]
    if unknown:
        raise ValueError(f"unknown role(s) in allowed_roles: {unknown}; must be one of {sorted(_VALID_ROLE_NAMES)}")
    return roles


class MCPServerCreateRequest(BaseModel):
    """Admin request to register a new external MCP server."""

    name: str
    transport: str  # "stdio" | "sse" | "streamable_http"
    command: str | None = None
    url: str | None = None
    auth_type: str | None = None
    #: Shape matches SecretCreateRequest's connector-bridge fields (#16428/#16444):
    #: present-but-incomplete is a validation error, not "no credential".
    credentials: dict[str, str] | None = None
    enabled: bool = True
    #: Which platform roles may call this server's tools, on top of every
    #: caller needing Permission.MCP_EXTERNAL — admin-only unless the admin
    #: widens it (#11542, owner decision on #16458).
    allowed_roles: list[str] | None = None

    @model_validator(mode="after")
    def _validate_transport_fields(self) -> "MCPServerCreateRequest":
        if self.transport == "stdio" and not self.command:
            raise ValueError("stdio transport requires 'command'")
        if self.transport in ("sse", "streamable_http") and not self.url:
            raise ValueError(f"{self.transport} transport requires 'url'")
        if self.auth_type and self.credentials is None:
            raise ValueError("auth_type given without credentials")
        _check_allowed_roles(self.allowed_roles)
        return self


class MCPServerUpdateRequest(BaseModel):
    """Admin request to update an existing external MCP server. Omitted fields are unchanged."""

    name: str | None = None
    enabled: bool | None = None
    command: str | None = None
    url: str | None = None
    auth_type: str | None = None
    credentials: dict[str, str] | None = None
    allowed_roles: list[str] | None = None

    @model_validator(mode="after")
    def _validate_allowed_roles(self) -> "MCPServerUpdateRequest":
        _check_allowed_roles(self.allowed_roles)
        return self


class MCPServerResponse(BaseModel):
    """Public shape of a configured external MCP server — never carries a secret."""

    server_id: str
    name: str
    transport: str
    enabled: bool
    owner_id: str
    created_at: datetime
    command: str | None = None
    url: str | None = None
    auth_type: str | None = None
    allowed_roles: list[str]
    has_credential: bool = Field(description="True when a credential is stored, without exposing it")


class MCPServerListResponse(BaseModel):
    """List of configured external MCP servers."""

    servers: list[MCPServerResponse]
