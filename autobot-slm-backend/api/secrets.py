# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
System Secrets API Routes (#1417)

Encrypted storage for internal system tokens (HF_TOKEN, API keys, etc.).
Admin-only — secrets are not exposed to end users.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from autobot_shared.auth.permissions import Permission
from models.database import Node, SystemSecret
from models.schemas import (
    ApplySecretsRequest,
    ApplySecretsResponse,
    SecretCreate,
    SecretResponse,
    SecretUpdate,
)
from services.ansible_secrets import _SECRET_TO_DEPENDENT_ROLES
from services.auth import require_permission
from services.database import get_db
from services.encryption import decrypt_data, encrypt_data

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/secrets", tags=["secrets"])


@router.get("", response_model=List[SecretResponse])
async def list_secrets(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_permission(Permission.SECURITY_MANAGE))],
) -> List[SecretResponse]:
    """List all system secrets (values never returned)."""
    result = await db.execute(select(SystemSecret).order_by(SystemSecret.key))
    return [SecretResponse.model_validate(s) for s in result.scalars().all()]


@router.post(
    "",
    response_model=SecretResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_secret(
    data: SecretCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_permission(Permission.SECURITY_MANAGE))],
) -> SecretResponse:
    """Create a new system secret (admin only)."""
    existing = await db.execute(select(SystemSecret).where(SystemSecret.key == data.key))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Secret '{data.key}' already exists",
        )

    secret = SystemSecret(
        key=data.key,
        encrypted_value=encrypt_data(data.value),
        category=data.category,
        description=data.description,
    )
    db.add(secret)
    await db.commit()
    await db.refresh(secret)

    logger.info("System secret created: %s [%s]", data.key, data.category)
    return SecretResponse.model_validate(secret)


@router.get("/dependent-roles")
async def get_dependent_roles_mapping(
    _: Annotated[dict, Depends(require_permission(Permission.SECURITY_MANAGE))],
) -> dict:
    """Return the secret-key -> dependent-role mapping for apply-secrets (#11719).

    Single source of truth is _SECRET_TO_DEPENDENT_ROLES in
    services/ansible_secrets.py; the frontend uses this to decide whether to
    show the "Apply to services" action for a given secret key.
    """
    return {"mapping": _SECRET_TO_DEPENDENT_ROLES}


@router.get("/{key}", response_model=SecretResponse)
async def get_secret(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_permission(Permission.SECURITY_MANAGE))],
) -> SecretResponse:
    """Get a system secret metadata (value never returned)."""
    result = await db.execute(select(SystemSecret).where(SystemSecret.key == key))
    secret = result.scalar_one_or_none()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Secret not found",
        )
    return SecretResponse.model_validate(secret)


@router.get("/{key}/value")
async def get_secret_value(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_permission(Permission.SECURITY_MANAGE))],
) -> dict:
    """Get a decrypted secret value (admin only, for fleet provisioning)."""
    result = await db.execute(select(SystemSecret).where(SystemSecret.key == key))
    secret = result.scalar_one_or_none()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Secret not found",
        )
    return {"key": secret.key, "value": decrypt_data(secret.encrypted_value)}


@router.put("/{key}", response_model=SecretResponse)
async def update_secret(
    key: str,
    data: SecretUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_permission(Permission.SECURITY_MANAGE))],
) -> SecretResponse:
    """Update a system secret (admin only)."""
    result = await db.execute(select(SystemSecret).where(SystemSecret.key == key))
    secret = result.scalar_one_or_none()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Secret not found",
        )

    if data.value is not None:
        secret.encrypted_value = encrypt_data(data.value)
    if data.category is not None:
        secret.category = data.category
    if data.description is not None:
        secret.description = data.description

    await db.commit()
    await db.refresh(secret)

    logger.info("System secret updated: %s", key)
    return SecretResponse.model_validate(secret)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_permission(Permission.SECURITY_MANAGE))],
) -> None:
    """Delete a system secret (admin only)."""
    result = await db.execute(select(SystemSecret).where(SystemSecret.key == key))
    secret = result.scalar_one_or_none()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Secret not found",
        )

    await db.delete(secret)
    await db.commit()
    logger.info("System secret deleted: %s", key)


@router.post("/apply", response_model=ApplySecretsResponse)
async def apply_secret(
    payload: ApplySecretsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_permission(Permission.SECURITY_MANAGE))],
) -> ApplySecretsResponse:
    """Propagate a stored secret to its dependent services (#11719).

    Re-renders only the env-file template(s) of the roles that consume this
    secret (see services.ansible_secrets._SECRET_TO_DEPENDENT_ROLES) and
    restarts the affected systemd service(s), limited to the nodes hosting
    those roles -- no full role redeploy required.
    """
    dependent_roles = _SECRET_TO_DEPENDENT_ROLES.get(payload.key)
    if not dependent_roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Secret '{payload.key}' has no lightweight apply mapping — "
                "use the role's Migrate/Redeploy action instead"
            ),
        )

    target_node_ids = await _find_node_ids_for_roles(db, dependent_roles)
    if not target_node_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No nodes are currently running roles that depend on " f"'{payload.key}': {', '.join(dependent_roles)}"
            ),
        )

    return await _run_apply_secrets(payload.key, dependent_roles, target_node_ids)  # codeql[py/stack-trace-exposure]


async def _find_node_ids_for_roles(db: AsyncSession, role_names: List[str]) -> List[str]:
    """Return node_ids whose Node.roles JSON column includes any of role_names (#11719).

    Filtering happens in Python (not a DB-side JSON-contains query) so this
    works identically across the SQLite and Postgres backends — same pattern
    as _get_active_role_names in api/roles.py.
    """
    result = await db.execute(select(Node.node_id, Node.roles))
    role_set = set(role_names)
    return [node_id for node_id, roles in result.all() if roles and role_set.intersection(roles)]


async def _run_apply_secrets(
    key: str,
    dependent_roles: List[str],
    target_node_ids: List[str],
) -> ApplySecretsResponse:
    """Execute the apply-secrets playbook limited to target nodes (#11719)."""
    from services.playbook_executor import PlaybookExecutor

    executor = PlaybookExecutor()
    logger.info(
        "Applying secret %s to roles %s on nodes %s",
        key,
        dependent_roles,
        target_node_ids,
    )
    result = await executor.execute_playbook(
        playbook_name="apply-secrets.yml",
        limit=target_node_ids,
        extra_vars={"apply_roles_csv": ",".join(dependent_roles)},
    )
    logger.info("Apply-secrets for %s: success=%s", key, result["success"])
    return ApplySecretsResponse(
        success=result["success"],
        key=key,
        dependent_roles=dependent_roles,
        target_node_ids=target_node_ids,
        output=result["output"],
        returncode=result["returncode"],
    )
