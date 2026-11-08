# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PUT /chat/sessions/{id} writes through the manager's real API; POST and PUT share one strip (#20928).

The route used to call ``update_session(session_id=, title=, metadata=)`` on a manager whose
method takes ``(session_id, updates)`` and returns a bool, so it raised ``TypeError`` on every
request. A real ``ChatHistoryManager`` writing under ``tmp_path`` is used: a mock accepting any
arguments would have passed against the broken call.
"""

import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.chat_sessions as chat_sessions
import api.chat_sessions_update as chat_sessions_update
from api.schemas_chat import SessionUpdate
from autobot_memory_graph.owner_scope import OwnerScope
from chat_history import ChatHistoryManager
from chat_history.graph_owner import session_owner_scope
from exceptions import InternalError, ResourceNotFoundError
from security.session_ownership import SessionOwnershipValidator, build_owner_metadata
from services.feature_flags import EnforcementMode

SID = "6a1d0b6f-2c3d-4e4f-9a01-1b2c3d4e5f60"


@pytest.fixture
def history(tmp_path, monkeypatch):
    chats = tmp_path / "chats"
    chats.mkdir()
    manager = ChatHistoryManager(history_file=str(tmp_path / "history.json"), use_redis=False)
    manager.redis_client = None
    monkeypatch.setattr(manager, "_get_chats_directory", lambda: str(chats))
    monkeypatch.setattr(chat_sessions, "get_chat_history_manager", lambda _r: manager)
    monkeypatch.setattr(chat_sessions, "publish_session_updated", AsyncMock())
    for name in ("log_chat_event", "log_request_context"):
        monkeypatch.setattr(chat_sessions, name, MagicMock())
    return manager


async def _put(body: SessionUpdate, sid: str = SID):
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    return await chat_sessions.update_session.__wrapped__(sid, body, request, ownership={"valid": True})


@pytest.mark.asyncio
async def test_put_applies_title_and_merges_metadata(history):
    await history.create_session(session_id=SID, title="old", metadata={"owner": "alice"})

    response = await _put(SessionUpdate(title="new title", metadata={"color": "red"}))

    stored = await history.get_session(SID)
    assert stored["name"] == "new title"
    assert stored["metadata"]["color"] == "red"
    assert stored["metadata"]["owner"] == "alice"  # a merge: server-written keys survive
    assert response.status_code == 200
    assert b"new title" in response.body


@pytest.mark.asyncio
async def test_put_on_absent_session_is_not_found(history):
    with pytest.raises(ResourceNotFoundError):
        await _put(SessionUpdate(title="x"))


@pytest.mark.asyncio
async def test_put_failed_write_is_an_error_not_success(history, monkeypatch):
    await history.create_session(session_id=SID, title="old")

    async def _refuse(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(history, "_write_session_to_storage", _refuse)

    with pytest.raises(InternalError):
        await _put(SessionUpdate(title="new"))


@pytest.mark.asyncio
async def test_put_metadata_failure_leaves_name_unchanged(history, monkeypatch):
    """Metadata is written before the title, so a refused metadata write never renames (#20928)."""
    await history.create_session(session_id=SID, title="old", metadata={"owner": "alice"})

    async def _refuse(*_a, **_k):
        return False

    monkeypatch.setattr(history, "update_session_metadata", _refuse)

    with pytest.raises(InternalError):
        await _put(SessionUpdate(title="new", metadata={"color": "red"}))

    stored = await history.get_session(SID)
    assert stored["name"] == "old"
    assert stored["metadata"] == {"owner": "alice"}


def _noop(name: str):
    """A stand-in for a create-route side effect (audit, hooks, live event): sync or async to match."""
    if name == "audit_record":
        return lambda *_a, **_k: None

    async def _done(*_a, **_k):
        return None

    return _done


@contextlib.contextmanager
def _real_route(history, username: str, *, anonymous_create: bool = False):
    """The real router with the REAL ``validate_session_ownership`` dependency, authenticated as *username*.

    Only the leaves are stubbed (flags, Redis, metrics, the auth middleware, the identity lookup); the
    owner is read from the real manager's stored session, and the ownership decision is the code under test.
    """
    flags = MagicMock()
    flags.get_enforcement_mode = AsyncMock(return_value=EnforcementMode.ENFORCED)
    flags.get_endpoint_enforcement = AsyncMock(return_value=None)
    auth = MagicMock()
    auth.enable_auth = True

    async def _owner(_self, session_id):
        return await history.get_session_owner(session_id)

    user = {"username": username, "user_id": f"{username}-id", "auth_disabled": False}
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("services.feature_flags.get_feature_flags", AsyncMock(return_value=flags)))
        stack.enter_context(patch("autobot_shared.redis_client.get_redis_client", AsyncMock(return_value=MagicMock())))
        stack.enter_context(patch("services.access_control_metrics.get_metrics_service", AsyncMock(return_value=None)))
        stack.enter_context(patch("security.session_ownership.get_auth_middleware", return_value=auth))
        stack.enter_context(patch.object(SessionOwnershipValidator, "get_session_owner", _owner))
        stack.enter_context(
            patch.object(SessionOwnershipValidator, "_is_org_admin_access", AsyncMock(return_value=False))
        )
        stack.enter_context(
            patch.object(SessionOwnershipValidator, "_record_violation_metrics", AsyncMock(return_value=None))
        )
        stack.enter_context(
            patch.object(SessionOwnershipValidator, "_get_authenticated_user", AsyncMock(return_value=user))
        )
        creator = None if anonymous_create else user
        stack.enter_context(patch.object(chat_sessions, "resolve_human_user", AsyncMock(return_value=creator)))
        for name in ("audit_record", "_emit_session_create", "publish_session_created"):
            stack.enter_context(patch.object(chat_sessions, name, MagicMock(side_effect=_noop(name))))
        app = FastAPI()
        app.include_router(chat_sessions.router)
        yield TestClient(app, raise_server_exceptions=False)


