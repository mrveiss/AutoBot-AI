# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The REST presence read enforces the VIEWER level it documents (#16580).

``get_presence`` said *"Requires: VIEWER permission"* in its docstring and
depended on ``get_current_user`` alone, so any signed-in user could list the
online users of any session id. Every sibling in the module checks — OWNER for
invite and remove, EDITOR for secret sharing, VIEWER for participants. #16455
closed the same gap on the WebSocket route; this is the REST read.

These tests drive the real ``_ensure_permission`` by patching
``_get_session_collab`` beneath it, rather than patching the gate itself: a test
that mocks the check it is verifying passes whether or not the handler calls it.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.collaboration import get_participants, get_presence
from models.session_collaboration import PermissionLevel, SessionCollaboration

SESSION_ID = "chat-1234567890-abcd1234"
ONLINE = ["user-a", "user-b"]


@pytest.fixture
def mock_db():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def owner_id():
    return uuid.uuid4()


@pytest.fixture
def collab(owner_id):
    return SessionCollaboration(session_id=SESSION_ID, owner_id=owner_id)


def _as_user(user_id: uuid.UUID) -> dict:
    return {"user_id": str(user_id)}


def _presence_returning(users):
    manager = MagicMock()
    manager.get_online_users = AsyncMock(return_value=users)
    return patch("websocket.presence.presence_manager", manager)


class TestTheGateIsClosed:
    @pytest.mark.asyncio
    async def test_a_user_with_no_collaboration_is_refused(self, mock_db, collab) -> None:
        stranger = _as_user(uuid.uuid4())
        with patch("api.collaboration._get_session_collab", AsyncMock(return_value=collab)):
            with pytest.raises(HTTPException) as caught:
                await get_presence(SESSION_ID, mock_db, stranger)
        assert caught.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_the_refusal_is_the_one_get_participants_gives(self, mock_db, collab) -> None:
        """The issue's wording: the same refusal, not merely some refusal."""
        stranger = _as_user(uuid.uuid4())
        with patch("api.collaboration._get_session_collab", AsyncMock(return_value=collab)):
            with pytest.raises(HTTPException) as presence:
                await get_presence(SESSION_ID, mock_db, stranger)
            with pytest.raises(HTTPException) as participants:
                await get_participants(SESSION_ID, mock_db, stranger)
        assert presence.value.status_code == participants.value.status_code
        assert presence.value.detail == participants.value.detail

    @pytest.mark.asyncio
    async def test_a_refusal_is_not_reported_as_a_server_error(self, mock_db, collab) -> None:
        """The handler's `except Exception` would swallow the 403 into a 500.

        HTTPException IS an Exception, so without the `except HTTPException:
        raise` clause the gate looks closed while every refusal arrives as a
        server error — indistinguishable, to a caller, from the endpoint being
        broken. Deleting that clause turns this red.
        """
        stranger = _as_user(uuid.uuid4())
        with patch("api.collaboration._get_session_collab", AsyncMock(return_value=collab)):
            with pytest.raises(HTTPException) as caught:
                await get_presence(SESSION_ID, mock_db, stranger)
        assert caught.value.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_an_unknown_session_is_a_404_not_a_500(self, mock_db) -> None:
        with patch("api.collaboration._get_session_collab", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as caught:
                await get_presence(SESSION_ID, mock_db, _as_user(uuid.uuid4()))
        assert caught.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_a_malformed_user_id_is_a_400(self, mock_db) -> None:
        with pytest.raises(HTTPException) as caught:
            await get_presence(SESSION_ID, mock_db, {"user_id": "not-a-uuid"})
        assert caught.value.status_code == status.HTTP_400_BAD_REQUEST


class TestTheGateStillLetsTheRightPeopleThrough:
    """A check that refuses everyone is not a fix."""

    @pytest.mark.asyncio
    async def test_a_viewer_gets_the_presence_list(self, mock_db, collab) -> None:
        viewer_id = uuid.uuid4()
        collab.add_collaborator(viewer_id, PermissionLevel.VIEWER)
        with patch("api.collaboration._get_session_collab", AsyncMock(return_value=collab)):
            with _presence_returning(ONLINE):
                response = await get_presence(SESSION_ID, mock_db, _as_user(viewer_id))
        assert response["online_users"] == ONLINE
        assert response["count"] == len(ONLINE)
        assert response["session_id"] == SESSION_ID

    @pytest.mark.asyncio
    async def test_the_owner_gets_the_presence_list(self, mock_db, collab, owner_id) -> None:
        with patch("api.collaboration._get_session_collab", AsyncMock(return_value=collab)):
            with _presence_returning([]):
                response = await get_presence(SESSION_ID, mock_db, _as_user(owner_id))
        assert response["online_users"] == []
        assert response["count"] == 0
