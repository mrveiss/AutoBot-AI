# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Secrets API

REST endpoints for managing workflow-scoped credentials.

Secrets are stored encrypted (Fernet via SecretsService).
Values are NEVER returned in list or detail responses.

Routes:
    POST   /api/workflow-secrets          — create a secret
    GET    /api/workflow-secrets          — list secret names/metadata
    PUT    /api/workflow-secrets/{name}   — update secret value
    DELETE /api/workflow-secrets/{name}   — delete a secret

Issue #2153 — Secret management for workflow credentials.
"""

import logging
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from auth_middleware import get_current_user
from services.workflow_secret_service import (
    WorkflowSecretService,
    get_workflow_secret_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Allowed characters in a secret name — same rule as the general secrets API.
_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


def _validate_secret_name(name: str) -> str:
    """Reject names containing characters outside the safe set. Issue #2153."""
    if not _NAME_RE.match(name):
        raise ValueError(
            "Secret name must contain only alphanumeric characters, "
            "underscores, hyphens, and dots"
        )
    return name


class WorkflowSecretCreateRequest(BaseModel):
    """Request body for creating a workflow secret. Issue #2303: owner_id derived from auth."""

    name: str = Field(..., min_length=1, max_length=256)
    value: str = Field(..., min_length=1, max_length=65536)
    secret_type: str = Field(default="api_key", max_length=50)
    workflow_id: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None, max_length=1024)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Reject unsafe characters in the secret name."""
        return _validate_secret_name(v)


class WorkflowSecretUpdateRequest(BaseModel):
    """Request body for updating a workflow secret's value. Issue #2303: owner_id from auth."""

    value: str = Field(..., min_length=1, max_length=65536)


class WorkflowSecretMetadata(BaseModel):
    """Safe metadata response — no value field. Issue #2153."""

    id: str
    name: str
    secret_type: str
    scope: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _svc() -> WorkflowSecretService:
    """Dependency-like helper for the service singleton. Issue #2153."""
    return get_workflow_secret_service()


def _to_metadata(row: dict) -> WorkflowSecretMetadata:
    """Convert a SecretsService list row to the safe metadata schema."""
    return WorkflowSecretMetadata(
        id=row.get("id", ""),
        name=row.get("name", ""),
        secret_type=row.get("secret_type", ""),
        scope=row.get("scope", ""),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        description=row.get("description"),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201, response_model=WorkflowSecretMetadata)
async def create_workflow_secret(
    request: WorkflowSecretCreateRequest,
    current_user: dict = Depends(get_current_user),
) -> WorkflowSecretMetadata:
    """
    Store an encrypted workflow credential.

    The plaintext **value** is encrypted with Fernet before persistence and
    is never stored in plaintext. It cannot be retrieved via any API endpoint.

    Issue #2153, #2303.
    """
    owner_id = current_user.get("user_id", "")
    try:
        result = _svc().create_secret(
            name=request.name,
            value=request.value,
            owner_id=owner_id,
            secret_type=request.secret_type,
            workflow_id=request.workflow_id,
            description=request.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Request failed") from exc
    except Exception as exc:
        logger.error(
            "Failed to create workflow secret name=%s owner=%s: %s",
            request.name,
            owner_id,
            exc,
        )
        raise HTTPException(status_code=500, detail="Failed to store secret") from exc

    return WorkflowSecretMetadata(
        id=result.get("id", ""),
        name=result.get("name", request.name),
        secret_type=result.get("secret_type", request.secret_type),
        scope=result.get("scope", "workflow"),
        created_at=result.get("created_at"),
        description=request.description,
    )


@router.get("", response_model=List[WorkflowSecretMetadata])
async def list_workflow_secrets(
    workflow_id: Optional[str] = Query(default=None, max_length=128),
    current_user: dict = Depends(get_current_user),
) -> List[WorkflowSecretMetadata]:
    """
    List workflow secret names and metadata.

    Secret **values are never returned**. Use the ${secrets.NAME} syntax in
    workflow step commands to reference secrets at execution time.

    Issue #2153, #2303.
    """
    owner_id = current_user.get("user_id", "")
    try:
        rows = _svc().list_secrets(owner_id=owner_id, workflow_id=workflow_id)
    except Exception as exc:
        logger.error("Failed to list workflow secrets owner=%s: %s", owner_id, exc)
        raise HTTPException(status_code=500, detail="Failed to list secrets") from exc

    return [_to_metadata(row) for row in rows]


@router.put("/{name}", response_model=WorkflowSecretMetadata)
async def update_workflow_secret(
    name: str,
    request: WorkflowSecretUpdateRequest,
    current_user: dict = Depends(get_current_user),
) -> WorkflowSecretMetadata:
    """
    Replace the encrypted value of an existing workflow secret.

    The name in the path must match an existing secret owned by the caller.

    Issue #2153, #2303.
    """
    try:
        _validate_secret_name(name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Request failed") from exc

    owner_id = current_user.get("user_id", "")
    try:
        updated = _svc().update_secret(
            name=name,
            new_value=request.value,
            owner_id=owner_id,
        )
    except Exception as exc:
        logger.error(
            "Failed to update workflow secret name=%s owner=%s: %s",
            name,
            owner_id,
            exc,
        )
        raise HTTPException(status_code=500, detail="Failed to update secret") from exc

    if not updated:
        raise HTTPException(status_code=404, detail=f"Secret '{name}' not found")

    # codeql-suppress py/clear-text-logging-sensitive-data: logs name/owner metadata, not secret value
    logger.info("Workflow secret updated via API: name=%s owner=%s", name, owner_id)
    return WorkflowSecretMetadata(
        id="",
        name=name,
        secret_type="",
        scope="workflow",
    )


@router.delete("/{name}", status_code=204)
async def delete_workflow_secret(
    name: str,
    current_user: dict = Depends(get_current_user),
) -> None:
    """
    Deactivate (soft-delete) a workflow secret.

    Issue #2153, #2303.
    """
    try:
        _validate_secret_name(name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Request failed") from exc

    owner_id = current_user.get("user_id", "")
    try:
        deleted = _svc().delete_secret(name=name, owner_id=owner_id)
    except Exception as exc:
        logger.error(
            "Failed to delete workflow secret name=%s owner=%s: %s",
            name,
            owner_id,
            exc,
        )
        raise HTTPException(status_code=500, detail="Failed to delete secret") from exc

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Secret '{name}' not found")

    # codeql-suppress py/clear-text-logging-sensitive-data: logs name/owner metadata, not secret value
    logger.info("Workflow secret deleted via API: name=%s owner=%s", name, owner_id)
