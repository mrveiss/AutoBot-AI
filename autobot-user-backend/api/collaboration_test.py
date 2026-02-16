# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Session Collaboration API

Part of Issue #872 - Session Collaboration API (#608 Phase 3).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.collaboration import (
    InviteRequest,
    RemoveRequest,
    ShareSecretRequest,
    _ensure_permission,
    _get_or_create_collab,
    _get_session_collab,
    get_participants,
    invite_user,
    remove_collaborator,
    share_secret_with_session,
)
from backend.models.secret import Secret, SecretScope, SecretType
from backend.models.session_collaboration import PermissionLevel, SessionCollaboration


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
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
# Helper Function Tests
# ====================================================================


@pytest.mark.asyncio
async def test_get_session_collab_found(mock_db, session_id, owner_id):
    """Test getting existing collaboration record."""
    # Arrange
    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = collab
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Act
    result = await _get_session_collab(session_id, mock_db)

    # Assert
    assert result == collab
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_session_collab_not_found(mock_db, session_id):
    """Test getting non-existent collaboration record."""
    # Arrange
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Act
    result = await _get_session_collab(session_id, mock_db)

    # Assert
    assert result is None


@pytest.mark.asyncio
async def test_ensure_permission_success(mock_db, session_id, owner_id):
    """Test permission check with sufficient permission."""
    # Arrange
    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)

    with patch("api.collaboration._get_session_collab", return_value=collab):
        # Act
        result = await _ensure_permission(
            session_id, owner_id, PermissionLevel.OWNER, mock_db
        )

        # Assert
        assert result == collab


@pytest.mark.asyncio
async def test_ensure_permission_not_found(mock_db, session_id, owner_id):
    """Test permission check for non-existent session."""
    # Arrange
    with patch("api.collaboration._get_session_collab", return_value=None):
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await _ensure_permission(
                session_id, owner_id, PermissionLevel.OWNER, mock_db
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_ensure_permission_insufficient(
    mock_db, session_id, owner_id, collaborator_id
):
    """Test permission check with insufficient permission."""
    # Arrange
    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)
    collab.add_collaborator(collaborator_id, PermissionLevel.VIEWER)

    with patch("api.collaboration._get_session_collab", return_value=collab):
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await _ensure_permission(
                session_id,
                collaborator_id,
                PermissionLevel.OWNER,
                mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_or_create_collab_existing(mock_db, session_id, owner_id):
    """Test getting existing collaboration record."""
    # Arrange
    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)

    with patch("api.collaboration._get_session_collab", return_value=collab):
        # Act
        result = await _get_or_create_collab(session_id, owner_id, mock_db)

        # Assert
        assert result == collab
        mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_collab_new(mock_db, session_id, owner_id):
    """Test creating new collaboration record."""
    # Arrange
    with patch("api.collaboration._get_session_collab", return_value=None):
        # Act
        result = await _get_or_create_collab(session_id, owner_id, mock_db)

        # Assert
        assert result.session_id == session_id
        assert result.owner_id == owner_id
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


# ====================================================================
# Invite User Endpoint Tests
# ====================================================================


@pytest.mark.asyncio
async def test_invite_user_success(
    mock_db, session_id, owner_id, collaborator_id, current_user_owner
):
    """Test successfully inviting user."""
    # Arrange
    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)
    invite = InviteRequest(
        user_id=str(collaborator_id), permission=PermissionLevel.EDITOR
    )

    with patch("api.collaboration._ensure_permission", return_value=collab):
        # Act
        response = await invite_user(session_id, invite, mock_db, current_user_owner)

        # Assert
        assert response.success is True
        assert response.session_id == session_id
        assert response.invited_user_id == str(collaborator_id)
        assert response.permission == PermissionLevel.EDITOR.value
        mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_invite_user_invalid_uuid(mock_db, session_id, current_user_owner):
    """Test inviting user with invalid UUID."""
    # Arrange
    invite = InviteRequest(user_id="invalid-uuid", permission=PermissionLevel.EDITOR)

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await invite_user(session_id, invite, mock_db, current_user_owner)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


# ====================================================================
# Remove Collaborator Endpoint Tests
# ====================================================================


