# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The CLAUDE.md chunk deletion is a proposal; approval deletes exactly the selector's chunks (#21383, #17038).

Fakes only: no real Redis or database is touched.
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

from services import claude_md_reindex_action as action
from services.approval_execution import _ADMIN_ONLY, _REGISTRY, _SERVER_ONLY, set_verified_decider

_BACKEND = Path(__file__).resolve().parents[1]
OTHER_TITLE = "Some other document"
INDEX = "llama_index"


class FakeRedis:
    """Hashes by key. A key whose value is a string answers ``hget`` with a WRONGTYPE error, as Redis does."""

    def __init__(self, data: dict):
        self.data, self.unlinked = dict(data), []

    def scan_iter(self, match, count=None):
        prefix = match.rstrip("*")
        return iter([k for k in list(self.data) if k.startswith(prefix)])

    def hget(self, key, field):
        value = self.data[key]
        if not isinstance(value, dict):
            raise action.ResponseError("WRONGTYPE")
        return value.get(field)

    def unlink(self, *keys):
        self.unlinked.extend(keys)
        for key in keys:
            self.data.pop(key, None)


def _chunks() -> dict:
    mine = {f"doc:claude-{i}": {"title": action.SELECTOR_VALUE, "source": action.SOURCE_VALUE} for i in range(3)}
    return {
        **mine,
        "doc:same-title-other-source": {"title": action.SELECTOR_VALUE, "source": "a_user_upload"},
        "doc:same-title-no-source": {"title": action.SELECTOR_VALUE},
        "doc:other-1": {"title": OTHER_TITLE},
        "doc:untitled": {"text": "x"},
        "doc:version:abc": "7",
        "fact:1": {"title": action.SELECTOR_VALUE},  # the right title outside the chunk prefix: out of scope
    }


@pytest.fixture
def world(monkeypatch):
    redis = FakeRedis(_chunks())
    audit = AsyncMock(return_value=True)
    monkeypatch.setattr(action, "default_client", lambda database: redis)
    monkeypatch.setattr(action, "audit_log", audit)
    monkeypatch.setattr(action, "kb_index_names", lambda: (INDEX,))
    monkeypatch.setattr(action, "review_kb_proposal", AsyncMock(return_value=False))
    return types.SimpleNamespace(redis=redis, audit=audit)


def _approval(plan=None, status="approved"):
    plan = {"selector": action._selector(), "indexes": [INDEX], "chunks": 3} if plan is None else plan
    approval = types.SimpleNamespace(
        id=uuid.uuid4(),
        status=status,
        decided_by_user="alice",
        decided_at=datetime(2026, 11, 19, 9, 0, tzinfo=timezone.utc),
        requested_by_agent="claude-md-reindex:operator",
        context={"action": action.ACTION, "channel": "operator", "plan": plan},
    )
    set_verified_decider(approval, uuid.uuid4())
    return approval


def _session():
    session = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_planning_counts_only_the_selectors_chunks_and_deletes_nothing(world):
    plan = await action.plan_claude_md_reindex(lambda database: world.redis)
    assert plan["chunks"] == 3 and plan["indexes"] == [INDEX] and plan["selector"] == action._selector()
    assert world.redis.unlinked == [] and len(world.redis.data) == len(_chunks())


@pytest.mark.asyncio
async def test_a_proposal_is_filed_and_nothing_is_deleted(world, monkeypatch):
    created = {}

    class Gate:
        def __init__(self, session):
            pass

        async def create_approval(self, **kwargs):
            created.update(kwargs)
            return types.SimpleNamespace(id=uuid.uuid4(), status="pending")

    monkeypatch.setattr("services.approval_gate_service.ApprovalGateService", Gate)
    monkeypatch.setattr(action, "_pending_proposal", AsyncMock(return_value=None))
    session = MagicMock()
    session.execute = AsyncMock()
    plan = await action.plan_claude_md_reindex(lambda database: world.redis)
    await action.propose_claude_md_reindex(session, "operator", plan)
    assert created["approval_type"] == "destructive_action" and created["context"]["action"] == action.ACTION
    assert created["context"]["plan"]["selector"] == action._selector() and "keys" not in created["context"]["plan"]
    assert world.redis.unlinked == [] and len(world.redis.data) == len(_chunks())


@pytest.mark.asyncio
async def test_approval_deletes_exactly_the_scoped_chunks_and_others_survive(world):
    session = _session()
    await action.execute_claude_md_reindex_action(_approval(), session)
    assert sorted(world.redis.unlinked) == ["doc:claude-0", "doc:claude-1", "doc:claude-2"]
    assert set(world.redis.data) == {
        "doc:other-1",
        "doc:untitled",
        "doc:version:abc",
        "fact:1",
        "doc:same-title-other-source",
        "doc:same-title-no-source",
    }
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_audit_is_durable_intent_first_then_success(world):
    await action.execute_claude_md_reindex_action(_approval(), _session())
    calls = world.audit.await_args_list
    assert [c.kwargs["result"] for c in calls] == ["attempted", "success"]
    assert all(c.args == ("knowledge.claude_md_reindex",) and c.kwargs["durable"] is True for c in calls)
    assert calls[0].kwargs["details"]["chunks"] == 3 and calls[1].kwargs["details"]["deleted"] == 3
    assert calls[0].kwargs["details"]["selector"] == action._selector()


