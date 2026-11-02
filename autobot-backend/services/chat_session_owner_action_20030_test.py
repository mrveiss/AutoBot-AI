# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20030: an ownerless session gets an owner only through an approved proposal, with a record."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import approval_execution
from services import chat_session_owner_action as action

_ADMIN, _OTHER = uuid.uuid4(), uuid.uuid4()


class _Manager:
    def __init__(self, owners: dict, fail: bool = False) -> None:
        self.owners, self.fail, self.written = owners, fail, []

    async def session_exists(self, session_id):
        return session_id in self.owners

    async def list_sessions(self):
        return [{"chatId": session_id} for session_id in self.owners]

    async def get_session_owner(self, session_id):
        if self.owners[session_id] == "UNREADABLE":
            raise action.SessionOwnerUnreadable(session_id)
        return self.owners[session_id]

    async def update_session_metadata(self, session_id, metadata):
        self.written.append((session_id, metadata))
        return not self.fail


def _session(user_exists: bool = True, admins: int = 2) -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    found = MagicMock()
    found.scalars.return_value.first.return_value = uuid.uuid4() if user_exists else None
    found.scalar_one.return_value = admins
    session.execute = AsyncMock(return_value=found)
    return session


def _approval(decider=_OTHER, requested_by=_ADMIN, session_id="s1", owner="alice") -> SimpleNamespace:
    approval = SimpleNamespace(
        id=uuid.uuid4(),
        decided_by_user="owner",
        requested_by_agent=f"chat-session-owner:{requested_by}",
        context={"action": action.ACTION, "session_id": session_id, "owner": owner},
    )
    approval_execution.set_verified_decider(approval, decider)
    return approval


def _validator(cached=None, redis_set=None, claim=None) -> SimpleNamespace:
    """Redis as claim sees it: SET NX succeeds only when no owner is cached."""
    return SimpleNamespace(
        set_session_owner=redis_set or AsyncMock(return_value=True),
        get_session_owner=AsyncMock(return_value=cached),
        redis=SimpleNamespace(set=claim or AsyncMock(return_value=cached is None), delete=AsyncMock()),
        ownership_ttl=60,
        _get_ownership_key=lambda session_id: f"key:{session_id}",
    )


async def _run(manager: _Manager, approval, session, cached=None, redis_set=None, claim=None):
    validator = _validator(cached, redis_set, claim)
    redis_set = validator.set_session_owner
    with (
        patch.object(action, "ChatHistoryManager", return_value=manager),
        patch.object(action, "get_redis_client", AsyncMock()),
        patch.object(action, "SessionOwnershipValidator", return_value=validator),
        patch.object(action, "audit_log", AsyncMock()) as audit,
    ):
        await action.execute_owner_assign(approval, session)
    return redis_set, audit


async def test_the_report_lists_ownerless_apart_from_unreadable() -> None:
    manager = _Manager({"a": "bob", "b": None, "c": "UNREADABLE"})
    assert await action.ownerless_report(manager) == (["b"], ["c"])


async def test_approval_writes_the_owner_to_file_and_redis_with_a_record() -> None:
    manager, session = _Manager({"s1": None}), _session()
    redis_set, audit = await _run(manager, _approval(), session)
    assert manager.written[0][1]["owner"] == "alice" and manager.written[0][1]["username"] == "alice"
    redis_set.assert_awaited_once_with("s1", "alice")
    assert "now belongs to alice" in session.add.call_args.args[0].body
    assert [c.kwargs["details"]["stage"] for c in audit.await_args_list] == ["started", "success"]


async def test_a_session_that_gained_an_owner_is_left_alone() -> None:
    manager, session = _Manager({"s1": "bob"}), _session()
    _, audit = await _run(manager, _approval(), session)
    assert manager.written == [] and "already belongs to bob" in session.add.call_args.args[0].body
    assert audit.await_args.args[1:] == () and audit.await_args.kwargs["details"]["stage"] == "skipped"


async def test_the_only_admin_may_self_approve_and_it_is_flagged() -> None:
    session = _session(admins=1)
    _, audit = await _run(_Manager({"s1": None}), _approval(decider=_ADMIN), session)
    assert "(self-approved)" in session.add.call_args.args[0].body
    assert audit.await_args.kwargs["details"]["self_approval"] is True


async def test_a_self_approval_with_another_admin_writes_nothing() -> None:
    manager = _Manager({"s1": None})
    with pytest.raises(ValueError):
        await _run(manager, _approval(decider=_ADMIN), _session(admins=2))
    assert manager.written == []


