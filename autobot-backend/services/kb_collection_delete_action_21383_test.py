# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The two collection delete routes only propose; approval deletes exactly the scoped set (#21383, #17038).

Fakes only: no real Redis, knowledge base or database is touched.
"""

import os
import subprocess
import sys
import types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api import knowledge_collections as routes
from services import kb_collection_delete_action as action
from services import kb_collection_delete_request as request
from services.approval_execution import (
    _ADMIN_ONLY,
    _REGISTRY,
    _SERVER_ONLY,
    set_verified_decider,
)

_BACKEND = Path(__file__).resolve().parents[1]
ADMIN = {"id": str(uuid.uuid4()), "role": "admin"}


class FakeKB:
    """Collections of fact ids. ``mutations`` records every delete, in order; reads are not recorded."""

    def __init__(self, events: list):
        self.collections = {"c1": {"f1", "f2", "f3"}, "c2": {"g1"}}
        self.created = {"c1": "t1", "c2": "t2"}
        self.facts = {"f1", "f2", "f3", "g1", "loose"}
        self.mutations: list = []
        self.events = events

    async def get_collection(self, collection_id):
        if collection_id not in self.collections:
            return {"success": False, "code": "not_found", "message": f"Collection not found: {collection_id}"}
        return {
            "success": True,
            "collection": {"name": f"Name {collection_id}", "created_at": self.created[collection_id]},
        }

    async def bulk_delete_collection_facts(self, collection_id, confirm=False, approved=None):
        if collection_id not in self.collections:
            return {
                "success": False,
                "message": f"Collection not found: {collection_id}",
            }
        ids = self.collections[collection_id]
        if not confirm:
            return {
                "success": True,
                "facts_to_delete": len(ids),
                "confirm_required": True,
            }
        if approved and (self.created[collection_id] != approved["created_at"] or len(ids) > approved["facts"]):
            return {"success": False, "message": "not the approved collection; nothing deleted"}
        self.mutations.append(("bulk", collection_id))
        self.events.append("delete")
        deleted = len(ids)
        self.facts -= ids
        self.collections[collection_id] = set()
        return {
            "success": True,
            "collection_id": collection_id,
            "deleted_count": deleted,
        }

    async def delete_collection(self, collection_id, delete_facts=False, approved=None):
        if collection_id not in self.collections:
            return {
                "success": False,
                "message": f"Collection not found: {collection_id}",
            }
        too_many = delete_facts and approved and len(self.collections[collection_id]) > approved["facts"]
        if approved and (self.created[collection_id] != approved["created_at"] or too_many):
            return {"success": False, "message": "not the approved collection; nothing deleted"}
        self.mutations.append(("delete", collection_id, delete_facts))
        self.events.append("delete")
        ids = self.collections.pop(collection_id)
        if delete_facts:
            self.facts -= ids
        return {
            "success": True,
            "facts_in_collection": len(ids),
            "facts_deleted": len(ids) if delete_facts else 0,
        }


@pytest.fixture
def world(monkeypatch):
    events: list = []
    kb = FakeKB(events)
    audit = AsyncMock(side_effect=lambda *a, **k: (events.append(f"audit:{k['details'].get('phase')}") or True))
    created: dict = {}

    class Gate:
        def __init__(self, session):
            pass

        async def create_approval(self, **kwargs):
            created.update(kwargs)
            return types.SimpleNamespace(id=uuid.uuid4(), status="pending")

    monkeypatch.setattr("services.approval_gate_service.ApprovalGateService", Gate)
    monkeypatch.setattr(action, "_pending_proposal", AsyncMock(return_value=None))
    monkeypatch.setattr(action, "audit_log", audit)
    monkeypatch.setattr(action, "_kb", AsyncMock(return_value=kb))
    monkeypatch.setattr(action, "review_kb_proposal", AsyncMock(return_value=False))
    monkeypatch.setattr(routes, "get_or_create_knowledge_base", AsyncMock(return_value=kb))
    return types.SimpleNamespace(kb=kb, audit=audit, created=created, events=events)


def _session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


def _req():
    return types.SimpleNamespace(app=object())


def _approval(op, selector, facts, status="approved", created_at="t1"):
    approval = types.SimpleNamespace(
        id=uuid.uuid4(),
        status=status,
        decided_by_user="alice",
        decided_at=datetime(2026, 11, 19, 9, 0, tzinfo=timezone.utc),
        requested_by_agent="kb-collection-delete:operator",
        context={
            "action": op.action,
            "channel": "api",
            "plan": {"selector": selector, "facts": facts},
        },
    )
    set_verified_decider(approval, uuid.uuid4())
    return approval


async def _run(op, approval):
    await action.execute(op, approval, _session())


# -- the routes only propose -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_route_files_a_proposal_and_deletes_nothing(world):
    reply = await routes.delete_collection("c1", True, _req(), ADMIN, _session())
    assert reply["status"] == "pending_approval" and reply["approval_id"] and reply["facts_in_collection"] == 3
    assert (
        world.kb.mutations == []
        and world.kb.facts == {"f1", "f2", "f3", "g1", "loose"}
        and "c1" in world.kb.collections
    )
    assert (
        world.created["approval_type"] == "destructive_action"
        and world.created["context"]["action"] == "kb_collection_delete"
    )
    plan = world.created["context"]["plan"]
    assert (
        plan["selector"] == action.selector_for(action.DELETE, "c1", True)
        and "ids" not in plan
        and "fact_ids" not in plan
    )


@pytest.mark.asyncio
async def test_bulk_delete_route_files_a_proposal_and_deletes_nothing(world):
    reply = await routes.bulk_delete_collection_facts("c1", True, _req(), ADMIN, _session())
    assert reply["status"] == "pending_approval" and reply["action"] == "kb_collection_bulk_delete"
    assert world.kb.mutations == [] and world.kb.collections["c1"] == {"f1", "f2", "f3"}
    assert world.created["context"]["plan"] == {
        "selector": action.selector_for(action.BULK_DELETE, "c1"),
        "facts": 3,
    }


@pytest.mark.asyncio
async def test_bulk_delete_without_confirm_is_a_preview_and_files_nothing(world):
    reply = await routes.bulk_delete_collection_facts("c1", False, _req(), ADMIN, _session())
    assert reply["status"] == "preview" and reply["facts_in_collection"] == 3 and reply["confirm_required"] is True
    assert world.kb.mutations == [] and world.created == {}


@pytest.mark.asyncio
async def test_an_unknown_collection_is_a_404_and_files_nothing(world):
    with pytest.raises(HTTPException) as refused:
        await routes.delete_collection("nope", False, _req(), ADMIN, _session())
    assert refused.value.status_code == 404 and world.created == {} and world.kb.mutations == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "caller",
    [
        {"id": str(uuid.uuid4()), "role": "user"},
        {"id": "svc-key", "role": "admin"},
        {"role": "admin"},
    ],
)
async def test_a_caller_that_is_not_an_admin_user_files_nothing(world, caller):
    with pytest.raises(HTTPException) as refused:
        await request.request_collection_bulk_delete(world.kb, caller, _session(), "c1")
    assert refused.value.status_code == 403 and world.created == {} and world.kb.mutations == []


# -- approval deletes exactly the scoped set --------------------------------------------------------------


@pytest.mark.asyncio
async def test_approved_collection_delete_with_facts_removes_only_that_collection_and_its_facts(
    world,
):
    await _run(
        action.DELETE,
        _approval(action.DELETE, action.selector_for(action.DELETE, "c1", True), 3),
    )
    assert world.kb.mutations == [("delete", "c1", True)]
    assert world.kb.facts == {"g1", "loose"} and "c2" in world.kb.collections and "c1" not in world.kb.collections


@pytest.mark.asyncio
async def test_approved_collection_delete_without_facts_keeps_the_facts(world):
    await _run(
        action.DELETE,
        _approval(action.DELETE, action.selector_for(action.DELETE, "c1", False), 3),
    )
    assert world.kb.mutations == [("delete", "c1", False)] and {"f1", "f2", "f3"} <= world.kb.facts


@pytest.mark.asyncio
async def test_approved_bulk_delete_removes_exactly_the_collections_facts(world):
    await _run(
        action.BULK_DELETE,
        _approval(action.BULK_DELETE, action.selector_for(action.BULK_DELETE, "c1"), 3),
    )
    assert world.kb.mutations == [("bulk", "c1")] and world.kb.facts == {"g1", "loose"}
    assert world.kb.collections == {"c1": set(), "c2": {"g1"}}


# -- the audit is durable, intent first ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_audit_is_durable_and_the_intent_entry_precedes_the_delete(world):
    await _run(
        action.BULK_DELETE,
        _approval(action.BULK_DELETE, action.selector_for(action.BULK_DELETE, "c1"), 3),
    )
    assert world.events == ["audit:intent", "delete", "audit:completion"]
    assert all(call.kwargs["durable"] is True for call in world.audit.await_args_list)
    assert world.audit.await_args_list[0].kwargs["details"]["selector"]["collection_id"] == "c1"


@pytest.mark.asyncio
async def test_no_committed_intent_entry_means_nothing_is_deleted(world):
    world.audit.side_effect = None
    world.audit.return_value = False
    with pytest.raises(RuntimeError, match="nothing was deleted"):
        await _run(
            action.DELETE,
            _approval(action.DELETE, action.selector_for(action.DELETE, "c1", True), 3),
        )
    assert world.kb.mutations == []


@pytest.mark.asyncio
async def test_a_failed_delete_is_audited_as_failed(world, monkeypatch):
    monkeypatch.setattr(
        world.kb,
        "delete_collection",
        AsyncMock(return_value={"success": False, "message": "boom"}),
    )
    with pytest.raises(RuntimeError, match="refused the deletion"):
        await _run(
            action.DELETE,
            _approval(action.DELETE, action.selector_for(action.DELETE, "c1", True), 3),
        )
    last = world.audit.await_args.kwargs
    assert last["result"] == "failed" and last["details"]["phase"] == "failure"


# -- the executor does not trust the proposal's numbers or scope --------------------------------------------


@pytest.mark.asyncio
async def test_more_facts_than_approved_is_refused_audited_and_deletes_nothing(world):
    approval = _approval(action.BULK_DELETE, action.selector_for(action.BULK_DELETE, "c1"), 2)
    with pytest.raises(ValueError, match="nothing was deleted"):
        await _run(action.BULK_DELETE, approval)
    refusal = world.audit.await_args.kwargs
    assert world.kb.mutations == [] and refusal["details"]["phase"] == "refused"
    assert refusal["details"]["approved"] == 2 and refusal["details"]["found"] == 3


@pytest.mark.asyncio
async def test_fewer_facts_than_approved_still_deletes(world):
    await _run(
        action.BULK_DELETE,
        _approval(action.BULK_DELETE, action.selector_for(action.BULK_DELETE, "c2"), 9),
    )
    assert world.kb.mutations == [("bulk", "c2")]


@pytest.mark.asyncio
async def test_a_pending_or_other_action_approval_is_refused(world):
    selector = action.selector_for(action.DELETE, "c1", True)
    with pytest.raises(ValueError, match="refused"):
        await _run(action.DELETE, _approval(action.DELETE, selector, 3, status="pending"))
    with pytest.raises(ValueError, match="refused"):
        await _run(action.BULK_DELETE, _approval(action.DELETE, selector, 3))
    assert world.kb.mutations == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selector",
    [
        {
            "operation": "delete_collection",
            "collection_id": "c1",
            "delete_facts": True,
            "fact_ids": ["g1"],
        },
        {
            "operation": "delete_collection",
            "collection_id": "../c1",
            "delete_facts": True,
        },
        {
            "operation": "bulk_delete_collection_facts",
            "collection_id": "c1",
            "delete_facts": True,
        },
        {"operation": "delete_collection", "collection_id": "c1"},
        {"operation": "flushdb", "collection_id": "c1"},
    ],
)
async def test_a_selector_the_code_does_not_build_is_refused(world, selector):
    with pytest.raises(ValueError, match="different selector"):
        await _run(action.DELETE, _approval(action.DELETE, selector, 3))
    assert world.kb.mutations == []


# -- the count check applies only where facts go; identity; the display name -------------------------------


@pytest.mark.asyncio
async def test_a_collection_delete_without_facts_ignores_the_fact_count(world):
    selector = action.selector_for(action.DELETE, "c1", False)
    await _run(action.DELETE, _approval(action.DELETE, selector, 0))  # 3 facts now, 0 approved: none are deleted
    assert world.kb.mutations == [("delete", "c1", False)] and {"f1", "f2", "f3"} <= world.kb.facts


@pytest.mark.asyncio
async def test_a_collection_delete_with_facts_still_refuses_a_higher_count(world):
    with pytest.raises(ValueError, match="nothing was deleted"):
        await _run(action.DELETE, _approval(action.DELETE, action.selector_for(action.DELETE, "c1", True), 2))
    assert world.kb.mutations == []


@pytest.mark.asyncio
@pytest.mark.parametrize("op", action.OPS)
async def test_a_collection_recreated_under_the_same_id_is_refused(world, op):
    approval = _approval(op, action.selector_for(op, "c1", True), 3)
    world.kb.created["c1"] = "t-later"  # deleted and re-created after the approval
    with pytest.raises(ValueError, match="changed since it was approved"):
        await _run(op, approval)
    refusal = world.audit.await_args.kwargs["details"]
    assert world.kb.mutations == [] and refusal["phase"] == "refused" and refusal["found_created_at"] == "t-later"


@pytest.mark.asyncio
async def test_a_plan_without_the_identity_marker_is_refused(world):
    approval = _approval(action.BULK_DELETE, action.selector_for(action.BULK_DELETE, "c1"), 3, created_at=None)
    with pytest.raises(ValueError, match="changed since it was approved"):
        await _run(action.BULK_DELETE, approval)
    assert world.kb.mutations == []


@pytest.mark.asyncio
async def test_the_name_is_display_only_and_never_part_of_the_scope(world):
    reply = await routes.delete_collection("c1", False, _req(), ADMIN, _session())
    plan = world.created["context"]["plan"]
    assert plan["name"] == "Name c1" and "name" not in plan["selector"] and reply["facts_in_collection"] == 3
    approval = _approval(action.DELETE, action.selector_for(action.DELETE, "c1", False), 3)
    approval.context["plan"]["name"] = "Another name"  # a different display name changes nothing
    await _run(action.DELETE, approval)
    assert world.kb.mutations == [("delete", "c1", False)]


# -- the count is bound to the snapshot that is deleted; a store failure is not "not found" ------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("op", action.OPS)
async def test_a_fact_added_after_the_count_check_is_not_deleted_with_the_approved_ones(world, op):
    approval = _approval(op, action.selector_for(op, "c1", True), 3)
    real = world.audit.side_effect

    def grow_during_the_intent_audit(*args, **kwargs):
        if kwargs["details"].get("phase") == "intent":
            world.kb.collections["c1"].add("f4")  # a member joins after the count check, before the delete
        return real(*args, **kwargs)

    world.audit.side_effect = grow_during_the_intent_audit
    with pytest.raises(RuntimeError, match="refused the deletion"):
        await _run(op, approval)
    assert world.kb.mutations == [] and "f4" in world.kb.collections["c1"]
    assert world.audit.await_args.kwargs["result"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("op", action.OPS)
async def test_a_collection_recreated_during_the_intent_audit_is_not_deleted(world, op):
    approval = _approval(op, action.selector_for(op, "c1", True), 3)
    real = world.audit.side_effect

    def recreate_during_the_intent_audit(*args, **kwargs):
        if kwargs["details"].get("phase") == "intent":
            world.kb.created["c1"] = "t-later"  # the same id, a new collection, after the identity check
        return real(*args, **kwargs)

    world.audit.side_effect = recreate_during_the_intent_audit
    with pytest.raises(RuntimeError, match="refused the deletion"):
        await _run(op, approval)
    assert world.kb.mutations == [] and world.kb.collections["c1"] == {"f1", "f2", "f3"}


@pytest.mark.asyncio
async def test_a_store_failure_is_raised_and_only_a_missing_collection_is_none(world, monkeypatch):
    unavailable = AsyncMock(return_value={"success": False, "message": "Redis not available"})
    monkeypatch.setattr(world.kb, "get_collection", unavailable)
    with pytest.raises(RuntimeError, match="could not read the collection"):
        await action.collection_state(world.kb, "c1")
    with pytest.raises(Exception):
        await routes.delete_collection("c1", False, _req(), ADMIN, _session())
    assert world.created == {}
    assert await action.collection_state(FakeKB([]), "nope") is None


@pytest.mark.asyncio
async def test_an_error_whose_text_merely_says_not_found_still_raises(world, monkeypatch):
    lookalike = AsyncMock(return_value={"success": False, "message": "Redis host not found: the store is down"})
    monkeypatch.setattr(world.kb, "get_collection", lookalike)
    with pytest.raises(RuntimeError, match="could not read the collection"):
        await action.collection_state(world.kb, "c1")


# -- registration -------------------------------------------------------------------------------------------


def test_registration_is_server_only_admin_only_for_both_actions():
    action.register_collection_delete_actions()
    for op in action.OPS:
        assert op.action in _REGISTRY and op.action in _SERVER_ONLY and op.action in _ADMIN_ONLY


def test_importing_the_approvals_router_registers_both_handlers_in_a_fresh_interpreter():
    names = [op.action for op in action.OPS]
    code = (
        "import api.approval_gates, services.approval_execution as e; "
        f"print(all(n in e._REGISTRY and n in e._SERVER_ONLY and n in e._ADMIN_ONLY for n in {names!r}))"
    )
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(_BACKEND), str(_BACKEND.parent)]),
    }
    done = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        cwd=_BACKEND,
        env=env,
    )
    assert done.returncode == 0 and done.stdout.strip().endswith("True"), done.stderr[-800:]
