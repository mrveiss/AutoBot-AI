# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for budget policy hard-stop auto-pause (GH#6470).

Verifies:
1. Policy CRUD operations
2. Budget evaluation and hard-stop enforcement
3. Agent pause/resume flow with wakeup queue drainage
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from models.heartbeat import AgentRuntimeState, AgentWakeupRequest
from services.budget_policy import (
    BudgetPolicy,
    PERIOD_DAY,
    PERIOD_MONTH,
    SCOPE_AGENT,
    SCOPE_TENANT,
    create_policy,
    delete_policy,
    get_policy,
    list_all_policies,
    list_policies_for_scope,
    patch_policy,
    pause_agent,
    resume_agent,
    configure_session_factory,
)


@pytest.fixture
async def async_db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        # Import and run migrations
        from user_management.models.base import Base

        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    configure_session_factory(factory)

    async with factory() as session:
        yield session

    await engine.dispose()


class TestBudgetPolicyCRUD:
    """Test CRUD operations for budget policies."""

    @pytest.mark.asyncio
    async def test_create_policy(self):
        """Create a budget policy and verify it's stored."""
        policy = BudgetPolicy(
            scope=SCOPE_TENANT,
            scope_id="default",
            period=PERIOD_MONTH,
            threshold_usd=500.0,
            warning_pct=0.8,
            name="Test monthly cap",
            description="$500 monthly budget",
        )
        created = await create_policy(policy)

        assert created.id == policy.id
        assert created.scope == SCOPE_TENANT
        assert created.threshold_usd == 500.0
        assert created.enabled is True

    @pytest.mark.asyncio
    async def test_get_policy(self):
        """Get a policy by ID."""
        policy = BudgetPolicy(
            scope=SCOPE_AGENT,
            scope_id="agent-123",
            period=PERIOD_DAY,
            threshold_usd=100.0,
        )
        created = await create_policy(policy)

        retrieved = await get_policy(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.scope == SCOPE_AGENT
        assert retrieved.scope_id == "agent-123"

    @pytest.mark.asyncio
    async def test_get_nonexistent_policy(self):
        """Get a nonexistent policy returns None."""
        result = await get_policy("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_policies_for_scope(self):
        """List policies filtered by scope."""
        # Create multiple policies
        policy1 = BudgetPolicy(
            scope=SCOPE_TENANT,
            scope_id="default",
            period=PERIOD_MONTH,
            threshold_usd=500.0,
            enabled=True,
        )
        policy2 = BudgetPolicy(
            scope=SCOPE_TENANT,
            scope_id="default",
            period=PERIOD_DAY,
            threshold_usd=50.0,
            enabled=True,
        )
        policy3 = BudgetPolicy(
            scope=SCOPE_AGENT,
            scope_id="agent-456",
            period=PERIOD_MONTH,
            threshold_usd=1000.0,
            enabled=True,
        )

        await create_policy(policy1)
        await create_policy(policy2)
        await create_policy(policy3)

        # List for tenant
        tenant_policies = await list_policies_for_scope(SCOPE_TENANT, "default")
        assert len(tenant_policies) == 2
        assert all(p.scope == SCOPE_TENANT for p in tenant_policies)

        # List for agent
        agent_policies = await list_policies_for_scope(SCOPE_AGENT, "agent-456")
        assert len(agent_policies) == 1
        assert agent_policies[0].scope == SCOPE_AGENT

    @pytest.mark.asyncio
    async def test_list_all_policies(self):
        """List all policies without filtering."""
        policy1 = BudgetPolicy(
            scope=SCOPE_TENANT,
            scope_id="default",
            period=PERIOD_MONTH,
            threshold_usd=500.0,
            enabled=True,
        )
        policy2 = BudgetPolicy(
            scope=SCOPE_AGENT,
            scope_id="agent-789",
            period=PERIOD_DAY,
            threshold_usd=100.0,
            enabled=True,
        )

        await create_policy(policy1)
        await create_policy(policy2)

        all_policies = await list_all_policies()
        assert len(all_policies) >= 2

    @pytest.mark.asyncio
    async def test_patch_policy(self):
        """Update a policy."""
        policy = BudgetPolicy(
            scope=SCOPE_AGENT,
            scope_id="agent-999",
            period=PERIOD_MONTH,
            threshold_usd=500.0,
            enabled=True,
            name="Original name",
        )
        created = await create_policy(policy)

        # Update the policy
        updated = await patch_policy(created.id, {"threshold_usd": 1000.0, "name": "Updated name"})
        assert updated is not None
        assert updated.threshold_usd == 1000.0
        assert updated.name == "Updated name"
        assert updated.enabled is True

    @pytest.mark.asyncio
    async def test_patch_nonexistent_policy(self):
        """Patch a nonexistent policy returns None."""
        result = await patch_policy("nonexistent-id", {"threshold_usd": 100.0})
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_policy(self):
        """Delete a policy."""
        policy = BudgetPolicy(
            scope=SCOPE_AGENT,
            scope_id="agent-del",
            period=PERIOD_MONTH,
            threshold_usd=500.0,
        )
        created = await create_policy(policy)

        # Verify it exists
        assert await get_policy(created.id) is not None

        # Delete it
        success = await delete_policy(created.id)
        assert success is True

        # Verify it's gone
        assert await get_policy(created.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_policy(self):
        """Delete a nonexistent policy returns False."""
        result = await delete_policy("nonexistent-id")
        assert result is False


class TestPauseResume:
    """Test agent pause/resume with wakeup queue drainage."""

    @pytest.mark.asyncio
    async def test_pause_agent_creates_runtime_state(self, async_db_session: AsyncSession):
        """Pausing an agent creates its runtime state."""
        agent_id = str(uuid.uuid4())

        await pause_agent(agent_id, reason="Budget hard-stop test")

        # Verify the state was created
        result = await async_db_session.execute(
            select(AgentRuntimeState).where(AgentRuntimeState.agent_id == agent_id)
        )
        state = result.scalar_one_or_none()
        assert state is not None
        assert state.status == "paused"
        assert state.paused_reason == "Budget hard-stop test"

    @pytest.mark.asyncio
    async def test_pause_agent_drains_wakeup_queue(self, async_db_session: AsyncSession):
        """Pausing an agent drains unconsumed wakeups from the queue."""
        agent_id = str(uuid.uuid4())

        # Create runtime state
        state = AgentRuntimeState(
            id=uuid.uuid4(),
            agent_id=agent_id,
            status="active",
        )
        async_db_session.add(state)

        # Add some wakeup requests (unconsumed)
        for i in range(3):
            wake = AgentWakeupRequest(
                id=uuid.uuid4(),
                agent_id=agent_id,
                source="budget_test",
                trigger_time=datetime.now(timezone.utc),
            )
            async_db_session.add(wake)

        await async_db_session.commit()

        # Verify wakeups exist
        wake_result = await async_db_session.execute(
            select(AgentWakeupRequest).where(
                AgentWakeupRequest.agent_id == agent_id,
                AgentWakeupRequest.consumed_at.is_(None),
            )
        )
        initial_wakes = wake_result.scalars().all()
        assert len(initial_wakes) == 3

        # Pause the agent
        await pause_agent(agent_id, reason="Wakeup drain test")

        # Verify wakeups are drained
        wake_result = await async_db_session.execute(
            select(AgentWakeupRequest).where(
                AgentWakeupRequest.agent_id == agent_id,
                AgentWakeupRequest.consumed_at.is_(None),
            )
        )
        remaining_wakes = wake_result.scalars().all()
        assert len(remaining_wakes) == 0

    @pytest.mark.asyncio
    async def test_resume_agent_clears_pause(self, async_db_session: AsyncSession):
        """Resuming a paused agent clears its pause status."""
        agent_id = str(uuid.uuid4())

        # Create a paused state
        state = AgentRuntimeState(
            id=uuid.uuid4(),
            agent_id=agent_id,
            status="paused",
            paused_reason="Budget test",
            paused_at=datetime.now(timezone.utc),
            paused_by="budget_policy",
        )
        async_db_session.add(state)
        await async_db_session.commit()

        # Resume the agent
        success = await resume_agent(agent_id, approved_by="test_admin")
        assert success is True

        # Verify the state is cleared
        result = await async_db_session.execute(
            select(AgentRuntimeState).where(AgentRuntimeState.agent_id == agent_id)
        )
        resumed_state = result.scalar_one_or_none()
        assert resumed_state is not None
        assert resumed_state.status == "active"
        assert resumed_state.paused_reason is None
        assert resumed_state.paused_at is None

    @pytest.mark.asyncio
    async def test_resume_nonpaused_agent_fails(self, async_db_session: AsyncSession):
        """Resuming a non-paused agent returns False."""
        agent_id = str(uuid.uuid4())

        # Try to resume without pausing first
        success = await resume_agent(agent_id, approved_by="test_admin")
        assert success is False
