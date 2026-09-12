# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin CRUD for user-configured external MCP servers (#11542).

Router-level admin gate: every route here requires check_admin_permission —
a stdio command is a subprocess AutoBot spawns, and a remote URL is
credentialed outbound traffic, so configuring one is an admin action, not a
login-only one (contrast api/knowledge_crawl.py's #16375 login-only routes).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from api.schemas_mcp_external_servers import (
    MCPServerCreateRequest,
    MCPServerListResponse,
    MCPServerResponse,
    MCPServerUpdateRequest,
)
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.auth.connector_auth import validate_config_against_schema
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from knowledge.connectors.credential_store import get_credential_store
from services.mcp_external_servers import MCPServerConfig, get_mcp_external_server_store
from services.mcp_launcher_allowlist import LauncherNotAllowedError
from services.mcp_server_credentials import resolve_auth_class

logger = get_logger(__name__)

router = APIRouter(
    tags=["mcp-external-servers"],
    dependencies=[Depends(check_admin_permission)],
)


async def _audit(operation: str, result: str, user: dict, server_id: str, **details) -> None:
    from services.audit_logger import audit_log  # noqa: PLC0415

    caller_id = str(user.get("user_id") or user.get("sub") or user.get("username") or "")
    await audit_log(operation, result=result, user_id=caller_id, resource=server_id, details=details)


def _caller_id(user: dict) -> str:
    caller_id = str(user.get("user_id") or user.get("sub") or user.get("username") or "")
    if not caller_id:
        raise HTTPException(status_code=401, detail="Authenticated caller has no resolvable identity")
    return caller_id


def _to_response(cfg: MCPServerConfig) -> MCPServerResponse:
    return MCPServerResponse(
        server_id=cfg.server_id,
        name=cfg.name,
        transport=cfg.transport,
        enabled=cfg.enabled,
        owner_id=cfg.owner_id,
        created_at=cfg.created_at,
        command=cfg.command,
        url=cfg.url,
        auth_type=cfg.auth_type,
        has_credential=cfg.secret_id is not None,
    )


async def _store_credentials(server_id: str, owner_id: str, auth_type: str, credentials: dict) -> tuple[str, dict]:
    """Validate then store *credentials* for *auth_type*, returning (secret_id, sanitized_auth_config)."""
    auth_cls = resolve_auth_class(auth_type)
    if auth_cls is None:
        raise HTTPException(status_code=422, detail=f"Unknown auth_type: {auth_type!r}")
    errors = validate_config_against_schema(auth_cls, credentials)
    if errors:
        raise HTTPException(status_code=422, detail=f"Auth config invalid for {auth_type}: {'; '.join(errors)}")
    secret_id, sanitized = await get_credential_store().store(
        connector_id=server_id, owner_id=owner_id, auth_cls=auth_cls, config=credentials
    )
    return secret_id, sanitized


@router.get("/external_servers", response_model=MCPServerListResponse)
@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="list_mcp_external_servers")
async def list_external_servers() -> MCPServerListResponse:
    """List every configured external MCP server."""
    servers = await get_mcp_external_server_store().list()
    return MCPServerListResponse(servers=[_to_response(s) for s in servers])


@router.get("/external_servers/{server_id}", response_model=MCPServerResponse)
@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="get_mcp_external_server")
async def get_external_server(server_id: str) -> MCPServerResponse:
    """Return one configured external MCP server."""
    cfg = await get_mcp_external_server_store().get(server_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"MCP server {server_id!r} not found")
    return _to_response(cfg)


@router.post("/external_servers", status_code=201, response_model=MCPServerResponse)
@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="create_mcp_external_server")
async def create_external_server(
    request: MCPServerCreateRequest, user: dict = Depends(get_current_user)
) -> MCPServerResponse:
    """Register a new external MCP server. Validates the stdio launcher allowlist and auth schema."""
    owner_id = _caller_id(user)
    server_id = str(uuid.uuid4())

    secret_id: str | None = None
    auth_config: dict = {}
    if request.auth_type:
        secret_id, auth_config = await _store_credentials(server_id, owner_id, request.auth_type, request.credentials)

    cfg = MCPServerConfig(
        server_id=server_id,
        name=request.name,
        transport=request.transport,
        owner_id=owner_id,
        enabled=request.enabled,
        command=request.command,
        url=request.url,
        auth_type=request.auth_type,
        secret_id=secret_id,
        auth_config=auth_config,
    )
    try:
        cfg.validate()
    except (ValueError, LauncherNotAllowedError) as exc:
        if secret_id:
            await get_credential_store().revoke(secret_id, owner_id)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await get_mcp_external_server_store().create(cfg)
    await _audit("mcp.external_server.create", "success", user, server_id, transport=cfg.transport)
    logger.info("Created external MCP server %s (%s)", server_id, cfg.transport)
    return _to_response(cfg)


@router.put("/external_servers/{server_id}", response_model=MCPServerResponse)
@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="update_mcp_external_server")
async def update_external_server(
    server_id: str, request: MCPServerUpdateRequest, user: dict = Depends(get_current_user)
) -> MCPServerResponse:
    """Update an existing external MCP server. Omitted fields are left unchanged.

    A new ``credentials`` payload replaces the stored credential (old one
    revoked after the new one is validated and stored, never before).
    """
    owner_id = _caller_id(user)
    store = get_mcp_external_server_store()
    cfg = await store.get(server_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"MCP server {server_id!r} not found")

    for field_name in ("name", "enabled", "command", "url"):
        value = getattr(request, field_name)
        if value is not None:
            setattr(cfg, field_name, value)

    old_secret_id = cfg.secret_id
    if request.auth_type is not None:
        if request.credentials is None:
            raise HTTPException(status_code=422, detail="auth_type given without credentials")
        cfg.secret_id, cfg.auth_config = await _store_credentials(
            server_id, owner_id, request.auth_type, request.credentials
        )
        cfg.auth_type = request.auth_type

    try:
        cfg.validate()
    except (ValueError, LauncherNotAllowedError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await store.update(cfg)
    if request.auth_type is not None and old_secret_id and old_secret_id != cfg.secret_id:
        await get_credential_store().revoke(old_secret_id, cfg.owner_id)

    await _audit("mcp.external_server.update", "success", user, server_id)
    return _to_response(cfg)


@router.delete("/external_servers/{server_id}", status_code=204, response_model=None)
@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="delete_mcp_external_server")
async def delete_external_server(server_id: str, user: dict = Depends(get_current_user)) -> None:
    """Delete an external MCP server and revoke its stored credential, if any."""
    store = get_mcp_external_server_store()
    cfg = await store.get(server_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"MCP server {server_id!r} not found")

    await store.delete(server_id)
    if cfg.secret_id:
        await get_credential_store().revoke(cfg.secret_id, cfg.owner_id)

    await _audit("mcp.external_server.delete", "success", user, server_id)
