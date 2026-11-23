# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every path that reaches a chat by id applies the one company rule (#21997): other company refused, same passes.

Covers the live-event channels, the ``/ws`` broadcast filter, the presence socket, the share-link, collaboration
and chat-knowledge routers, streaming attachments and the import of one's own existing chat. The HTTP dependency
chain and the WebSocket owner check are in ``chat_company_scope_21997_test.py``.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import (
    chat_knowledge,
    chat_shared_links,
    collaboration,
    collaboration_events,
    live_events,
    presence_ws,
    websockets,
)
from api.chat_streaming import attachments_allowed
from chat_history.company_scope import ActiveCompany
from security import session_company
from security.session_company import ACTIVE_COMPANY_KEY, require_session_company, session_in_company
from security.session_owner_errors import SessionOwnerUnreadable
from security.session_posture import UNREADABLE_OWNER_DETAIL

CO_A, CO_B = str(uuid.uuid4()), str(uuid.uuid4())
_SID = "chat_" + "a" * 32


def _manager(stored=None, owner="alice"):
    return MagicMock(
        get_session_company=AsyncMock(return_value=stored), get_session_owner=AsyncMock(return_value=owner)
    )


class TestLiveEventChannels:
    """``session:`` / ``chat:`` subscriptions: the company first, an administrator bound by it too."""

    async def _allowed(self, user, stored, active, channel="session:s1"):
        payload = {**user, ACTIVE_COMPANY_KEY: active}
        with patch("utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager") as factory:
            factory.return_value = _manager(stored)
            return await live_events._authorize_conversation_channel(channel, payload)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("channel", ["session:s1", "chat:s1"])
    async def test_the_owner_of_another_companys_chat_is_refused(self, channel):
        assert await self._allowed({"username": "alice", "role": "user"}, CO_B, CO_A, channel) is False

    @pytest.mark.asyncio
    async def test_the_owner_of_a_chat_in_the_active_company_or_unassigned_passes(self):
        user = {"username": "alice", "role": "user"}
        assert await self._allowed(user, CO_A, CO_A) is True
        assert await self._allowed(user, None, CO_A) is True

    @pytest.mark.asyncio
    async def test_an_administrator_is_bound_by_the_active_company(self):
        assert await self._allowed({"username": "root", "role": "admin"}, CO_B, CO_A) is False
        assert await self._allowed({"username": "root", "role": "admin"}, CO_A, CO_A) is True

    @pytest.mark.asyncio
    async def test_no_active_company_keeps_the_admin_bypass_and_the_owner_check(self):
        assert await self._allowed({"username": "root", "role": "admin"}, CO_B, None) is True
        assert await self._allowed({"username": "alice", "role": "user"}, CO_B, None) is True
        assert await self._allowed({"username": "bob", "role": "user"}, CO_B, None) is False

    @pytest.mark.asyncio
    async def test_an_unreadable_company_denies(self):
        payload = {"username": "alice", "role": "user", ACTIVE_COMPANY_KEY: CO_A}
        manager = MagicMock(get_session_company=AsyncMock(side_effect=SessionOwnerUnreadable("s1")))
        with patch("utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager", return_value=manager):
            assert await live_events._authorize_conversation_channel("session:s1", payload) is False


class TestBroadcastFilter:
    """``/ws`` events: a chat in another company than the subscriber's active one is not delivered."""

    async def _delivered(self, stored, company, owner="alice"):
        event = {"type": "message", "payload": {"session_id": "s1", "text": "x"}}
        with patch("utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager") as factory:
            factory.return_value = _manager(stored, owner)
            return await websockets._event_is_for_user(event, "alice", {}, company)

    @pytest.mark.asyncio
    async def test_another_company_is_withheld_the_same_company_and_unassigned_delivered(self):
        assert await self._delivered(CO_B, ActiveCompany(CO_A)) is False
        assert await self._delivered(CO_A, ActiveCompany(CO_A)) is True
        assert await self._delivered(None, ActiveCompany(CO_A)) is True

    @pytest.mark.asyncio
    async def test_no_active_company_changes_nothing(self):
        assert await self._delivered(CO_B, ActiveCompany(None)) is True
        assert await self._delivered(CO_B, None) is True

    @pytest.mark.asyncio
    async def test_the_owner_rule_still_applies_first(self):
        assert await self._delivered(CO_A, ActiveCompany(CO_A), owner="bob") is False


