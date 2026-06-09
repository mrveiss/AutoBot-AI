# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: MCP client token management (Issue #6453).

Endpoints:
    POST   /api/mcp/tokens         — generate a new scoped MCP client token
    GET    /api/mcp/tokens         — list active tokens (masked secret + last-used)
    DELETE /api/mcp/tokens/{token_id} — revoke a token

Access: admin or superadmin role required.

Redis storage layout:
    mcp:token:by_secret:{secret}  → JSON record {token_id, scopes, label,
                                                  created_at, last_used}
    mcp:tokens:index              → Redis set of token_ids
    mcp:token:id:{token_id}       → secret (reverse-lookup for revoke)
"""

import json
import secrets
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field

from auth_middleware import get_auth_middleware
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from utils.catalog_http_exceptions import raise_auth_error

logger = get_logger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp", "admin", "mcp-tokens"])

_VALID_SCOPES = {"kb", "memory", "agents"}
_SECRET_BYTES = 32  # 256-bit entropy


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CreateTokenRequest(BaseModel):
    scopes: List[str] = Field(..., description="List of scopes: kb, memory, agents")
    label: str = Field(default="", description="Human-readable label for this token")


class TokenRecord(BaseModel):
    token_id: str
    label: str
    scopes: List[str]
    created_at: float
    last_used: float | None
    masked_secret: str  # first 4 chars + "..."


class CreateTokenResponse(BaseModel):
    token_id: str
    token: str  # full "<secret>:<scopes>" — shown once, never again
    scopes: List[str]
    label: str


class ListTokensResponse(BaseModel):
    tokens: List[TokenRecord]
    count: int


class RevokeTokenResponse(BaseModel):
    revoked: bool
    token_id: str


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def _require_admin(request: Request) -> bool:
    """Dependency: reject callers without admin or superadmin role."""
    user_data = get_auth_middleware().get_user_from_request(request)
    if not user_data:
        raise_auth_error("AUTH_0002", "Authentication required")
    role = user_data.get("role", "")
    if role not in ("admin", "superadmin"):
        raise_auth_error("AUTH_0003", "Admin permission required")
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_redis():
    """Return async Redis client or raise 503."""
    redis = await get_async_redis_client(database="main")
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return redis


def _record_key(secret: str) -> str:
    return f"mcp:token:by_secret:{secret}"


def _id_key(token_id: str) -> str:
    return f"mcp:token:id:{token_id}"


_INDEX_KEY = "mcp:tokens:index"


# ---------------------------------------------------------------------------
# POST /api/mcp/tokens
# ---------------------------------------------------------------------------


@router.post("/tokens", response_model=CreateTokenResponse, status_code=201)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_mcp_token",
    error_code_prefix="MCP",
)
async def create_mcp_token(
    body: CreateTokenRequest,
    _admin: bool = Depends(_require_admin),
) -> CreateTokenResponse:
    """Generate a new scoped MCP client token.

    The full token string (``<secret>:<scopes>``) is returned **once** in the
    response and is never stored in plaintext — only the secret is kept in
    Redis as a lookup key.  Callers must save the token immediately.

    Valid scopes: ``kb``, ``memory``, ``agents``.
    """
    invalid = set(body.scopes) - _VALID_SCOPES
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid scopes: {sorted(invalid)}. Allowed: {sorted(_VALID_SCOPES)}",
        )
    if not body.scopes:
        raise HTTPException(status_code=422, detail="At least one scope is required")

    secret = secrets.token_hex(_SECRET_BYTES)
    token_id = secrets.token_hex(8)  # 16-char hex ID
    scopes = sorted(set(body.scopes))
    now = time.time()

    record = {
        "token_id": token_id,
        "scopes": scopes,
        "label": body.label,
        "created_at": now,
        "last_used": None,
    }

    redis = await _get_redis()
    pipe = redis.pipeline()
    pipe.set(_record_key(secret), json.dumps(record, ensure_ascii=False))
    pipe.set(_id_key(token_id), secret)
    pipe.sadd(_INDEX_KEY, token_id)
    await pipe.execute()

    token_string = f"{secret}:{','.join(scopes)}"
    logger.info(
        "mcp_token created token_id=%s scopes=%s label=%r",
        token_id,
        scopes,
        body.label,
    )
    return CreateTokenResponse(
        token_id=token_id,
        token=token_string,
        scopes=scopes,
        label=body.label,
    )


# ---------------------------------------------------------------------------
# GET /api/mcp/tokens
# ---------------------------------------------------------------------------


@router.get("/tokens", response_model=ListTokensResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_mcp_tokens",
    error_code_prefix="MCP",
)
async def list_mcp_tokens(
    _admin: bool = Depends(_require_admin),
) -> ListTokensResponse:
    """List all active MCP tokens.

    Secrets are masked (first 4 characters followed by ``...``) so the
    response is safe to log and display in the admin UI.
    """
    redis = await _get_redis()

    token_ids = await redis.smembers(_INDEX_KEY)
    records: List[TokenRecord] = []

    for tid in token_ids:
        tid_str = tid if isinstance(tid, str) else tid.decode("utf-8")
        secret_raw = await redis.get(_id_key(tid_str))
        if secret_raw is None:
            # Orphaned index entry — skip silently
            continue
        secret = secret_raw if isinstance(secret_raw, str) else secret_raw.decode("utf-8")
        raw = await redis.get(_record_key(secret))
        if raw is None:
            continue
        data = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
        records.append(
            TokenRecord(
                token_id=data["token_id"],
                label=data.get("label", ""),
                scopes=data.get("scopes", []),
                created_at=data["created_at"],
                last_used=data.get("last_used"),
                masked_secret=secret[:4] + "...",
            )
        )

    records.sort(key=lambda r: r.created_at, reverse=True)
    return ListTokensResponse(tokens=records, count=len(records))


# ---------------------------------------------------------------------------
# DELETE /api/mcp/tokens/{token_id}
# ---------------------------------------------------------------------------


@router.delete("/tokens/{token_id}", response_model=RevokeTokenResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="revoke_mcp_token",
    error_code_prefix="MCP",
)
async def revoke_mcp_token(
    token_id: str = Path(..., description="Token ID to revoke"),
    _admin: bool = Depends(_require_admin),
) -> RevokeTokenResponse:
    """Revoke an MCP token by its ID.

    Removes the token record, the reverse-lookup key, and the index entry.
    Revocation takes effect immediately — the next request using the token
    will be rejected by ``AutoBotMCPServer._validate_redis_token()``.
    """
    redis = await _get_redis()

    secret_raw = await redis.get(_id_key(token_id))
    if secret_raw is None:
        raise HTTPException(status_code=404, detail=f"Token not found: {token_id}")

    secret = secret_raw if isinstance(secret_raw, str) else secret_raw.decode("utf-8")

    pipe = redis.pipeline()
    pipe.delete(_record_key(secret))
    pipe.delete(_id_key(token_id))
    pipe.srem(_INDEX_KEY, token_id)
    await pipe.execute()

    logger.info("mcp_token revoked token_id=%s", token_id)
    return RevokeTokenResponse(revoked=True, token_id=token_id)
