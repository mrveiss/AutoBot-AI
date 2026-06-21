# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""GH#10032 — dual agent-identifier keyspace guards.

``AgentOrgNode`` is identified two ways (see the model docstring):
  * ``id``       — UUID PK; what ``llc_work_items.assignee_agent_id`` stores.
  * ``agent_id`` — String slug; the keyspace for heartbeat runs / budgets /
                   scheduler dispatch / controls pause-resume.

A lookup that resolves a work-item assignee (PK) but joins/filters against the
slug column compiles fine and returns zero rows in Postgres — and is invisible
in tests that seed ``agent_id = str(uuid4())`` (both keyspaces collide).

These tests seed a NON-UUID slug DISTINCT from the PK so a wrong-column join
fails loudly.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import WorkItemPriority, WorkItemType
from llc.models.work_item import LLCWorkItem, LLCWorkItemComment

# Importing the harness registers the SQLite compile shims before any model code.
from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode, OrgRole

_COMPANY = uuid.uuid4()
_SPRINT = uuid.uuid4()


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):  # noqa: ANN001, ANN201
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_node_and_item(
    session_factory,  # noqa: ANN001
    *,
    adapter_type: str = "claude_code",
    heartbeat_enabled: bool = True,
    status: str = "in_progress",
) -> tuple[uuid.UUID, str, uuid.UUID]:
    """Seed one node (slug ≠ PK) + one work item assigned to it by PK."""
    node_pk = uuid.uuid4()
    slug = f"assistant-test-{node_pk.hex[:8]}"  # non-UUID, distinct from the PK
    item_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            AgentOrgNode(
                id=node_pk,
                agent_id=slug,
                name="Bot",
                org_role=OrgRole.WORKER.value,
                company_id=_COMPANY,
                adapter_type=adapter_type,
                heartbeat_enabled=heartbeat_enabled,
            )
        )
        session.add(
            LLCWorkItem(
                id=item_id,
                company_id=_COMPANY,
                sprint_id=_SPRINT,
                identifier=f"WI-{item_id.hex[:6]}",
                type=WorkItemType.TASK.value,
                title="Task",
                status=status,
                priority=WorkItemPriority.MEDIUM.value,
                version=1,
                labels=[],
                assignee_agent_id=node_pk,
            )
        )
        await session.commit()
    return node_pk, slug, item_id


@pytest.mark.asyncio
async def test_agents_in_sprint_resolves_pk_to_slug(session_factory):
    """controls._agents_in_sprint must return the agent_id slug (what
    pause_agent keys on), resolved from the work item's assignee PK."""
    from llc.services.controls_service import ControlsService

    node_pk, slug, _ = await _seed_node_and_item(session_factory)
    async with session_factory() as session:
        # SQLite stores UUIDs as 32-char hex; pass that form so the company/sprint
        # filters match (Postgres accepts both forms). The JOIN under test —
        # AgentOrgNode.id == assignee_agent_id — is the #10032 fix.
        agents = await ControlsService()._agents_in_sprint(session, _COMPANY.hex, _SPRINT.hex)

    assert agents == [slug]  # the slug, NOT the PK
    assert str(node_pk) not in agents


@pytest.mark.asyncio
async def test_comment_wake_resolves_assignee_pk_to_slug_keyspace(session_factory):
    """trigger_comment_wake must look the node up by PK and key the created
    heartbeat run by the agent_id slug (the scheduler-dispatch keyspace)."""
    from sqlalchemy import select

    from llc.models.heartbeat_run import LLCHeartbeatRun
    from llc.services.comment_wake_service import CommentWakeService

    node_pk, slug, item_id = await _seed_node_and_item(session_factory)
    comment_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(LLCWorkItemComment(id=comment_id, company_id=_COMPANY, work_item_id=item_id, body="ping"))
        await session.commit()

    async with session_factory() as session:
        result = await CommentWakeService().trigger_comment_wake(session, str(item_id), str(comment_id))
        await session.commit()
        # Wrong-column lookup (pre-#10032) would 'agent not found' → None.
        assert result is not None
        run_pk = result[0]  # (run_id, agent_config, context)
        assert result[1]["agent_id"] == slug  # dispatch config keyed by the slug
        run = (await session.execute(select(LLCHeartbeatRun).where(LLCHeartbeatRun.id == run_pk))).scalar_one()

    assert run.agent_id == slug  # heartbeat run keyed by the slug, not the UUID PK
    assert run.agent_id != str(node_pk)
