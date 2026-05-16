# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Admin-only virtual LLM API key management endpoints (#6590).

Routes (all require admin permission):
  POST /llm-keys/issue   — create a new virtual key
  POST /llm-keys/revoke  — revoke a key by key_id
  POST /llm-keys/rotate  — rotate a key (old hash stays valid for grace period)
  GET  /llm-keys/list    — list keys with current-month spend
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from services.llm_api_key_service import get_llm_api_key_service

router = APIRouter(tags=["llm-keys"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class IssueKeyRequest(BaseModel):
    team_id: str
    label: str = ""
    monthly_budget_usd: float = 0.0
    allowed_models: List[str] = []
    expires_at: float | None = None


class IssueKeyResponse(BaseModel):
    key_id: str
    raw_key: str  # shown exactly once — caller must store it
    team_id: str
    label: str
    monthly_budget_usd: float
    allowed_models: List[str]
    expires_at: float | None


class RevokeKeyRequest(BaseModel):
    key_id: str


class RotateKeyRequest(BaseModel):
    key_id: str


class RotateKeyResponse(BaseModel):
    key_id: str
    new_raw_key: str  # shown exactly once


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/issue", response_model=IssueKeyResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="issue_llm_key",
    error_code_prefix="LLM_KEYS",
)
async def issue_key(
    body: IssueKeyRequest,
    _user: Any = Depends(check_admin_permission),
) -> IssueKeyResponse:
    """Issue a new virtual LLM API key."""
    svc = get_llm_api_key_service()
    record, raw_key = await svc.issue_key(
        team_id=body.team_id,
        label=body.label,
        monthly_budget_usd=body.monthly_budget_usd,
        allowed_models=body.allowed_models,
        expires_at=body.expires_at,
    )
    return IssueKeyResponse(
        key_id=record.key_id,
        raw_key=raw_key,
        team_id=record.team_id,
        label=record.label,
        monthly_budget_usd=record.monthly_budget_usd,
        allowed_models=record.allowed_models,
        expires_at=record.expires_at,
    )


@router.post("/revoke")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="revoke_llm_key",
    error_code_prefix="LLM_KEYS",
)
async def revoke_key(
    body: RevokeKeyRequest,
    _user: Any = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Revoke a virtual LLM API key."""
    svc = get_llm_api_key_service()
    found = await svc.revoke_key(body.key_id)
    if not found:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"ok": True, "key_id": body.key_id}


@router.post("/rotate", response_model=RotateKeyResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rotate_llm_key",
    error_code_prefix="LLM_KEYS",
)
async def rotate_key(
    body: RotateKeyRequest,
    _user: Any = Depends(check_admin_permission),
) -> RotateKeyResponse:
    """Rotate a virtual LLM API key. Old key stays valid for grace period."""
    svc = get_llm_api_key_service()
    result = await svc.rotate_key(body.key_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Key not found or revoked")
    record, new_raw = result
    return RotateKeyResponse(key_id=record.key_id, new_raw_key=new_raw)


@router.get("/list")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_llm_keys",
    error_code_prefix="LLM_KEYS",
)
async def list_keys(
    team_id: str | None = Query(None),
    _user: Any = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """List virtual LLM API keys with current-month spend."""
    svc = get_llm_api_key_service()
    keys = await svc.list_keys(team_id=team_id)
    return {"keys": keys}
