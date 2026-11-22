# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every chat belongs to a company; the list shows the active company's chats and the Unassigned ones (#21997).

Each acceptance criterion of the backend half is driven at the route function (or the dependency every session
route shares), not at a helper in isolation.
"""

import ast
import asyncio
import contextlib
import json
import pathlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.datastructures import State

from api import chat_session_company, chat_sessions
from chat_history.company_scope import ActiveCompany
from security import session_company

CO_A = str(uuid.uuid4())
CO_B = str(uuid.uuid4())
_USER = {"username": "alice", "user_id": str(uuid.uuid4()), "role": "user"}

_ALL = [
    {"id": "a1", "companyId": CO_A, "sessionKind": "user", "lastModified": "3"},
    {"id": "a2", "companyId": CO_A.upper(), "sessionKind": "user", "lastModified": "2"},
    {"id": "b1", "companyId": CO_B, "sessionKind": "user", "lastModified": "1"},
    {"id": "u1", "companyId": "", "sessionKind": "user", "lastModified": "0"},
    {"id": "ceo", "companyId": CO_A, "sessionKind": "agent", "lastModified": "9"},
    {"id": "legacy-ceo", "companyId": "", "sessionKind": "user", "title": "CEO · x", "lastModified": "0"},
]


def _request(company: str | None = None):
    request = MagicMock()
    request.headers = {session_company.ACTIVE_COMPANY_HEADER: company} if company else {}
    return request


def _manager(sessions=None, doc=None):
    manager = MagicMock()
    manager.list_sessions_fast = AsyncMock(return_value=list(_ALL if sessions is None else sessions))
    manager.get_session = AsyncMock(return_value=doc)
    manager.set_metadata_if_unset = AsyncMock(return_value=True)
    manager.get_session_company = AsyncMock(return_value=((doc or {}).get("metadata") or {}).get("company_id"))
    manager.get_session_owner = AsyncMock(return_value="alice")
    return manager


def _owning_everything():
    validator = MagicMock()
    validator.get_user_sessions = AsyncMock(return_value=[s["id"] for s in _ALL])
    validator.redis.exists = AsyncMock(return_value=1)
    return validator


def _payload(response) -> dict:
    body = response.body if hasattr(response, "body") else response
    body = json.loads(body) if isinstance(body, (bytes, bytearray)) else body
    return body.get("data", body)


async def _list(company: str | None, scope=None, member=True):
    with (
        patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock()),
        patch.object(chat_sessions, "get_chat_history_manager", return_value=_manager()),
        patch.object(chat_sessions, "_build_ownership_validator", return_value=_owning_everything()),
        patch.object(session_company, "may_act_in_company", new=AsyncMock(return_value=member)),
    ):
        return await chat_sessions.list_sessions(_request(company), dict(_USER), scope=scope, team_id=None)


def _ids(rows) -> set:
    return {s["id"] for s in rows}


class TestListIsScopedByTheActiveCompany:
    """AC2: server-side filter plus a separate Unassigned set."""

    @pytest.mark.asyncio
    async def test_the_active_companys_chats_only_and_unassigned_apart(self):
        data = _payload(await _list(CO_A))
        assert _ids(data["sessions"]) == {"a1", "a2"}
        assert _ids(data["unassigned"]) == {"u1", "legacy-ceo"}
        assert (data["count"], data["unassigned_count"], data["company_id"]) == (2, 2, CO_A)

    @pytest.mark.asyncio
    async def test_another_companys_chat_and_the_agent_chat_are_in_neither_set(self):
        data = _payload(await _list(CO_A))
        assert {"b1", "ceo"}.isdisjoint(_ids(data["sessions"]) | _ids(data["unassigned"]))

    @pytest.mark.asyncio
    async def test_switching_company_changes_the_list(self):
        assert _ids(_payload(await _list(CO_B))["sessions"]) == {"b1"}

    @pytest.mark.asyncio
    async def test_no_active_company_lists_only_untagged_chats(self):
        data = _payload(await _list(None))
        assert _ids(data["sessions"]) == {"u1", "legacy-ceo"} == _ids(data["unassigned"])
        assert data["company_id"] is None

    @pytest.mark.asyncio
    async def test_a_header_naming_a_company_the_caller_is_not_in_is_refused(self):
        with pytest.raises(HTTPException) as refused:
            await _list(CO_B, member=False)
        assert refused.value.status_code == 403
        assert refused.value.detail == "Forbidden"  # the canonical text, autobot_shared.http_refusal


class TestEveryListingRouteAppliesTheSameFilter:
    """AC2: org, team and shared scope, the ``/chats`` alias, chat-init and the bulk export."""

    @pytest.mark.asyncio
    async def test_org_scope(self):
        validator = MagicMock(get_org_sessions=AsyncMock(return_value=[s["id"] for s in _ALL]))
        user = {"org_id": "org", "role": "admin"}
        response = await chat_sessions._list_org_sessions(user, validator, _manager(), "r", ActiveCompany(CO_A))
        data = _payload(response)
        assert _ids(data["sessions"]) == {"a1", "a2"}  # the agent chat "ceo" is in the id list and still absent
        assert "b1" not in _ids(data["sessions"]) and "u1" in _ids(data["unassigned"])

    @pytest.mark.asyncio
    async def test_team_scope(self):
        validator = MagicMock(get_team_sessions=AsyncMock(return_value=["b1", "u1"]))
        data = _payload(await chat_sessions._list_team_sessions("t", validator, _manager(), "r", ActiveCompany(CO_B)))
        assert _ids(data["sessions"]) == {"b1"} and _ids(data["unassigned"]) == {"u1"}

    @pytest.mark.asyncio
    async def test_shared_scope(self):
        validator = MagicMock(get_shared_sessions=AsyncMock(return_value=["a1", "b1", "u1"]))
        with (
            patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock()),
            patch("security.session_ownership.SessionOwnershipValidator", return_value=validator),
            patch.object(chat_sessions, "get_auth_middleware") as auth,
        ):
            auth.return_value.get_user_from_request.return_value = dict(_USER)
            response = await chat_sessions._list_shared_sessions(MagicMock(), "r", _manager(), ActiveCompany(CO_A))
        data = _payload(response)
        assert _ids(data["sessions"]) == {"a1"} and _ids(data["unassigned"]) == {"u1"}

    @pytest.mark.asyncio
    async def test_the_shared_listing_every_flat_route_uses(self):
        with patch.object(chat_sessions, "_filter_user_sessions", new=AsyncMock(side_effect=lambda s, *_: s)):
            rows = await chat_sessions.list_user_sessions(_manager(), "alice", ActiveCompany(CO_A))
        assert _ids(rows) == {"a1", "a2", "u1", "legacy-ceo"}

    @pytest.mark.asyncio
    async def test_bulk_export_carries_the_same_set(self):
        from services import conversation_export

        seen = {}

        async def fake_listing(manager, username, company=None):
            seen["company"] = company
            return [{"id": "a1"}]

        with patch("api.chat_sessions.list_user_sessions", new=fake_listing):
            rows = await conversation_export._sessions_to_export(MagicMock(), "alice", False, ActiveCompany(CO_A))
        assert rows == [{"id": "a1"}] and seen["company"].active == CO_A

    def test_every_user_facing_lister_passes_the_company(self):
        """Grep the behaviour: a route that calls ``list_user_sessions`` and drops the company is a lister left out."""
        root = pathlib.Path(__file__).resolve().parents[1]
        callers = [
            root / "api" / "chat.py",
            root / "api" / "batch_jobs.py",
            root / "api" / "chat_sessions.py",
            root / "services" / "conversation_export.py",
        ]
        for path in callers:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                is_call = isinstance(node, ast.Call) and getattr(node.func, "id", "") == "list_user_sessions"
                if is_call and path.name != "chat_sessions.py":
                    assert len(node.args) + len(node.keywords) >= 3, f"{path.name}:{node.lineno} drops the company"


class TestCreationStampsTheActiveCompany:
    """AC1."""

    @pytest.mark.asyncio
    async def test_stamps_the_active_company(self):
        with patch.object(session_company, "may_act_in_company", new=AsyncMock(return_value=True)):
            stamped = await session_company.creation_company_metadata(_request(CO_A), {}, dict(_USER))
        assert stamped == {"company_id": CO_A}

    @pytest.mark.asyncio
    async def test_no_active_company_is_created_unassigned_not_refused(self):
        assert await session_company.creation_company_metadata(_request(None), {}, dict(_USER)) == {}

    @pytest.mark.asyncio
    async def test_a_client_naming_the_active_company_is_stamped_with_it(self):
        with patch.object(session_company, "may_act_in_company", new=AsyncMock(return_value=True)):
            stamped = await session_company.creation_company_metadata(
                _request(CO_A), {"company_id": CO_A, "session_kind": "agent"}, dict(_USER)
            )
        assert stamped == {"company_id": CO_A}

    @pytest.mark.asyncio
    async def test_a_client_naming_another_company_is_refused(self):
        with patch.object(session_company, "may_act_in_company", new=AsyncMock(return_value=True)):
            with pytest.raises(HTTPException) as refused:
                await session_company.creation_company_metadata(_request(CO_A), {"company_id": CO_B}, dict(_USER))
        assert refused.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_client_naming_a_company_with_none_active_must_be_a_member(self):
        with patch.object(session_company, "may_act_in_company", new=AsyncMock(return_value=False)):
            with pytest.raises(HTTPException):
                await session_company.creation_company_metadata(_request(None), {"company_id": CO_B}, dict(_USER))

    def test_create_session_stamps_after_the_owner_metadata(self):
        source = (pathlib.Path(chat_sessions.__file__)).read_text(encoding="utf-8")
        assert source.index("build_owner_metadata(user_data") < source.index("creation_company_metadata(request")

    def test_a_metadata_merge_cannot_set_the_company(self):
        """PUT /chat/sessions/{id} must not re-tag a chat behind the audited route."""
        from chat_history.owner_keys import strip_server_controlled

        assert strip_server_controlled({"company_id": CO_B, "k": 1}) == {"k": 1}


class TestAnotherCompanysChatIsRefused:
    """AC3: open, read, post, export, all through the one dependency; owner and share rules are unchanged."""

    @pytest.mark.asyncio
    async def test_cross_company_session_is_refused(self):
        doc = {"metadata": {"company_id": CO_B}}
        with (
            patch.object(session_company, "may_act_in_company", new=AsyncMock(return_value=True)),
            patch("utils.chat_utils.get_chat_history_manager", return_value=_manager(doc=doc)),
        ):
            with pytest.raises(HTTPException) as refused:
                await session_company.enforce_session_company("s", _request(CO_A))
        assert (refused.value.status_code, refused.value.detail) == (403, "Forbidden")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stored", [None, {"metadata": {}}, {"metadata": {"company_id": CO_A.upper()}}])
    async def test_unassigned_or_same_company_session_passes(self, stored):
        with (
            patch.object(session_company, "may_act_in_company", new=AsyncMock(return_value=True)),
            patch("utils.chat_utils.get_chat_history_manager", return_value=_manager(doc=stored)),
        ):
            await session_company.enforce_session_company("s", _request(CO_A))

    @pytest.mark.asyncio
    async def test_no_active_company_checks_nothing(self):
        with patch("utils.chat_utils.get_chat_history_manager", side_effect=AssertionError("must not read")):
            await session_company.enforce_session_company("s", _request(None))

    @pytest.mark.asyncio
    async def test_the_first_step_of_every_posture_enforces_it(self):
        """``authenticated_user`` is the first step of the default and STRICT postures and of ``validate_strict_hidden``."""
        from security import session_posture

        refuse = AsyncMock(side_effect=HTTPException(status_code=403, detail="Forbidden"))
        with (
            patch.object(session_posture, "resolve_human_user", new=AsyncMock(return_value=dict(_USER))),
            patch.object(session_posture, "enforce_session_company", new=refuse),
        ):
            with pytest.raises(HTTPException) as refused:
                await session_posture.authenticated_user("s", MagicMock())
        assert refused.value.status_code == 403
        refuse.assert_awaited_once()

    def test_every_session_route_dependency_goes_through_that_first_step(self):
        """Grep the behaviour: the default posture, STRICT and the hidden variant all start at ``authenticated_user``."""
        root = pathlib.Path(__file__).resolve().parents[1] / "security"
        ownership = (root / "session_ownership.py").read_text(encoding="utf-8")
        posture = (root / "session_posture.py").read_text(encoding="utf-8")
        assert "return await authenticated_user(session_id, request)" in ownership  # the default posture
        assert "validate_strict(session_id, await authenticated_user(session_id, request), request)" in ownership
        assert "validate_strict(session_id, await authenticated_user(session_id, request), request)" in posture

    @pytest.mark.asyncio
    async def test_a_service_principal_acts_in_no_company(self):
        scope = await session_company.resolve_company_scope(_request(CO_A), {"service": True, "username": "svc"})
        assert scope.active is None

    def test_the_single_conversation_export_route_checks_the_company(self):
        from api import conversation_export

        source = pathlib.Path(conversation_export.__file__).read_text(encoding="utf-8")
        assert "validate_session_ownership" in source  # read access, which enforces the company (#22002)


def _ownership():
    return {"authorized": True, "reason": "owner_match", "user_data": dict(_USER)}


@contextlib.contextmanager
def _assign_patches(manager, member=True, exists=True, audit=None):
    """ONE patch scope for the assign route; concurrent assigns enter it once, around both calls."""
    with (
        patch.object(chat_session_company, "get_chat_history_manager", return_value=manager),
        patch("utils.chat_utils.get_chat_history_manager", return_value=manager),
        patch.object(chat_session_company, "may_act_in_company", new=AsyncMock(return_value=member)),
        patch.object(chat_session_company, "company_exists", new=AsyncMock(return_value=exists)),
        patch.object(chat_session_company, "publish_session_updated", new=AsyncMock()),
        patch("security.session_share_audit.audit_log", new=audit),
        patch("api.chat_sessions.log_request_context"),
    ):
        yield


async def _call_assign(company):
    body = chat_session_company.SessionCompanyAssign(company_id=company)
    return await chat_session_company.assign_session_company("s1", body, MagicMock(), _ownership())


async def _assign(manager, company=CO_A, member=True, exists=True, audit=None):
    audit = audit if audit is not None else AsyncMock(return_value=True)
    with _assign_patches(manager, member, exists, audit):
        return await _call_assign(company), audit


class TestAssignCompany:
    """AC4."""

    @pytest.mark.asyncio
    async def test_writes_the_company_and_audits_attempted_then_success(self):
        manager = _manager(doc={"metadata": {}})
        response, audit = await _assign(manager)
        manager.set_metadata_if_unset.assert_awaited_once_with("s1", "company_id", CO_A)
        assert _payload(response)["company_id"] == CO_A
        calls = audit.await_args_list
        assert [c.args[1] for c in calls] == ["attempted", "success"]
        assert calls[0].args[0] == "session.company_assign"
        assert all(c.kwargs["durable"] is True for c in calls)
        assert calls[0].kwargs["details"]["company_id"] == CO_A and calls[0].kwargs["resource"] == "s1"

    @pytest.mark.asyncio
    async def test_an_already_assigned_chat_is_refused_and_not_audited_as_changed(self):
        manager = _manager(doc={"metadata": {"company_id": CO_B}})
        with pytest.raises(HTTPException) as refused:
            await _assign(manager)
        assert refused.value.status_code == 409
        manager.set_metadata_if_unset.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_durable_attempted_record_means_no_change(self):
        manager = _manager(doc={"metadata": {}})
        with pytest.raises(HTTPException) as refused:
            await _assign(manager, audit=AsyncMock(return_value=False))
        assert refused.value.status_code == 503
        manager.set_metadata_if_unset.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_write_is_recorded_as_failed(self):
        manager = _manager(doc={"metadata": {}})
        manager.set_metadata_if_unset = AsyncMock(return_value=False)
        audit = AsyncMock(return_value=True)
        with pytest.raises(HTTPException) as refused:
            await _assign(manager, audit=audit)
        assert refused.value.status_code == 409  # a lost race: another assignment holds the company
        assert [c.args[1] for c in audit.await_args_list] == ["attempted", "failed"]
        assert audit.await_args_list[1].kwargs["details"]["reason"] == "already_assigned"

    @pytest.mark.asyncio
    async def test_a_company_the_caller_may_not_act_in_is_refused(self):
        manager = _manager(doc={"metadata": {}})
        with pytest.raises(HTTPException) as refused:
            await _assign(manager, member=False)
        assert refused.value.status_code == 403
        manager.set_metadata_if_unset.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_unknown_company_or_session_is_a_404(self):
        with pytest.raises(HTTPException) as no_company:
            await _assign(_manager(doc={"metadata": {}}), exists=False)
        with pytest.raises(HTTPException) as no_session:
            await _assign(_manager(doc=None))
        assert (no_company.value.status_code, no_session.value.status_code) == (404, 404)

    def test_the_route_is_owner_only_through_the_21898_gate(self):
        from api.chat_session_sharing import validate_session_owner

        route = next(
            r
            for r in chat_session_company.router.routes
            if getattr(r, "path", "").endswith("/sessions/{session_id}/company")
        )
        assert route.methods == {"POST"}
        assert validate_session_owner in [d.call for d in route.dependant.dependencies]

    def test_the_route_is_mounted_on_the_chat_router(self):
        """``include_router`` defers route copies here (#15093), so the mount is read from the source."""
        source = pathlib.Path(chat_sessions.__file__).read_text(encoding="utf-8")
        assert "router.include_router(_company.router)" in source


class TestNothingRetagsAChatOnItsOwn:
    """The owner decision: no migration, no agent and no startup hook assigns a company."""

    def test_the_backfill_has_no_caller(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        importers = []
        for path in root.rglob("*.py"):
            if path.name.startswith("session_scope_backfill") or path == pathlib.Path(__file__).resolve():
                continue
            if "session_scope_backfill" in path.read_text(encoding="utf-8", errors="ignore"):
                importers.append(str(path.relative_to(root)))
        assert importers == [], f"the backfill is wired into: {importers}"


class TestConcurrentAssignIsACompareAndSet:
    """The assign is one compare-and-set under the session lease: of two concurrent assigns exactly one wins."""

    @pytest.mark.asyncio
    async def test_two_concurrent_assigns_one_wins_the_other_is_409_and_the_winners_company_stands(self, tmp_path):
        from chat_history.session_lease_20862_test import _Manager

        manager = _Manager(str(tmp_path))
        await manager.save_session("s1", messages=[{"sender": "user", "text": "hi", "timestamp": "t0"}])
        audit = AsyncMock(return_value=True)
        with _assign_patches(manager, audit=audit):  # one patch lifetime around both calls
            outcomes = await asyncio.gather(_call_assign(CO_A), _call_assign(CO_B), return_exceptions=True)
        won = [o for o in outcomes if not isinstance(o, BaseException)]
        lost = [o for o in outcomes if isinstance(o, HTTPException)]
        assert len(won) == 1 and [e.status_code for e in lost] == [409]
        winner = _payload(won[0])["company_id"]
        assert await manager.get_session_company("s1") == winner
        results = sorted(c.args[1] for c in audit.await_args_list)
        assert results == ["attempted", "attempted", "failed", "success"]


def _socket(company: str | None = None):
    socket = MagicMock()
    socket.headers = {session_company.ACTIVE_COMPANY_HEADER: company} if company else {}
    socket.state = State()
    return socket


class TestWebSocketAppliesTheSameCompanyRule:
    """``owns_chat_session`` (the Overseer socket) refuses another company's chat exactly as HTTP does."""

    async def _owns(self, user, stored, company, durable_owner="alice"):
        from api import ws_security

        manager = MagicMock(get_session_company=AsyncMock(return_value=stored))
        with (
            patch.object(session_company, "may_act_in_company", new=AsyncMock(return_value=True)),
            patch("utils.chat_utils.get_chat_history_manager", return_value=manager),
            patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock()),
            patch("security.session_ownership.SessionOwnershipValidator") as validator,
        ):
            validator.return_value.get_session_owner = AsyncMock(return_value=durable_owner)
            return await ws_security.owns_chat_session(_socket(company), "s1", user)

    @pytest.mark.asyncio
    async def test_the_owner_of_a_chat_of_another_company_is_refused(self):
        assert await self._owns({"username": "alice", "role": "user"}, CO_B, CO_A) is False

    @pytest.mark.asyncio
    async def test_an_administrator_is_bound_by_the_active_company_too(self):
        assert await self._owns({"username": "root", "role": "admin"}, CO_B, CO_A) is False

    @pytest.mark.asyncio
    async def test_the_same_company_and_an_unassigned_chat_pass_for_the_owner(self):
        assert await self._owns({"username": "alice", "role": "user"}, CO_A, CO_A) is True
        assert await self._owns({"username": "alice", "role": "user"}, None, CO_A) is True

    @pytest.mark.asyncio
    async def test_no_active_company_changes_nothing(self):
        assert await self._owns({"username": "alice", "role": "user"}, CO_B, None) is True
        assert await self._owns({"username": "root", "role": "admin"}, CO_B, None) is True

    @pytest.mark.asyncio
    async def test_a_non_owner_is_still_refused_in_the_same_company(self):
        assert await self._owns({"username": "bob", "role": "user"}, CO_A, CO_A) is False


class TestNoActiveCompanyOpensATaggedChatById:
    """Hidden is not denied: a tagged chat is absent from the list with no active company, its owner opens it by id."""

    @pytest.mark.asyncio
    async def test_hidden_from_the_list_yet_open_by_id(self):
        data = _payload(await _list(None))
        assert "a1" not in _ids(data["sessions"]) | _ids(data["unassigned"])
        with patch(
            "utils.chat_utils.get_chat_history_manager", return_value=_manager(doc={"metadata": {"company_id": CO_A}})
        ):
            await session_company.enforce_session_company("a1", _request(None), dict(_USER))


class TestPerRequestCost:
    """One request resolves the active company once, and reads the stored company without the full session."""

    @pytest.mark.asyncio
    async def test_membership_is_checked_once_per_request(self):
        request = MagicMock()
        request.headers = {session_company.ACTIVE_COMPANY_HEADER: CO_A}
        request.state = State()
        member = AsyncMock(return_value=True)
        with (
            patch.object(session_company, "may_act_in_company", new=member),
            patch("utils.chat_utils.get_chat_history_manager", return_value=_manager()),
        ):
            await session_company.enforce_session_company("s", request, dict(_USER))
            await session_company.enforce_session_company("s", request, dict(_USER))
        assert member.await_count == 1

    @pytest.mark.asyncio
    async def test_the_stored_company_is_a_metadata_read(self):
        manager = _manager(doc={"metadata": {"company_id": CO_A}})
        with patch("utils.chat_utils.get_chat_history_manager", return_value=manager):
            assert await session_company.company_of_session(_request(CO_A), "s") == CO_A
        manager.get_session_company.assert_awaited_once_with("s")
        manager.get_session.assert_not_awaited()
