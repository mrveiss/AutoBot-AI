# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Retention Policy API Integration Tests (MVA-3145, GH#8995)

Tests for data retention policy CRUD endpoints:
- Creating global and user-specific policies
- Policy resolution (user-specific overrides global)
- Updating and deleting policies
- Admin RBAC enforcement
- Validation constraints
"""

import uuid
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio.session import async_sessionmaker
from sqlalchemy.pool import StaticPool

from api.admin_retention_policies import _require_admin
from api.admin_retention_policies import router as retention_router
from api.user_management.dependencies import get_db_session
from user_management.models.base import Base
from user_management.models.retention_policy import RetentionPolicy
from user_management.models.user import User

# Test database setup
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def test_db_engine():
    """Create an in-memory test database engine."""
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def test_db_session(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session = async_sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session


@pytest.fixture
def admin_user():
    """Mock admin user."""
    return {
        "id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "email": "admin@example.com",
        "role": "admin",
    }


@pytest.fixture
def regular_user():
    """Mock regular user (non-admin)."""
    return {
        "id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "email": "user@example.com",
        "role": "user",
    }


@pytest.fixture
def test_client_admin(test_db_session, admin_user):
    """Create a test FastAPI client with admin user."""
    app = FastAPI()
    app.include_router(retention_router, prefix="/api")

    # Override dependencies
    app.dependency_overrides[get_db_session] = lambda: test_db_session
    app.dependency_overrides[_require_admin] = lambda: admin_user

    return TestClient(app)


@pytest.fixture
def test_client_regular(test_db_session, regular_user):
    """Create a test FastAPI client with regular user (should be rejected)."""
    app = FastAPI()
    app.include_router(retention_router, prefix="/api")

    # Override dependencies
    app.dependency_overrides[get_db_session] = lambda: test_db_session

    # Regular user will fail admin check
    def reject_non_admin():
        from utils.catalog_http_exceptions import raise_auth_error

        raise_auth_error("AUTH_0003", "Admin permission required")

    app.dependency_overrides[_require_admin] = reject_non_admin

    return TestClient(app)


@pytest.mark.asyncio
async def test_create_global_policy(test_client_admin, test_db_session):
    """Test creating a global retention policy."""
    response = test_client_admin.post(
        "/api/admin/retention-policies",
        json={
            "policy_type": "chat",
            "retention_days": 90,
            "anonymize_instead_of_delete": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["policy_type"] == "chat"
    assert data["retention_days"] == 90
    assert data["user_id"] is None
    assert data["anonymize_instead_of_delete"] is False
    assert "id" in data
    assert "created_at" in data

    # Verify in database
    result = await test_db_session.execute(select(RetentionPolicy).where(RetentionPolicy.policy_type == "chat"))
    policy = result.scalar_one()
    assert policy.retention_days == 90


@pytest.mark.asyncio
async def test_create_user_specific_policy(test_client_admin, test_db_session):
    """Test creating a user-specific retention policy override."""
    user_id = str(uuid.uuid4())

    response = test_client_admin.post(
        "/api/admin/retention-policies",
        json={
            "policy_type": "file",
            "retention_days": 30,
            "user_id": user_id,
            "anonymize_instead_of_delete": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["policy_type"] == "file"
    assert data["retention_days"] == 30
    assert data["user_id"] == user_id
    assert data["anonymize_instead_of_delete"] is True


@pytest.mark.asyncio
async def test_upsert_policy(test_client_admin, test_db_session):
    """Test upserting (create then update) a policy."""
    # Create initial policy
    response1 = test_client_admin.post(
        "/api/admin/retention-policies",
        json={
            "policy_type": "audit",
            "retention_days": 365,
            "anonymize_instead_of_delete": False,
        },
    )
    assert response1.status_code == 200
    policy_id_1 = response1.json()["id"]

    # Update same policy (upsert)
    response2 = test_client_admin.post(
        "/api/admin/retention-policies",
        json={
            "policy_type": "audit",
            "retention_days": 730,  # Changed
            "anonymize_instead_of_delete": True,  # Changed
        },
    )
    assert response2.status_code == 200
    policy_id_2 = response2.json()["id"]

    # Should be same policy ID (updated, not created new)
    assert policy_id_1 == policy_id_2
    assert response2.json()["retention_days"] == 730
    assert response2.json()["anonymize_instead_of_delete"] is True


@pytest.mark.asyncio
async def test_list_policies(test_client_admin, test_db_session):
    """Test listing all retention policies."""
    # Create multiple policies
    test_client_admin.post(
        "/api/admin/retention-policies",
        json={"policy_type": "chat", "retention_days": 90},
    )
    test_client_admin.post(
        "/api/admin/retention-policies",
        json={"policy_type": "file", "retention_days": 180},
    )

    response = test_client_admin.get("/api/admin/retention-policies")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["policies"]) == 2

    policy_types = {p["policy_type"] for p in data["policies"]}
    assert policy_types == {"chat", "file"}


@pytest.mark.asyncio
async def test_get_policy_by_type(test_client_admin, test_db_session):
    """Test retrieving a specific policy by type."""
    # Create policy
    test_client_admin.post(
        "/api/admin/retention-policies",
        json={"policy_type": "kb", "retention_days": 730},
    )

    response = test_client_admin.get("/api/admin/retention-policies/kb")

    assert response.status_code == 200
    data = response.json()
    assert data["policy_type"] == "kb"
    assert data["retention_days"] == 730


@pytest.mark.asyncio
async def test_get_policy_not_found(test_client_admin, test_db_session):
    """Test retrieving a non-existent policy."""
    response = test_client_admin.get("/api/admin/retention-policies/chat")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_policy_resolution_user_override(test_client_admin, test_db_session):
    """Test that user-specific policies override global policies."""
    user_id = str(uuid.uuid4())

    # Create global policy
    test_client_admin.post(
        "/api/admin/retention-policies",
        json={"policy_type": "chat", "retention_days": 90},
    )

    # Create user-specific override
    test_client_admin.post(
        "/api/admin/retention-policies",
        json={
            "policy_type": "chat",
            "retention_days": 30,
            "user_id": user_id,
        },
    )

    # Get policy for specific user (should return user override)
    response = test_client_admin.get(f"/api/admin/retention-policies/chat?user_id={user_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["retention_days"] == 30  # User override, not global 90
    assert data["user_id"] == user_id


@pytest.mark.asyncio
async def test_delete_policy(test_client_admin, test_db_session):
    """Test deleting a retention policy."""
    # Create policy
    test_client_admin.post(
        "/api/admin/retention-policies",
        json={"policy_type": "file", "retention_days": 60},
    )

    # Delete policy
    response = test_client_admin.delete("/api/admin/retention-policies/file")

    assert response.status_code == 204

    # Verify deleted
    get_response = test_client_admin.get("/api/admin/retention-policies/file")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_policy_not_found(test_client_admin, test_db_session):
    """Test deleting a non-existent policy."""
    response = test_client_admin.delete("/api/admin/retention-policies/audit")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_validation_retention_days_positive(test_client_admin, test_db_session):
    """Test that retention_days must be positive."""
    response = test_client_admin.post(
        "/api/admin/retention-policies",
        json={"policy_type": "chat", "retention_days": 0},
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_validation_retention_days_max(test_client_admin, test_db_session):
    """Test that retention_days has max limit (10 years)."""
    response = test_client_admin.post(
        "/api/admin/retention-policies",
        json={"policy_type": "chat", "retention_days": 4000},  # > 3650 (10 years)
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_admin_rbac_enforcement(test_client_regular, test_db_session):
    """Test that non-admin users are rejected."""
    response = test_client_regular.post(
        "/api/admin/retention-policies",
        json={"policy_type": "chat", "retention_days": 90},
    )

    # Should be rejected due to admin requirement
    assert response.status_code in [401, 403]  # Auth error


@pytest.mark.asyncio
async def test_filter_by_user_id(test_client_admin, test_db_session):
    """Test filtering policies by user_id."""
    user_id_1 = str(uuid.uuid4())
    user_id_2 = str(uuid.uuid4())

    # Create policies for different users
    test_client_admin.post(
        "/api/admin/retention-policies",
        json={"policy_type": "chat", "retention_days": 90},  # Global
    )
    test_client_admin.post(
        "/api/admin/retention-policies",
        json={"policy_type": "file", "retention_days": 60, "user_id": user_id_1},
    )
    test_client_admin.post(
        "/api/admin/retention-policies",
        json={"policy_type": "audit", "retention_days": 365, "user_id": user_id_2},
    )

    # Filter by user_id_1
    response = test_client_admin.get(f"/api/admin/retention-policies?user_id={user_id_1}")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["policies"][0]["user_id"] == user_id_1