class TestConnectionScope:
    @pytest.mark.asyncio
    async def test_a_header_naming_a_company_the_caller_may_not_act_in_closes_4403(self):
        socket = MagicMock(headers={session_company.ACTIVE_COMPANY_HEADER: CO_A}, close=AsyncMock())
        user = {"username": "alice", "user_id": str(uuid.uuid4()), "role": "user"}
        with (
            patch.object(session_company, "may_act_in_company", new=AsyncMock(return_value=False)),
            patch("autobot_shared.websocket_subprotocol.accept_websocket", new=AsyncMock()),
        ):
            assert await session_company.connection_company(socket, user) is None
        socket.close.assert_awaited_once_with(code=4403, reason="Forbidden")

    @pytest.mark.asyncio
    async def test_a_member_gets_the_scope(self):
        socket = MagicMock(headers={session_company.ACTIVE_COMPANY_HEADER: CO_A})
        user = {"username": "alice", "user_id": str(uuid.uuid4()), "role": "user"}
        with patch.object(session_company, "may_act_in_company", new=AsyncMock(return_value=True)):
            assert (await session_company.connection_company(socket, user)).active == CO_A

    @pytest.mark.asyncio
    async def test_session_in_company_is_the_one_rule_as_a_yes_no(self):
        assert await session_in_company(_manager(CO_B), "s", ActiveCompany(CO_A)) is False
        assert await session_in_company(_manager(CO_A), "s", ActiveCompany(CO_A)) is True
        assert await session_in_company(_manager(CO_B), "s", ActiveCompany(None)) is True


class TestPresenceSocket:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("allowed,closed", [(False, True), (True, False)])
    async def test_another_companys_session_is_closed_the_same_company_joins(self, allowed, closed):
        socket = MagicMock(close=AsyncMock())
        handler = AsyncMock()
        user = {"user_id": str(uuid.uuid4()), "username": "alice"}
        with (
            patch.object(presence_ws, "enforce_ws_origin", new=AsyncMock(return_value=True)),
            patch.object(presence_ws, "authenticate_websocket", new=AsyncMock(return_value=user)),
            patch.object(presence_ws, "_authorized_participant", new=AsyncMock(return_value=True)),
            patch.object(presence_ws, "in_active_company", new=AsyncMock(return_value=allowed)),
            patch.object(presence_ws, "accept_websocket", new=AsyncMock()),
            patch.object(presence_ws, "presence_websocket_handler", new=handler),
        ):
            await presence_ws.session_presence(socket, _SID)
        assert socket.close.await_count == int(closed)
        assert handler.await_count == int(not closed)


class TestRouterDependency:
    """Share-link owner routes, collaboration and chat-knowledge name a chat in their path: one dependency each."""

    @pytest.mark.parametrize("module", [chat_shared_links, collaboration, collaboration_events, chat_knowledge])
    def test_the_router_carries_the_company_dependency(self, module):
        assert require_session_company in [d.dependency for d in module.router.dependencies]

    @pytest.mark.asyncio
    async def test_a_chat_named_in_the_path_is_enforced_and_a_path_without_one_is_not(self):
        enforce = AsyncMock(side_effect=HTTPException(status_code=403, detail="Forbidden"))
        with patch.object(session_company, "enforce_session_company", new=enforce):
            with pytest.raises(HTTPException) as refused:
                await require_session_company(MagicMock(path_params={"session_id": _SID}))
            await require_session_company(MagicMock(path_params={"token": "t"}))
            await require_session_company(
                MagicMock(path_params={"session_id": "../etc"})
            )  # not a chat id: left to its route
        assert refused.value.status_code == 403
        enforce.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_dependency_refuses_another_company_and_passes_the_same_one(self):
        user = {"username": "alice", "user_id": str(uuid.uuid4()), "role": "user"}
        conn = MagicMock(path_params={"chat_id": _SID}, headers={session_company.ACTIVE_COMPANY_HEADER: CO_A})
        conn.state = None
        for stored, refused in ((CO_B, True), (CO_A, False), (None, False)):
            with (
                patch.object(session_company, "may_act_in_company", new=AsyncMock(return_value=True)),
                patch.object(session_company, "company_of_session", new=AsyncMock(return_value=stored)),
                patch.object(session_company, "_caller", return_value=user),
            ):
                if refused:
                    with pytest.raises(HTTPException):
                        await require_session_company(conn)
                else:
                    await require_session_company(conn)


class TestStreamingAttachments:
    @pytest.mark.asyncio
    async def test_another_companys_chat_reads_no_attachments_the_same_company_does(self):
        user = {"username": "alice", "role": "user"}
        refuse = AsyncMock(side_effect=HTTPException(status_code=403, detail="Forbidden"))
        with patch("security.session_company.enforce_session_company", new=refuse):
            assert await attachments_allowed("c1", user, MagicMock()) is False
        with (
            patch("security.session_company.enforce_session_company", new=AsyncMock()),
            patch("security.session_posture.validate_strict", new=AsyncMock(return_value={"reason": "owner_match"})),
        ):
            assert await attachments_allowed("c1", user, MagicMock()) is True


class TestImportOntoOwnChat:
    @pytest.mark.asyncio
    async def test_an_unreadable_company_fails_closed_like_an_unreadable_owner(self):
        from services import conversation_export

        manager = AsyncMock()
        manager.get_session_company = AsyncMock(side_effect=SessionOwnerUnreadable("s"))
        with pytest.raises(HTTPException) as denied:
            await conversation_export._refuse_other_company(manager, "s", {"company_id": CO_A})
        assert (denied.value.status_code, denied.value.detail) == (403, UNREADABLE_OWNER_DETAIL)


