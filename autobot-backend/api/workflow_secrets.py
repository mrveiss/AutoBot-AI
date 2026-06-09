# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas_system import _validate_secret_name
from api.schemas_workflows import (
    WorkflowSecretCreateRequest,
    WorkflowSecretMetadata,
    WorkflowSecretUpdateRequest,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.workflow_secret_service import (
    WorkflowSecretService,
    get_workflow_secret_service,
)

logger = get_logger(__name__)

router = APIRouter()


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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_workflow_secret",
    error_code_prefix="WORKFLOW_SECRETS",
)
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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_workflow_secrets",
    error_code_prefix="WORKFLOW_SECRETS",
)
async def list_workflow_secrets(
    workflow_id: str | None = Query(default=None, max_length=128),
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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_workflow_secret",
    error_code_prefix="WORKFLOW_SECRETS",
)
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

    # codeql[py/clear-text-logging-sensitive-data]
    logger.info("Workflow secret updated via API: name=%s owner=%s", name, owner_id)
    return WorkflowSecretMetadata(
        id="",
        name=name,
        secret_type="",
        scope="workflow",
    )


@router.delete("/{name}", status_code=204, response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_workflow_secret",
    error_code_prefix="WORKFLOW_SECRETS",
)
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

    # codeql[py/clear-text-logging-sensitive-data]
    logger.info("Workflow secret deleted via API: name=%s owner=%s", name, owner_id)
