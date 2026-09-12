# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the collaboration event history and invitation list/respond
endpoints (#16460). Split from api/collaboration_test.py to keep both
files under the per-file line-count guard (#5060).
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status

from api.collaboration_events import (
    InvitationRespondRequest,
    get_session_events,
    list_my_invitations,
    respond_to_invitation,
)
from models.collaboration_event import CollaborationEvent
from models.session_collaboration import PermissionLevel, SessionCollaboration


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def session_id():
    """Test session ID."""
    return "chat-1234567890-abcd1234"


@pytest.fixture
def owner_id():
    """Test owner UUID."""
    return uuid.uuid4()


@pytest.fixture
def collaborator_id():
    """Test collaborator UUID."""
    return uuid.uuid4()


@pytest.fixture
def current_user_owner(owner_id):
    """Mock current user as owner."""
    return {"user_id": str(owner_id)}


@pytest.fixture
def current_user_editor(collaborator_id):
    """Mock current user as editor."""
    return {"user_id": str(collaborator_id)}


# ====================================================================
# Session Events Endpoint Tests
# ====================================================================


@pytest.mark.asyncio
async def test_get_session_events_success(mock_db, session_id, owner_id, current_user_owner):
    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)
    event = CollaborationEvent(
        id=uuid.uuid4(),
        session_id=session_id,
        kind="activity",
        user_id=owner_id,
        username="owner",
        payload={"type": "terminal", "content": "ls"},
    )
    event.timestamp = datetime.now(timezone.utc)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [event]
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("api.collaboration_events._ensure_permission", return_value=collab):
        response = await get_session_events(session_id, 50, None, mock_db, current_user_owner)

    assert response.session_id == session_id
    assert response.has_more is False
    assert len(response.events) == 1
    assert response.events[0].kind == "activity"


@pytest.mark.asyncio
async def test_get_session_events_requires_viewer_permission(mock_db, session_id, current_user_editor):
    with patch(
        "api.collaboration_events._ensure_permission",
        side_effect=HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_session_events(session_id, 50, None, mock_db, current_user_editor)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


# ====================================================================
# Invitation List/Respond Endpoint Tests
# ====================================================================


@pytest.mark.asyncio
async def test_list_my_invitations_finds_invitation_across_sessions(
    mock_db, owner_id, collaborator_id, current_user_editor
):
    collab_with_invite = SessionCollaboration(session_id="chat-with-invite", owner_id=owner_id)
    collab_with_invite.add_invitation(collaborator_id, PermissionLevel.EDITOR)
    collab_without_invite = SessionCollaboration(session_id="chat-without-invite", owner_id=owner_id)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [collab_with_invite, collab_without_invite]
    mock_db.execute = AsyncMock(return_value=mock_result)

    response = await list_my_invitations(mock_db, current_user_editor)

    assert len(response.invitations) == 1
    assert response.invitations[0].session_id == "chat-with-invite"
    assert response.invitations[0].from_user_id == str(owner_id)
    assert response.invitations[0].permission == PermissionLevel.EDITOR.value


@pytest.mark.asyncio
async def test_respond_to_invitation_accept_adds_collaborator(
    mock_db, session_id, owner_id, collaborator_id, current_user_editor
):
    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)
    collab.add_invitation(collaborator_id, PermissionLevel.EDITOR)

    with patch("api.collaboration_events._get_session_collab", return_value=collab):
        response = await respond_to_invitation(
            session_id, InvitationRespondRequest(accept=True), mock_db, current_user_editor
        )

    assert response.accepted is True
    assert response.permission == PermissionLevel.EDITOR.value
    assert collab.get_permission(collaborator_id) == PermissionLevel.EDITOR.value
    assert collab.invitations == []
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_respond_to_invitation_decline_does_not_add_collaborator(
    mock_db, session_id, owner_id, collaborator_id, current_user_editor
):
    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)
    collab.add_invitation(collaborator_id, PermissionLevel.VIEWER)

    with patch("api.collaboration_events._get_session_collab", return_value=collab):
        response = await respond_to_invitation(
            session_id, InvitationRespondRequest(accept=False), mock_db, current_user_editor
        )

    assert response.accepted is False
    assert response.permission is None
    assert collab.get_permission(collaborator_id) is None
    assert collab.invitations == []


@pytest.mark.asyncio
async def test_respond_to_invitation_no_matching_invitation_404s(mock_db, session_id, owner_id, current_user_editor):
    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)

    with patch("api.collaboration_events._get_session_collab", return_value=collab):
        with pytest.raises(HTTPException) as exc_info:
            await respond_to_invitation(session_id, InvitationRespondRequest(accept=True), mock_db, current_user_editor)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