@pytest.mark.parametrize(
    "approval, user_exists",
    [
        (_approval(decider=None), True),
        (_approval(requested_by="someone"), True),
        (_approval(owner=""), True),
        (_approval(session_id=""), True),
        (_approval(), False),
    ],
    ids=["no-verified-decider", "unknown-requester", "no-owner", "no-session", "owner-not-a-user"],
)
async def test_a_bad_approval_writes_nothing(approval, user_exists: bool) -> None:
    manager = _Manager({"s1": None})
    with pytest.raises(ValueError):
        await _run(manager, approval, _session(user_exists))
    assert manager.written == []


async def test_a_failed_file_write_records_no_success() -> None:
    manager, session = _Manager({"s1": None}, fail=True), _session()
    audit = AsyncMock()
    validator = _validator()
    with (
        patch.object(action, "ChatHistoryManager", return_value=manager),
        patch.object(action, "get_redis_client", AsyncMock()),
        patch.object(action, "SessionOwnershipValidator", return_value=validator),
        patch.object(action, "audit_log", audit),
        pytest.raises(ValueError),
    ):
        await action.execute_owner_assign(_approval(), session)
    assert [c.kwargs["details"]["stage"] for c in audit.await_args_list] == ["started"]
    validator.redis.delete.assert_awaited_once_with("key:s1")  # the failed proposal leaves no claim


async def test_an_owner_only_in_redis_is_left_alone() -> None:
    manager, session = _Manager({"s1": None}), _session()
    redis_set, audit = await _run(manager, _approval(), session, cached="bob")
    assert manager.written == [] and "already belongs to bob" in session.add.call_args.args[0].body
    redis_set.assert_not_awaited()
    assert audit.await_args.kwargs["details"]["stage"] == "skipped"


async def test_a_redis_record_of_the_named_owner_does_not_block_writing_the_file() -> None:
    manager = _Manager({"s1": None})
    await _run(manager, _approval(), _session(), cached="alice")
    assert manager.written


@pytest.mark.parametrize(
    "redis_set", [AsyncMock(side_effect=OSError("down")), AsyncMock(return_value=False)], ids=["raises", "refused"]
)
async def test_a_redis_failure_after_the_file_is_recorded_as_partial(redis_set) -> None:
    manager, session = _Manager({"s1": None}), _session()
    _, audit = await _run(manager, _approval(), session, redis_set=redis_set)
    assert manager.written and "Redis record was not written" in session.add.call_args.args[0].body
    assert audit.await_args.kwargs["result"] == "error" and audit.await_args.kwargs["details"]["stage"] == "partial"


async def test_a_grant_landing_during_the_approval_loses_nothing_and_writes_nothing() -> None:
    """Nothing cached when the approval began, but Redis refuses the claim: someone just took it."""
    manager, session = _Manager({"s1": None}), _session()
    validator = _validator(cached="bob", claim=AsyncMock(return_value=False))
    with (
        patch.object(action, "ChatHistoryManager", return_value=manager),
        patch.object(action, "get_redis_client", AsyncMock()),
        patch.object(action, "SessionOwnershipValidator", return_value=validator),
        patch.object(action, "audit_log", AsyncMock()),
    ):
        await action.execute_owner_assign(_approval(), session)
    assert manager.written == [] and "already belongs to bob" in session.add.call_args.args[0].body
    validator.redis.set.assert_awaited_once_with("key:s1", "alice", nx=True, ex=60)


async def test_redis_failing_at_the_claim_writes_nothing() -> None:
    manager = _Manager({"s1": None})
    with pytest.raises(ConnectionError):
        await _run(manager, _approval(), _session(), claim=AsyncMock(side_effect=ConnectionError()))
    assert manager.written == []


@pytest.mark.parametrize(
    "owners, expected",
    [({"s1": None}, True), ({"s1": "bob"}, False), ({"s1": "UNREADABLE"}, False), ({}, False)],
    ids=["ownerless", "owned", "unreadable", "no-such-session"],
)
async def test_one_sessions_answer_for_a_proposal(owners: dict, expected: bool) -> None:
    manager = _Manager(owners)
    manager.list_sessions = AsyncMock(side_effect=AssertionError("must not read every session"))
    assert await action.session_is_ownerless(manager, "s1") is expected


async def test_an_invalid_session_id_is_not_ownerless() -> None:
    manager = SimpleNamespace(session_exists=AsyncMock(side_effect=ValueError("bad id")))
    assert await action.session_is_ownerless(manager, "../x") is False


def test_the_action_is_server_only_with_its_proposer() -> None:
    action.register_owner_assign_action()
    assert approval_execution.is_server_only_action(action.ACTION)
    assert approval_execution.registered_action_proposers()[action.ACTION] == action.PROPOSED_BY
