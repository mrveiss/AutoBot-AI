# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A session delete never removes a legacy transcript -- end to end (#18293, #17038).

Two review rounds found a cross-user deletion: ``validate_session_ownership`` hands
an ownerless session to whoever asks (``legacy_migration``), and "the session file
records the caller as owner" can be MANUFACTURED --

* H2: create a session over another user's legacy-only id -> the creator is the owner;
* H1: claim it, then ``POST /chats/{id}/save`` stamps ``metadata.owner`` on the file.

Nothing here stubs an ownership ``reason`` or a recorded owner. The real
``SessionOwnershipValidator`` decides (enforced mode, an in-memory Redis), a real
``ChatHistoryManager`` writes session files under ``tmp_path``, and the real
``create_session`` / ``save_chat_by_id`` / ``delete_session`` bodies and the chat
workflow's own ``_load_conversation_history`` run. Stubbed:
the authenticated identity, the side services a delete also cleans up (terminal,
KB, files, events, audit), and the one Postgres write that records a proposal.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

import api.chat as chat_api
import api.chat_sessions as chat_sessions
import api.legacy_transcript_disposal as disposal
from api.schemas_chat import SessionCreate
from autobot_shared.ssot_config import config
from chat_history import ChatHistoryManager
from chat_workflow.conversation import ConversationHandlerMixin
from security.session_ownership import SessionOwnershipValidator
from services.feature_flags import EnforcementMode
from testkit.canonical_gate import install_canonical_resolver

ALICE, BOB = "alice", "bob"
LEGACY_ID = "5f0c9a5e-1b2c-4d3e-8f90-0a1b2c3d4e5f"
OWN_ID = "6a1d0b6f-2c3d-4e4f-9a01-1b2c3d4e5f60"


class _Redis:
    """In-memory async Redis: just the calls the ownership validator makes."""

    def __init__(self) -> None:
        self.kv: dict = {}

    async def get(self, key):
        return self.kv.get(key)

    async def set(self, key, value, ex=None):
        self.kv[key] = value
        return True

    async def sadd(self, key, *members):
        self.kv.setdefault(key, set()).update(members)

    async def expire(self, key, seconds):
        return True

    async def sismember(self, key, member):
        return member in self.kv.get(key, set())

    async def smembers(self, key):
        return self.kv.get(key, set())


