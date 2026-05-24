"""Tests for LLC WorkItemRelationService (GH#8252)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa

from llc.models.enums import WorkItemRelationType, WorkItemStatus
from llc.models.work_item import LLCWorkItem, LLCWorkItemRelation
from llc.services.work_item_relations import RelationConflict, WorkItemRelationService
from llc.services.work_item_service import InvalidTransition, WorkItemService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item(status: WorkItemStatus = WorkItemStatus.READY) -> MagicMock:
    item = MagicMock(spec=LLCWorkItem)
    item.id = uuid.uuid4()
    item.company_id = uuid.uuid4()
    item.identifier = f"WI-{uuid.uuid4().hex[:4]}"
    item.title = "Test"
    item.status = status
    item.outgoing_relations = []
    item.incoming_relations = []
    return item


def _rel(
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    relation_type: WorkItemRelationType,
    company_id: uuid.UUID | None = None,
) -> LLCWorkItemRelation:
    rel = MagicMock(spec=LLCWorkItemRelation)
    rel.id = uuid.uuid4()
    rel.company_id = company_id or uuid.uuid4()
    rel.source_id = source_id
    rel.target_id = target_id
    rel.relation_type = relation_type.value
    return rel


@pytest.fixture
def svc():
    return WorkItemRelationService()


# ---------------------------------------------------------------------------
# add() — mirror creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_blocks_creates_mirror(svc):
    session = AsyncMock()
    cid = str(uuid.uuid4())
    src = str(uuid.uuid4())
    tgt = str(uuid.uuid4())

    async def _execute(stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        r.scalars.return_value.all.return_value = []
        return r

    session.execute = _execute
    session.add = MagicMock()
    session.flush = AsyncMock()

    await svc.add(
        session,
        company_id=cid,
        source_id=src,
        target_id=tgt,
        relation_type=WorkItemRelationType.BLOCKS,
    )

    session.flush.assert_awaited_once()
    assert session.add.call_count == 2
    added_types = {call.args[0].relation_type for call in session.add.call_args_list}
    assert WorkItemRelationType.BLOCKS in added_types
    assert WorkItemRelationType.BLOCKED_BY in added_types


@pytest.mark.asyncio
async def test_add_relates_to_no_mirror(svc):
    session = AsyncMock()
    cid = str(uuid.uuid4())

    async def _execute(stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        return r

    session.execute = _execute
    session.add = MagicMock()
    session.flush = AsyncMock()

    await svc.add(
        session,
        company_id=cid,
        source_id=str(uuid.uuid4()),
        target_id=str(uuid.uuid4()),
        relation_type=WorkItemRelationType.RELATES_TO,
    )

    assert session.add.call_count == 1


@pytest.mark.asyncio
async def test_add_self_loop_raises(svc):
    session = AsyncMock()
    item_id = str(uuid.uuid4())
    with pytest.raises(RelationConflict, match="must differ"):
        await svc.add(
            session,
            company_id=str(uuid.uuid4()),
            source_id=item_id,
            target_id=item_id,
            relation_type=WorkItemRelationType.RELATES_TO,
        )


@pytest.mark.asyncio
async def test_add_duplicate_raises(svc):
    session = AsyncMock()
    existing = MagicMock(spec=LLCWorkItemRelation)

    async def _execute(stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = existing
        return r

    session.execute = _execute

    with pytest.raises(RelationConflict, match="already exists"):
        await svc.add(
            session,
            company_id=str(uuid.uuid4()),
            source_id=str(uuid.uuid4()),
            target_id=str(uuid.uuid4()),
            relation_type=WorkItemRelationType.RELATES_TO,
        )


# ---------------------------------------------------------------------------
# remove() — mirror deletion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_blocks_deletes_mirror(svc):
    session = AsyncMock()
    cid = uuid.uuid4()
    src = uuid.uuid4()
    tgt = uuid.uuid4()
    rel = _rel(src, tgt, WorkItemRelationType.BLOCKS, cid)
    mirror = _rel(tgt, src, WorkItemRelationType.BLOCKED_BY, cid)

    call_count = 0

    async def _execute(stmt):
        nonlocal call_count
        r = MagicMock()
        if call_count == 0:
            r.scalar_one_or_none.return_value = rel
        else:
            r.scalar_one_or_none.return_value = mirror
        call_count += 1
        return r

    session.execute = _execute
    session.delete = AsyncMock()
    session.flush = AsyncMock()

    await svc.remove(session, company_id=str(cid), relation_id=str(rel.id))

    assert session.delete.await_count == 2


@pytest.mark.asyncio
async def test_remove_not_found_raises(svc):
    session = AsyncMock()

    async def _execute(stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        return r

    session.execute = _execute

    with pytest.raises(ValueError, match="not found"):
        await svc.remove(session, company_id=str(uuid.uuid4()), relation_id=str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# has_unresolved_blockers()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_has_unresolved_blockers_true(svc):
    session = AsyncMock()
    blocker_rel = MagicMock()

    async def _execute(stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = blocker_rel
        return r

    session.execute = _execute
    result = await svc.has_unresolved_blockers(
        session, work_item_id=str(uuid.uuid4()), company_id=str(uuid.uuid4())
    )
    assert result is True


@pytest.mark.asyncio
async def test_has_unresolved_blockers_false_when_done(svc):
    session = AsyncMock()

    async def _execute(stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        return r

    session.execute = _execute
    result = await svc.has_unresolved_blockers(
        session, work_item_id=str(uuid.uuid4()), company_id=str(uuid.uuid4())
    )
    assert result is False


# ---------------------------------------------------------------------------
# WorkItemService.transition_status — blocked→in_progress guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transition_blocked_to_in_progress_with_active_blocker_raises():
    """BLOCKED → IN_PROGRESS must fail when unresolved blockers exist."""
    svc = WorkItemService()

    item = MagicMock(spec=LLCWorkItem)
    item.id = uuid.uuid4()
    item.status = WorkItemStatus.BLOCKED.value
    item.started_at = None
    item.version = 1

    session = AsyncMock()

    async def _execute(stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = item
        return r

    session.execute = _execute
    session.flush = AsyncMock()

    relation_svc = AsyncMock(spec=WorkItemRelationService)
    relation_svc.has_unresolved_blockers = AsyncMock(return_value=True)

    with pytest.raises(InvalidTransition, match="unresolved blocked_by"):
        await svc.transition_status(
            session,
            str(item.id),
            WorkItemStatus.IN_PROGRESS,
            company_id=str(uuid.uuid4()),
            relation_svc=relation_svc,
        )


@pytest.mark.asyncio
async def test_transition_blocked_to_in_progress_when_blockers_resolved():
    """BLOCKED → IN_PROGRESS must succeed when all blockers are done/cancelled."""
    svc = WorkItemService()

    item = MagicMock(spec=LLCWorkItem)
    item.id = uuid.uuid4()
    item.status = WorkItemStatus.BLOCKED.value
    item.started_at = None
    item.version = 1

    session = AsyncMock()

    async def _execute(stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = item
        return r

    session.execute = _execute
    session.flush = AsyncMock()

    relation_svc = AsyncMock(spec=WorkItemRelationService)
    relation_svc.has_unresolved_blockers = AsyncMock(return_value=False)

    result = await svc.transition_status(
        session,
        str(item.id),
        WorkItemStatus.IN_PROGRESS,
        company_id=str(uuid.uuid4()),
        relation_svc=relation_svc,
    )
    assert result is item
