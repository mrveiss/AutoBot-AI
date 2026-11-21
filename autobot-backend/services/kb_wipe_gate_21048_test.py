# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""propose -> approve -> wipe, through the real approval gate (#21048, #17038).

Mirrors ``api/orphan_storage_approval_chain_test.py``: the real proposer hands its approval to the real
``ApprovalGateService.approve()`` and the real dispatcher routes it to the real executor. The fakes are the
database session, the list of platform admins, and the stores at the far end (``kb_wipe_scope_21048_test``).

The four-eyes rule as the gate enforces it (``services.approval_four_eyes``): the person who asked may approve
their own request only when they are the single active platform admin, and then the approval is flagged; with a
second admin it is refused. A decision with no verified decider is refused.
"""

import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.approval_four_eyes import FourEyesError
from autobot_shared.time_utils import now_utc
from llc.tests.test_ai_lines_api_18430 import factory  # noqa: F401 -- fixture
from models.approval import Approval, ApprovalComment, ApprovalStatus
from services import approval_execution, approval_four_eyes
from services import kb_wipe_action as action
from services import kb_wipe_request as request_mod
from services.approval_gate_service import ApprovalGateService
from services.approval_gate_service_test import _make_approval, _make_session
from services.kb_wipe_action_21048_test import PLAN
from services.kb_wipe_scope_21048_test import FOREIGN_INDEX, FOREIGN_KEY, kb_index, world  # noqa: F401 -- fixtures
from testkit.fake_approval_session import ApprovalClaimSession

pytestmark = pytest.mark.asyncio

ASKER = uuid.UUID("00000000-0000-4000-8000-0000000000b1")
OTHER_ADMIN = uuid.UUID("00000000-0000-4000-8000-0000000000b2")
KB_ONLY_INDEXES = {"llama_index": 12, FOREIGN_INDEX: 40}


async def _noop():
    return None


@pytest.fixture
def chain(monkeypatch, world):  # noqa: F811
    """The real executor, registered as importing the admin router registers it, over the fake stores."""
    monkeypatch.setattr(approval_execution, "_REGISTRY", {})
    monkeypatch.setattr(approval_execution, "_PROPOSERS", {})
    monkeypatch.setattr(ApprovalGateService, "_notify", lambda self, event, approval: _noop())
    monkeypatch.setattr(approval_execution, "audit_log", AsyncMock(return_value=True))

    async def plan():
        return await action.plan_kb_wipe(world.factory)

    monkeypatch.setattr(request_mod, "plan_kb_wipe", plan)
    action.register_kb_wipe_action()
    return world


def _admins(monkeypatch, *ids):
    monkeypatch.setattr(approval_four_eyes, "_platform_admin_ids", AsyncMock(return_value=set(ids)))


async def _propose(session, chain) -> uuid.UUID:
    proposal = await request_mod.request_kb_wipe({"id": str(ASKER), "role": "admin"}, session)
    chain.log.clear()  # planning read the stores; what follows is the decision
    return uuid.UUID(proposal["approval_id"])


async def _approve(session, approval_id, decider):
    return await ApprovalGateService(session).approve(
        approval_id, decided_by="alice", author_type="human", comment=None, decider_id=decider
    )


def _untouched(chain) -> None:
    assert chain.log == [] and chain.redis.indexes == KB_ONLY_INDEXES and FOREIGN_KEY in chain.redis.data


async def test_proposing_then_approving_by_another_admin_wipes_behind_the_paper_trail(chain, monkeypatch):
    _admins(monkeypatch, ASKER, OTHER_ADMIN)
    session = ApprovalClaimSession()
    approval_id = await _propose(session, chain)
    _untouched(chain)  # a proposal deletes nothing

    await _approve(session, approval_id, OTHER_ADMIN)

    assert session.approval.status == "approved"
    assert chain.log[0] == ("audit", "attempted") and chain.log[-1] == ("audit", "success")
    intent = chain.audit.await_args_list[0].kwargs["details"]
    assert intent["approval_id"] == str(approval_id) and intent["proposed_by"] == f"kb-wipe:{ASKER}"
    assert intent["approver_id"] == str(OTHER_ADMIN) and intent["self_approval"] is False
    assert chain.redis.indexes == {FOREIGN_INDEX: 40}  # the KB index went, the foreign one did not
    assert any("Knowledge wipe done" in o.body for o in session.added if isinstance(o, ApprovalComment))


async def test_rejecting_the_proposal_deletes_nothing(chain, monkeypatch):
    _admins(monkeypatch, ASKER, OTHER_ADMIN)
    session = ApprovalClaimSession()
    approval_id = await _propose(session, chain)

    await ApprovalGateService(session).reject(approval_id, decided_by="alice", author_type="human", comment=None)

    assert session.approval.status == "rejected"
    _untouched(chain)


async def test_self_approval_is_refused_when_a_second_admin_exists(chain, monkeypatch):
    _admins(monkeypatch, ASKER, OTHER_ADMIN)
    session = ApprovalClaimSession()
    approval_id = await _propose(session, chain)

    with pytest.raises(FourEyesError):
        await _approve(session, approval_id, ASKER)

    assert session.approval.status == "pending"  # still waiting for someone who may decide it
    _untouched(chain)


async def test_the_only_admin_may_approve_their_own_request_and_the_wipe_is_flagged(chain, monkeypatch):
    _admins(monkeypatch, ASKER)
    session = ApprovalClaimSession()
    approval_id = await _propose(session, chain)

    await _approve(session, approval_id, ASKER)

    assert session.approval.status == "approved" and chain.redis.indexes == {FOREIGN_INDEX: 40}
    assert chain.audit.await_args_list[0].kwargs["details"]["self_approval"] is True
    bodies = [o.body for o in session.added if isinstance(o, ApprovalComment)]
    assert any(b.endswith("(self-approved by the only admin).") for b in bodies)


async def test_a_decision_without_a_verified_decider_is_refused(chain, monkeypatch):
    _admins(monkeypatch, ASKER)
    session = ApprovalClaimSession()
    approval_id = await _propose(session, chain)

    with pytest.raises(ValueError, match="verified decider"):
        await _approve(session, approval_id, None)  # a service or run credential carries no user id

    assert session.approval.status == "pending"
    _untouched(chain)


async def test_a_consumed_approval_cannot_be_approved_again(factory, monkeypatch):  # noqa: F811
    """The claim is one conditional UPDATE: a second approve finds the row already decided and runs nothing."""
    action.register_kb_wipe_action()
    wipe, audit = AsyncMock(), AsyncMock(return_value=True)
    monkeypatch.setattr(action, "_wipe", wipe)
    monkeypatch.setattr(action, "audit_log", audit)
    context = {"action": action.ACTION, "plan": PLAN}
    async with factory() as session:
        row = Approval(
            title="x", approval_type="destructive_action", status=ApprovalStatus.APPROVED.value, context=context
        )
        session.add(row)
        await session.commit()
        approval_id = row.id

    async with factory() as session:
        with pytest.raises(ValueError, match="Cannot transition from approved to approved"):
            await _approve(session, approval_id, uuid.uuid4())

    wipe.assert_not_awaited()
    audit.assert_not_awaited()


async def test_an_expired_approval_cannot_be_approved(monkeypatch):
    """A mocked session: SQLite hands back a naive ``expires_at``, which cannot be compared with the aware clock."""
    action.register_kb_wipe_action()
    wipe = AsyncMock()
    monkeypatch.setattr(action, "_wipe", wipe)
    approval = _make_approval()
    approval.context = {"action": action.ACTION, "plan": PLAN}
    approval.expires_at = now_utc() - timedelta(minutes=1)

    with patch("events.bus.publish_event", AsyncMock()):
        with pytest.raises(ValueError, match="expired"):
            await _approve(_make_session(scalar_result=approval), approval.id, uuid.uuid4())

    wipe.assert_not_awaited()