@pytest.mark.asyncio
async def test_remove_collaborator_success(
    mock_db, session_id, owner_id, collaborator_id, current_user_owner
):
    """Test successfully removing collaborator."""
    # Arrange
    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)
    collab.add_collaborator(collaborator_id, PermissionLevel.EDITOR)

    remove = RemoveRequest(user_id=str(collaborator_id))

    with patch("api.collaboration._ensure_permission", return_value=collab):
        # Act
        response = await remove_collaborator(
            session_id, remove, mock_db, current_user_owner
        )

        # Assert
        assert response.success is True
        assert response.session_id == session_id
        assert response.removed_user_id == str(collaborator_id)
        mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_remove_collaborator_cannot_remove_owner(
    mock_db, session_id, owner_id, current_user_owner
):
    """Test cannot remove session owner."""
    # Arrange
    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)
    remove = RemoveRequest(user_id=str(owner_id))

    with patch("api.collaboration._ensure_permission", return_value=collab):
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await remove_collaborator(session_id, remove, mock_db, current_user_owner)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Cannot remove session owner" in exc_info.value.detail


@pytest.mark.asyncio
async def test_remove_collaborator_not_found(
    mock_db, session_id, owner_id, current_user_owner
):
    """Test removing non-existent collaborator."""
    # Arrange
    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)
    remove = RemoveRequest(user_id=str(uuid.uuid4()))

    with patch("api.collaboration._ensure_permission", return_value=collab):
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await remove_collaborator(session_id, remove, mock_db, current_user_owner)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ====================================================================
# Get Participants Endpoint Tests
# ====================================================================


@pytest.mark.asyncio
async def test_get_participants_success(
    mock_db, session_id, owner_id, collaborator_id, current_user_owner
):
    """Test getting participants list."""
    # Arrange
    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)
    collab.add_collaborator(collaborator_id, PermissionLevel.EDITOR)

    with patch("api.collaboration._ensure_permission", return_value=collab):
        # Act
        response = await get_participants(session_id, mock_db, current_user_owner)

        # Assert
        assert response.session_id == session_id
        assert response.owner_id == str(owner_id)
        assert response.total_count == 2
        assert len(response.participants) == 2


# ====================================================================
# Share Secret Endpoint Tests
# ====================================================================


@pytest.mark.asyncio
async def test_share_secret_with_all_editors(
    mock_db, session_id, owner_id, collaborator_id, current_user_owner
):
    """Test sharing secret with all editors."""
    # Arrange
    secret_id = uuid.uuid4()
    secret = Secret(
        id=secret_id,
        owner_id=owner_id,
        name="test-secret",
        type=SecretType.API_KEY.value,
        scope=SecretScope.USER.value,
        encrypted_value="encrypted-data",
    )

    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)
    collab.add_collaborator(collaborator_id, PermissionLevel.EDITOR)

    share = ShareSecretRequest(secret_id=str(secret_id))

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = secret
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("api.collaboration._ensure_permission", return_value=collab):
        # Act
        response = await share_secret_with_session(
            session_id, share, mock_db, current_user_owner
        )

        # Assert
        assert response["success"] is True
        assert response["shared_with_count"] == 1
        mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_share_secret_not_owner(
    mock_db, session_id, owner_id, collaborator_id, current_user_editor
):
    """Test sharing secret user doesn't own."""
    # Arrange
    secret_id = uuid.uuid4()
    secret = Secret(
        id=secret_id,
        owner_id=owner_id,  # Different owner
        name="test-secret",
        type=SecretType.API_KEY.value,
        scope=SecretScope.USER.value,
        encrypted_value="encrypted-data",
    )

    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)
    collab.add_collaborator(collaborator_id, PermissionLevel.EDITOR)

    share = ShareSecretRequest(secret_id=str(secret_id))

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = secret
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("api.collaboration._ensure_permission", return_value=collab):
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await share_secret_with_session(
                session_id, share, mock_db, current_user_editor
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "only share secrets you own" in exc_info.value.detail


@pytest.mark.asyncio
async def test_share_secret_not_found(
    mock_db, session_id, owner_id, current_user_owner
):
    """Test sharing non-existent secret."""
    # Arrange
    secret_id = uuid.uuid4()
    collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)

    share = ShareSecretRequest(secret_id=str(secret_id))

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("api.collaboration._ensure_permission", return_value=collab):
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await share_secret_with_session(
                session_id, share, mock_db, current_user_owner
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