class _World:
    """One backend: a chat store, an ownership validator, a legacy dir, and who is calling."""

    def __init__(self, tmp_path: Path, monkeypatch) -> None:
        self.legacy = tmp_path / "data" / "conversation_transcripts"
        self.legacy.mkdir(parents=True)
        monkeypatch.setattr(config.path, "legacy_transcripts_dir", str(self.legacy), raising=False)
        monkeypatch.chdir(tmp_path)  # the pre-fix tree resolved the same directory from the cwd
        chats = tmp_path / "chats"
        chats.mkdir()
        self.history = ChatHistoryManager(history_file=str(tmp_path / "history.json"), use_redis=False)
        self.history.redis_client = None
        monkeypatch.setattr(self.history, "_get_chats_directory", lambda: str(chats))
        flags = SimpleNamespace(
            get_enforcement_mode=AsyncMock(return_value=EnforcementMode.ENFORCED),
            get_endpoint_enforcement=AsyncMock(return_value=None),
        )
        self.validator = SessionOwnershipValidator(_Redis(), feature_flags=flags)
        self.validator._audit_log_success = MagicMock()
        self.caller = ALICE
        self.proposals: list = []
        self._wire(monkeypatch)

    def _wire(self, monkeypatch) -> None:
        # Identity per request: whoever ``self.caller`` names. Every module that asks the auth
        # middleware for the user is pointed here -- since #18258 the validator asks through
        # ``security.session_posture.authenticated_user``, which resolves through the REAL
        # ``resolve_human_user`` (#18688); missing that seam silently authenticated every
        # request as the stub's default user.
        auth = SimpleNamespace(
            enable_auth=True,
            get_user_from_request=lambda _r: {"username": self.caller, "role": "user"},
            security_layer=MagicMock(),
        )
        for resolver in ("security.session_posture", "api.chat_sessions"):
            install_canonical_resolver(monkeypatch, f"{resolver}.resolve_human_user", auth)
        for module in ("security.session_ownership", "api.chat_sessions"):
            monkeypatch.setattr(f"{module}.get_auth_middleware", lambda: auth)
        for target in ("utils.chat_utils", "api.chat_sessions", "api.chat"):
            monkeypatch.setattr(f"{target}.get_chat_history_manager", lambda _r: self.history)
        for name in ("_handle_conversation_files", "_cleanup_terminal_sessions"):
            monkeypatch.setattr(chat_sessions, name, AsyncMock(return_value={}))
        for name in ("_cleanup_knowledge_base_facts", "_cleanup_chat_knowledge_context"):
            monkeypatch.setattr(chat_sessions, name, AsyncMock(return_value={}))
        for name in ("_emit_session_destroy", "publish_session_deleted"):
            monkeypatch.setattr(chat_sessions, name, AsyncMock())
        for name in ("log_chat_event", "audit_record", "log_request_context"):
            monkeypatch.setattr(chat_sessions, name, MagicMock())
        monkeypatch.setattr(chat_api, "log_request_context", MagicMock())
        # the workflow builds its own manager; give it this backend's store, nothing else
        monkeypatch.setattr("chat_history.ChatHistoryManager", lambda: self.history)

        async def _propose(session_id, requested_by, why):
            self.proposals.append((session_id, requested_by))
            return f"approval-{len(self.proposals)}"

        monkeypatch.setattr(disposal, "propose_transcript_disposal", _propose)

    def request(self):
        return SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace()),
            client=None,
            headers={},
            url=SimpleNamespace(path="/api/chat/sessions/x"),
            scope={"route": SimpleNamespace(path="/api/chat/sessions/{session_id}")},
        )

    def write_legacy(self, session_id: str) -> Path:
        path = self.legacy / f"{session_id}.json"
        path.write_text('{"messages": [{"user": "private", "assistant": "data"}]}', encoding="utf-8")
        return path

    async def ownership(self, session_id: str) -> dict:
        return await self.validator.validate_ownership(session_id, self.request())

    async def create(self, session_id: str):
        return await chat_sessions.create_session.__wrapped__(SessionCreate(id=session_id), self.request())

    async def save(self, session_id: str, ownership: dict, messages: list | None = None):
        data = {"data": {"messages": messages or [{"sender": "user", "text": "hi"}]}}
        save = chat_api.save_chat_by_id.__wrapped__
        return await save(session_id, {"username": self.caller}, data, self.request(), ownership)

    async def context(self, session_id: str) -> list:
        """The LLM context the real chat workflow would load for *session_id* (no cache)."""

        class _Workflow(ConversationHandlerMixin):
            redis_client = None
            conversation_history_ttl = 60

        return await _Workflow()._load_conversation_history(session_id)

    async def delete(self, session_id: str, ownership: dict):
        body = chat_sessions.delete_session.__wrapped__
        return await body(session_id, self.request(), ownership=ownership, file_action="delete", file_options=None)


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


@pytest.fixture
def world(tmp_path, monkeypatch) -> _World:
    return _World(tmp_path, monkeypatch)


@pytest.mark.asyncio
async def test_h2_creating_over_a_legacy_only_id_is_refused(world) -> None:
    transcript = world.write_legacy(LEGACY_ID)  # BOB's, from before #13214
    before = _bytes(transcript)

    with pytest.raises(HTTPException) as raised:
        await world.create(LEGACY_ID)

    assert raised.value.status_code == 409
    assert _bytes(transcript) == before
    assert await world.history.get_session(LEGACY_ID) is None