async def _seed_owned(history, owner: str, title: str = "old") -> None:
    await history.create_session(session_id=SID, title=title, metadata=build_owner_metadata({"username": owner}))


@pytest.mark.asyncio
async def test_put_from_a_non_owner_is_refused_and_writes_nothing(history):
    await _seed_owned(history, "alice")
    before = await history.get_session(SID)

    with _real_route(history, "mallory") as client:
        response = client.put(f"/chat/sessions/{SID}", json={"title": "hijacked", "metadata": {"color": "red"}})

    assert response.status_code in (403, 404), response.text
    after = await history.get_session(SID)
    assert after["name"] == before["name"] == "old"
    assert after["metadata"] == before["metadata"]


@pytest.mark.asyncio
async def test_put_from_the_owner_succeeds_through_the_real_dependency(history):
    await _seed_owned(history, "alice")

    with _real_route(history, "alice") as client:
        response = client.put(f"/chat/sessions/{SID}", json={"title": "renamed", "metadata": {"color": "red"}})

    assert response.status_code == 200
    stored = await history.get_session(SID)
    assert stored["name"] == "renamed"
    assert stored["metadata"]["color"] == "red"


async def _assert_put_ignores_planted_owner_keys(history):
    await _seed_owned(history, "alice")
    original = (await history.get_session(SID))["metadata"]

    with _real_route(history, "alice") as client:
        response = client.put(
            f"/chat/sessions/{SID}",
            json={"metadata": {"owner": "mallory", "username": "mallory", "org_id": "x", "color": "red"}},
        )

    assert response.status_code == 200
    stored = (await history.get_session(SID))["metadata"]
    assert stored["owner"] == original["owner"] == "alice"
    assert stored["username"] == original["username"] == "alice"
    assert stored.get("org_id") == original.get("org_id")
    assert stored["color"] == "red"  # other keys still merge


@pytest.mark.asyncio
async def test_put_metadata_cannot_change_server_controlled_keys(history):
    await _assert_put_ignores_planted_owner_keys(history)


PLANTED = {"owner": "mallory", "username": "mallory", "user_id": "mallory-id", "org_id": "x", "team_id": "x"}


async def _create_with_planted_keys(history, *, anonymous: bool = False) -> dict:
    """POST /chat/sessions through the real router with client-sent ownership keys; return stored metadata."""
    with _real_route(history, "alice", anonymous_create=anonymous) as client:
        response = client.post("/chat/sessions", json={"id": SID, "metadata": {**PLANTED, "color": "red"}})
    assert response.status_code == 201, response.text
    return (await history.get_session(SID))["metadata"]


async def _assert_create_keeps_server_owner_keys(history):
    stored = await _create_with_planted_keys(history)
    assert stored["owner"] == stored["username"] == "alice"
    assert stored["user_id"] == "alice-id"
    assert "org_id" not in stored and "team_id" not in stored  # the principal has none; the client's are dropped
    assert stored["color"] == "red"  # a benign key is kept


@pytest.mark.asyncio
async def test_create_metadata_cannot_set_server_controlled_keys(history):
    await _assert_create_keeps_server_owner_keys(history)


@pytest.mark.asyncio
async def test_anonymous_create_stores_no_client_ownership_keys(history):
    stored = await _create_with_planted_keys(history, anonymous=True)
    assert not set(stored) & set(PLANTED)
    assert stored["color"] == "red"
    assert session_owner_scope(stored) == OwnerScope.system()


@pytest.mark.asyncio
async def test_created_session_graph_owner_is_the_server_principal(history):
    stored = await _create_with_planted_keys(history)
    assert session_owner_scope(stored) == OwnerScope.for_user("alice-id")


def _disable_strip(monkeypatch):
    for module in (chat_sessions, chat_sessions_update):
        monkeypatch.setattr(module, "strip_server_controlled", lambda metadata: dict(metadata or {}))


@pytest.mark.asyncio
@pytest.mark.parametrize("check", [_assert_create_keeps_server_owner_keys, _assert_put_ignores_planted_owner_keys])
async def test_control_the_checks_fail_without_the_strip(history, monkeypatch, check):
    """Control: with the strip made an identity, the create and PUT owner-key checks fail (#20928)."""
    _disable_strip(monkeypatch)
    with pytest.raises(AssertionError):
        await check(history)