@pytest.mark.asyncio
async def test_no_committed_intent_entry_means_nothing_is_deleted(world):
    world.audit.return_value = False
    with pytest.raises(RuntimeError, match="nothing was deleted"):
        await action.execute_claude_md_reindex_action(_approval(), _session())
    assert world.redis.unlinked == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plan",
    [
        {"selector": {**action._selector(), "value": OTHER_TITLE}, "indexes": [INDEX]},
        {"selector": {**action._selector(), "prefix": "fact:"}, "indexes": [INDEX]},
        {"selector": action._selector(), "indexes": ["a_foreign_index"]},
        {"indexes": [INDEX]},
    ],
)
async def test_a_scope_that_is_not_the_codes_is_refused_and_deletes_nothing(world, plan):
    with pytest.raises(ValueError):
        await action.execute_claude_md_reindex_action(_approval(plan), _session())
    assert world.redis.unlinked == []


@pytest.mark.asyncio
async def test_a_client_key_list_in_the_plan_is_never_used(world):
    plan = {"selector": action._selector(), "indexes": [INDEX], "chunks": 3, "keys": ["fact:1", "doc:other-1"]}
    await action.execute_claude_md_reindex_action(_approval(plan), _session())
    assert "fact:1" in world.redis.data and "doc:other-1" in world.redis.data


@pytest.mark.asyncio
async def test_an_unapproved_or_undeciphered_decision_deletes_nothing(world):
    with pytest.raises(ValueError):
        await action.execute_claude_md_reindex_action(_approval(status="pending"), _session())
    undecided = _approval()
    set_verified_decider(undecided, None)
    with pytest.raises(ValueError):
        await action.execute_claude_md_reindex_action(undecided, _session())
    assert world.redis.unlinked == []


@pytest.mark.asyncio
async def test_a_failed_delete_audits_how_far_it_got_and_re_raises(world, monkeypatch):
    def broken(*keys):
        raise ConnectionError("lost")

    monkeypatch.setattr(world.redis, "unlink", broken)
    with pytest.raises(ConnectionError):
        await action.execute_claude_md_reindex_action(_approval(), _session())
    last = world.audit.await_args.kwargs
    assert (
        last["result"] == "failed" and last["details"]["deleted"] == 0 and last["details"]["error"] == "ConnectionError"
    )


def test_registration_is_server_only_admin_only_and_proposed_in_this_module():
    action.register_claude_md_reindex_action()
    assert action.ACTION in _REGISTRY and action.ACTION in _SERVER_ONLY and action.ACTION in _ADMIN_ONLY


def test_importing_the_approvals_router_registers_the_handler_in_a_fresh_interpreter():
    code = (
        "import api.approval_gates, services.approval_execution as e; "
        f"print({action.ACTION!r} in e._REGISTRY and {action.ACTION!r} in e._SERVER_ONLY)"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(_BACKEND), str(_BACKEND.parent)])}
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=300, check=False, cwd=_BACKEND, env=env
    )
    assert done.returncode == 0 and done.stdout.strip().endswith("True"), done.stderr[-800:]


@pytest.mark.asyncio
async def test_a_document_with_the_same_title_but_another_source_survives_the_approved_delete(world):
    await action.execute_claude_md_reindex_action(_approval(), _session())
    assert "doc:same-title-other-source" in world.redis.data and "doc:same-title-no-source" in world.redis.data
    assert not any(k.startswith("doc:claude-") for k in world.redis.data)


@pytest.mark.asyncio
async def test_more_chunks_than_approved_is_refused_audited_and_deletes_nothing(world):
    approval = _approval({"selector": action._selector(), "indexes": [INDEX], "chunks": 2})
    with pytest.raises(ValueError, match="nothing was deleted"):
        await action.execute_claude_md_reindex_action(approval, _session())
    assert world.redis.unlinked == []
    refusal = world.audit.await_args.kwargs
    assert refusal["result"] == "failed" and refusal["details"]["phase"] == "refused"
    assert refusal["details"]["approved_chunks"] == 2 and refusal["details"]["found_chunks"] == 3


@pytest.mark.asyncio
async def test_fewer_chunks_than_approved_still_deletes_what_remains(world):
    approval = _approval({"selector": action._selector(), "indexes": [INDEX], "chunks": 9})
    await action.execute_claude_md_reindex_action(approval, _session())
    assert len(world.redis.unlinked) == 3


@pytest.mark.asyncio
async def test_a_plan_without_a_count_is_refused(world):
    with pytest.raises(ValueError):
        await action.execute_claude_md_reindex_action(
            _approval({"selector": action._selector(), "indexes": [INDEX]}), _session()
        )
    assert world.redis.unlinked == []


@pytest.mark.asyncio
async def test_a_repeat_proposal_refreshes_the_pending_plan_durably(world, monkeypatch):
    from services import kb_wipe_action

    refresh_audit = AsyncMock(return_value=True)
    monkeypatch.setattr(kb_wipe_action, "audit_log", refresh_audit)
    pending = _approval({"selector": action._selector(), "indexes": [INDEX], "chunks": 1}, status="pending")
    pending.context["requested_by"] = "operator"
    monkeypatch.setattr(action, "_pending_proposal", AsyncMock(return_value=pending))
    session = MagicMock()
    session.execute, session.add, session.commit = AsyncMock(), MagicMock(), AsyncMock()
    fresh = {"selector": action._selector(), "indexes": [INDEX], "chunks": 3}
    assert await action.propose_claude_md_reindex(session, "second-operator", fresh) is pending
    assert pending.context["plan"]["chunks"] == 3 and pending.context["refreshed_by"] == ["second-operator"]
    kwargs = refresh_audit.await_args.kwargs
    assert refresh_audit.await_args.args == ("knowledge.claude_md_reindex.refresh",) and kwargs["durable"] is True
    assert kwargs["details"]["counts"] == {"chunks": [1, 3]}
    session.commit.assert_awaited_once()