@pytest.mark.asyncio
async def test_h1_claim_then_save_then_delete_keeps_the_transcript(world) -> None:
    transcript = world.write_legacy(LEGACY_ID)

    claim = await world.ownership(LEGACY_ID)
    assert claim["reason"] == "legacy_migration"  # decided by the real validator
    await world.save(LEGACY_ID, claim)
    assert await world.history.get_session_owner(LEGACY_ID) == ALICE  # the save stamped the file

    second = await world.ownership(LEGACY_ID)
    assert second["reason"] == "owner_match"
    await world.delete(LEGACY_ID, second)

    assert transcript.exists()
    assert world.proposals == [(LEGACY_ID, ALICE)]


@pytest.mark.asyncio
async def test_the_owner_deleting_their_own_session_gets_a_proposal(world) -> None:
    await world.create(OWN_ID)
    transcript = world.write_legacy(OWN_ID)  # a session from before #18293, in both stores

    ownership = await world.ownership(OWN_ID)
    assert ownership["reason"] == "owner_match"
    await world.delete(OWN_ID, ownership)

    assert transcript.exists()
    assert world.proposals == [(OWN_ID, ALICE)]
    assert await world.history.get_session(OWN_ID) is None


@pytest.mark.asyncio
async def test_another_user_cannot_delete_an_owned_session(world) -> None:
    await world.create(OWN_ID)
    transcript = world.write_legacy(OWN_ID)
    world.caller = BOB

    with pytest.raises(HTTPException) as raised:
        await world.ownership(OWN_ID)

    assert raised.value.status_code == 403
    assert transcript.exists() and world.proposals == []


@pytest.mark.asyncio
async def test_deleting_a_legacy_only_session_is_a_404_with_a_proposal(world) -> None:
    transcript = world.write_legacy(LEGACY_ID)
    claim = await world.ownership(LEGACY_ID)

    with pytest.raises(Exception, match="not found") as raised:
        await world.delete(LEGACY_ID, claim)

    assert "approval-1" in str(raised.value)
    assert transcript.exists() and world.proposals == [(LEGACY_ID, ALICE)]
    chat_sessions._cleanup_terminal_sessions.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_claimed_legacy_only_session_gets_empty_llm_context(world) -> None:
    """A claimer must not be handed another user's legacy conversation as context."""
    transcript = world.write_legacy(LEGACY_ID)
    claim = await world.ownership(LEGACY_ID)
    assert claim["reason"] == "legacy_migration"

    assert await world.context(LEGACY_ID) == []
    assert transcript.exists()


@pytest.mark.asyncio
async def test_a_normal_sessions_context_is_its_own_turns(world) -> None:
    await world.create(OWN_ID)
    ownership = await world.ownership(OWN_ID)
    turns = [
        {"sender": "user", "text": "what is uptime?", "messageType": "default"},
        {"sender": "assistant", "text": "Up 3 days.", "messageType": "response"},
    ]
    await world.save(OWN_ID, ownership, turns)

    assert await world.context(OWN_ID) == [{"user": "what is uptime?", "assistant": "Up 3 days."}]


def test_the_routes_driven_here_use_the_default_posture() -> None:
    """The harness runs ``SessionOwnershipValidator`` -- the DEFAULT posture's body (#18258).

    That is only the right validator if the delete and save routes really take DEFAULT; a route
    moved to STRICT would make these tests exercise a decision production no longer makes.
    """
    import inspect

    from security.session_ownership import validate_session_ownership

    delete_dep = inspect.signature(chat_sessions.delete_session).parameters["ownership"].default.dependency
    assert delete_dep is validate_session_ownership
    for route in (chat_api.save_chat_by_id, chat_api.delete_chat_by_id):
        assert inspect.signature(route).parameters["ownership"].default.dependency is chat_api.validate_chat_ownership
    assert "STRICT" not in inspect.getsource(chat_api.validate_chat_ownership)
