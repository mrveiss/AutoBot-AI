# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Admin API: Data Retention Policy CRUD Endpoints (MVA-3145, GH#8995)

Endpoints:
    GET    /api/admin/retention-policies       - List all policies
    POST   /api/admin/retention-policies       - Create/update policy
    GET    /api/admin/retention-policies/{type} - Get policy by type
    DELETE /api/admin/retention-policies/{type} - Delete policy by type

Access: admin role required (RBAC enforced).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_db_session
from auth_middleware import get_auth_middleware
from user_management.models.retention_policy import RetentionPolicy
from user_management.schemas.retention_policy import (
    PolicyType,
    RetentionPolicyCreate,
    RetentionPolicyListResponse,
    RetentionPolicyResponse,
)
from utils.catalog_http_exceptions import raise_auth_error

router = APIRouter(prefix="/admin")


def _require_admin(request: Request) -> dict:
    """Dependency: reject non-admin callers and return user data."""
    user_data = get_auth_middleware().get_user_from_request(request)
    if not user_data:
        raise_auth_error("AUTH_0002", "Authentication required")
    if user_data.get("role") != "admin":
        raise_auth_error("AUTH_0003", "Admin permission required")
    return user_data


@router.get("/retention-policies", response_model=RetentionPolicyListResponse)
async def list_retention_policies(
    request: Request,
    user_id: uuid.UUID | None = Query(None, description="Filter by user_id (NULL = global)"),
    _admin: dict = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> RetentionPolicyListResponse:
    """
    List all retention policies.

    Query filters:
    - user_id: Filter by user_id (omit to get all policies)

    Returns both global policies (user_id=NULL) and user-specific overrides.
    """
    query = select(RetentionPolicy)

    if user_id is not None:
        query = query.where(RetentionPolicy.user_id == user_id)

    result = await session.execute(query.order_by(RetentionPolicy.policy_type))
    policies = result.scalars().all()

    return RetentionPolicyListResponse(
        count=len(policies),
        policies=[RetentionPolicyResponse.model_validate(p) for p in policies],
    )


@router.post("/retention-policies", response_model=RetentionPolicyResponse)
async def create_or_update_retention_policy(
    request: Request,
    policy: RetentionPolicyCreate,
    _admin: dict = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> RetentionPolicyResponse:
    """
    Create or update a retention policy.

    Upsert semantics: if a policy already exists for (policy_type, user_id),
    update it; otherwise create a new one.

    User-specific policies override global defaults.
    """
    # Check if policy already exists
    query = select(RetentionPolicy).where(
        RetentionPolicy.policy_type == policy.policy_type,
        RetentionPolicy.user_id == policy.user_id,
    )
    result = await session.execute(query)
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing policy
        existing.retention_days = policy.retention_days
        existing.anonymize_instead_of_delete = policy.anonymize_instead_of_delete
        await session.commit()
        await session.refresh(existing)
        return RetentionPolicyResponse.model_validate(existing)
    else:
        # Create new policy
        new_policy = RetentionPolicy(
            policy_type=policy.policy_type,
            retention_days=policy.retention_days,
            user_id=policy.user_id,
            anonymize_instead_of_delete=policy.anonymize_instead_of_delete,
        )
        session.add(new_policy)
        await session.commit()
        await session.refresh(new_policy)
        return RetentionPolicyResponse.model_validate(new_policy)


@router.get("/retention-policies/{policy_type}", response_model=RetentionPolicyResponse)
async def get_retention_policy(
    request: Request,
    policy_type: PolicyType,
    user_id: uuid.UUID | None = Query(None, description="User ID for user-specific policy"),
    _admin: dict = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> RetentionPolicyResponse:
    """
    Get a specific retention policy by type and optional user_id.

    Resolution order:
    1. If user_id provided, return user-specific policy if exists
    2. Fall back to global policy (user_id=NULL)
    3. Return 404 if no policy found
    """
    # Try user-specific policy first if user_id provided
    if user_id is not None:
        query = select(RetentionPolicy).where(
            RetentionPolicy.policy_type == policy_type,
            RetentionPolicy.user_id == user_id,
        )
        result = await session.execute(query)
        policy = result.scalar_one_or_none()
        if policy:
            return RetentionPolicyResponse.model_validate(policy)

    # Fall back to global policy
    query = select(RetentionPolicy).where(
        RetentionPolicy.policy_type == policy_type,
        RetentionPolicy.user_id.is_(None),
    )
    result = await session.execute(query)
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retention policy not found for type: {policy_type}",
        )

    return RetentionPolicyResponse.model_validate(policy)


@router.delete("/retention-policies/{policy_type}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_retention_policy(
    request: Request,
    policy_type: PolicyType,
    user_id: uuid.UUID | None = Query(None, description="User ID for user-specific policy"),
    _admin: dict = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """
    Delete a retention policy by type and optional user_id.

    If user_id is provided, deletes user-specific policy.
    If user_id is NULL, deletes global policy.
    """
    query = select(RetentionPolicy).where(
        RetentionPolicy.policy_type == policy_type,
        RetentionPolicy.user_id == user_id if user_id is not None else RetentionPolicy.user_id.is_(None),
    )
    result = await session.execute(query)
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retention policy not found for type: {policy_type}",
        )

    await session.delete(policy)
    await session.commit()