class TestReviewFixes:
    """The CodeRabbit findings on #22013: each pinned at the route or dependency it concerned."""

    @pytest.mark.asyncio
    async def test_chat_init_answers_a_refused_company_with_its_403_not_a_500(self):
        from api import batch_jobs

        refuse = AsyncMock(side_effect=HTTPException(status_code=403, detail="Forbidden"))
        with patch.object(batch_jobs, "resolve_company_scope", new=refuse):
            with pytest.raises(HTTPException) as refused:
                await batch_jobs.batch_chat_initialization(MagicMock(), current_user={"username": "alice"})
        assert refused.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_create_retry_over_the_callers_own_chat_does_not_stamp_a_company(self):
        from api import chat_sessions
        from api.schemas_chat import SessionCreate

        for is_retry, stamped in ((True, False), (False, True)):
            manager = MagicMock(create_session=AsyncMock(return_value={"id": _SID}))
            stamp = AsyncMock(return_value={"company_id": CO_B})
            with (
                patch.object(chat_sessions, "get_chat_history_manager", return_value=manager),
                patch.object(chat_sessions, "resolve_human_user", new=AsyncMock(return_value={"username": "alice"})),
                patch.object(chat_sessions, "_reject_session_id_collision", new=AsyncMock(return_value=is_retry)),
                patch.object(chat_sessions, "creation_company_metadata", new=stamp),
                patch.object(chat_sessions, "_register_session_ownership", new=AsyncMock()),
                patch.object(chat_sessions, "_track_session_in_memory_graph", new=AsyncMock()),
                patch.object(chat_sessions, "_emit_session_create", new=AsyncMock()),
                patch.object(chat_sessions, "publish_session_created", new=AsyncMock()),
                patch.object(chat_sessions, "audit_record"),
                patch.object(chat_sessions, "log_chat_event"),
                patch.object(chat_sessions, "log_request_context"),
            ):
                await chat_sessions.create_session(SessionCreate(id=_SID), MagicMock())
            sent = manager.create_session.await_args.kwargs["metadata"]
            assert ("company_id" in sent) is stamped

    @pytest.mark.asyncio
    async def test_the_collision_check_reports_the_callers_own_retry(self):
        from api import chat_sessions

        own = MagicMock(get_session=AsyncMock(return_value={"metadata": {"owner": "alice"}}))
        new = MagicMock(get_session=AsyncMock(return_value=None))
        with patch.object(chat_sessions, "legacy_transcript_file", return_value=None):
            assert await chat_sessions._reject_session_id_collision(own, _SID, {"username": "alice"}) is True
            assert await chat_sessions._reject_session_id_collision(new, _SID, {"username": "alice"}) is False

    @pytest.mark.asyncio
    async def test_a_hidden_route_answers_another_companys_chat_as_not_found(self):
        from security import session_posture
        from security.session_company import OtherCompanyRefusal

        with patch.object(session_posture, "authenticated_user", new=AsyncMock(side_effect=OtherCompanyRefusal())):
            with pytest.raises(HTTPException) as refused:
                await session_posture.validate_strict_hidden(_SID, MagicMock())
        assert (refused.value.status_code, refused.value.detail) == (404, session_posture.SESSION_NOT_FOUND_DETAIL)

    @pytest.mark.asyncio
    async def test_the_overseer_socket_rechecks_the_company_on_every_message(self):
        from api import overseer_handlers

        socket = MagicMock(receive_json=AsyncMock(return_value={"type": "query"}), close=AsyncMock())
        handler = MagicMock(connect=AsyncMock(return_value=True), handle_message=AsyncMock(), disconnect=AsyncMock())
        with (
            patch.object(overseer_handlers, "open_authenticated_ws", new=AsyncMock(return_value=True)),
            patch.object(overseer_handlers, "OverseerWebSocketHandler", return_value=handler),
            patch.object(overseer_handlers, "in_active_company", new=AsyncMock(return_value=False)),
        ):
            await overseer_handlers.overseer_websocket(socket, _SID)
        handler.handle_message.assert_not_awaited()
        socket.close.assert_awaited_once_with(code=1008, reason="Forbidden")

    @pytest.mark.asyncio
    async def test_the_overseer_socket_keeps_serving_while_the_chat_stays_in_its_company(self):
        from api import overseer_handlers

        socket = MagicMock(receive_json=AsyncMock(side_effect=[{"type": "status"}, RuntimeError("stop")]))
        handler = MagicMock(connect=AsyncMock(return_value=True), handle_message=AsyncMock(), disconnect=AsyncMock())
        with (
            patch.object(overseer_handlers, "open_authenticated_ws", new=AsyncMock(return_value=True)),
            patch.object(overseer_handlers, "OverseerWebSocketHandler", return_value=handler),
            patch.object(overseer_handlers, "in_active_company", new=AsyncMock(return_value=True)),
        ):
            await overseer_handlers.overseer_websocket(socket, _SID)
        handler.handle_message.assert_awaited_once()
