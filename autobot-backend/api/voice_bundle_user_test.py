# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for user voice bundle endpoints (GH#8605)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# GET /voice/bundles — list available bundles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_bundles_user_role():
    """User can list bundles filtered for their role."""
    from api.voice_bundle_user import list_voice_bundles

    mock_tools_safe = ["tool1", "tool2"]
    mock_tools_extended = ["tool1", "tool2", "tool3", "tool4"]

    async def mock_count(bundle: str, is_admin: bool) -> int:
        if bundle == "voice_safe":
            return len(mock_tools_safe)
        elif bundle == "voice_extended":
            return len(mock_tools_extended)
        elif bundle == "voice_admin":
            return 0 if not is_admin else 10
        return 0

    current_user = {"user_id": "user-123", "role": "user"}

    with patch("api.voice_bundle_user._count_tools_for_bundle", side_effect=mock_count):
        bundles = await list_voice_bundles(current_user)

    assert len(bundles) == 3
    assert any(b.name == "voice_safe" for b in bundles)
    assert any(b.name == "voice_extended" for b in bundles)
    assert any(b.name == "voice_admin" for b in bundles)


@pytest.mark.asyncio
async def test_list_bundles_admin_role():
    """Admin can list all bundles."""
    from api.voice_bundle_user import list_voice_bundles

    async def mock_count(bundle: str, is_admin: bool) -> int:
        return {"voice_safe": 2, "voice_extended": 4, "voice_admin": 10}.get(bundle, 0)

    current_user = {"user_id": "admin-1", "role": "admin"}

    with patch("api.voice_bundle_user._count_tools_for_bundle", side_effect=mock_count):
        bundles = await list_voice_bundles(current_user)

    assert len(bundles) == 3
    admin_bundle = next(b for b in bundles if b.name == "voice_admin")
    assert admin_bundle.tool_count == 10


# ---------------------------------------------------------------------------
# GET /voice/users/{userId}/bundle — get user's bundle assignment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_own_bundle():
    """User can view their own bundle assignment."""
    from api.voice_bundle_user import get_user_bundle

    user_id = "user-123"
    current_user = {"user_id": user_id, "role": "user"}
    mock_request = MagicMock()

    mock_row = MagicMock()
    mock_row.fetchone.return_value = ("voice_extended",)
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_row)

    with patch("user_management.database.get_async_session", return_value=mock_session):
        result = await get_user_bundle(user_id, mock_request, current_user)

    assert result.user_id == user_id
    assert result.bundle_name == "voice_extended"


@pytest.mark.asyncio
async def test_admin_can_view_other_user_bundle():
    """Admin can view any user's bundle assignment."""
    from api.voice_bundle_user import get_user_bundle

    target_user_id = "other-user"
    current_user = {"user_id": "admin-1", "role": "admin"}
    mock_request = MagicMock()

    mock_row = MagicMock()
    mock_row.fetchone.return_value = ("voice_safe",)
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_row)

    with patch("user_management.database.get_async_session", return_value=mock_session):
        result = await get_user_bundle(target_user_id, mock_request, current_user)

    assert result.user_id == target_user_id
    assert result.bundle_name == "voice_safe"


@pytest.mark.asyncio
async def test_user_cannot_view_other_user_bundle():
    """User cannot view other user's bundle assignment."""
    from fastapi import HTTPException

    from api.voice_bundle_user import get_user_bundle

    target_user_id = "other-user"
    current_user = {"user_id": "user-123", "role": "user"}
    mock_request = MagicMock()

    with pytest.raises(HTTPException):
        await get_user_bundle(target_user_id, mock_request, current_user)


@pytest.mark.asyncio
async def test_get_bundle_no_assignment():
    """Return None when user has no explicit assignment."""
    from api.voice_bundle_user import get_user_bundle

    user_id = "user-123"
    current_user = {"user_id": user_id, "role": "user"}
    mock_request = MagicMock()

    mock_row = MagicMock()
    mock_row.fetchone.return_value = None
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_row)

    with patch("user_management.database.get_async_session", return_value=mock_session):
        result = await get_user_bundle(user_id, mock_request, current_user)

    assert result.user_id == user_id
    assert result.bundle_name is None


# ---------------------------------------------------------------------------
# PUT /voice/users/{userId}/bundle — assign bundle to user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_can_assign_own_bundle():
    """User can assign bundle to themselves."""
    from api.voice_bundle_user import set_user_bundle, BundleAssignRequest

    user_id = "user-123"
    current_user = {"user_id": user_id, "role": "user"}
    mock_request = MagicMock()
    body = BundleAssignRequest(bundle_name="voice_extended")

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("user_management.database.get_async_session", return_value=mock_session):
        with patch("services.event_log.emit"):
            result = await set_user_bundle(user_id, body, mock_request, current_user)

    assert result.user_id == user_id
    assert result.bundle_name == "voice_extended"
    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_admin_can_assign_bundle_to_other_user():
    """Admin can assign bundle to any user."""
    from api.voice_bundle_user import set_user_bundle, BundleAssignRequest

    target_user_id = "other-user"
    current_user = {"user_id": "admin-1", "role": "admin"}
    mock_request = MagicMock()
    body = BundleAssignRequest(bundle_name="voice_safe")

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("user_management.database.get_async_session", return_value=mock_session):
        with patch("services.event_log.emit"):
            result = await set_user_bundle(target_user_id, body, mock_request, current_user)

    assert result.user_id == target_user_id
    assert result.bundle_name == "voice_safe"


@pytest.mark.asyncio
async def test_user_cannot_assign_bundle_to_other_user():
    """User cannot assign bundle to other users."""
    from fastapi import HTTPException

    from api.voice_bundle_user import BundleAssignRequest, set_user_bundle

    target_user_id = "other-user"
    current_user = {"user_id": "user-123", "role": "user"}
    mock_request = MagicMock()
    body = BundleAssignRequest(bundle_name="voice_extended")

    with pytest.raises(HTTPException):
        await set_user_bundle(target_user_id, body, mock_request, current_user)


@pytest.mark.asyncio
async def test_set_bundle_invalid_name():
    """Reject invalid bundle names."""
    from api.voice_bundle_user import set_user_bundle, BundleAssignRequest
    from fastapi import HTTPException

    user_id = "user-123"
    current_user = {"user_id": user_id, "role": "user"}
    mock_request = MagicMock()
    body = BundleAssignRequest(bundle_name="invalid_bundle")

    with pytest.raises(HTTPException) as exc_info:
        await set_user_bundle(user_id, body, mock_request, current_user)

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_clear_bundle_assignment():
    """User can clear their bundle assignment (set to None)."""
    from api.voice_bundle_user import set_user_bundle, BundleAssignRequest

    user_id = "user-123"
    current_user = {"user_id": user_id, "role": "user"}
    mock_request = MagicMock()
    body = BundleAssignRequest(bundle_name=None)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("user_management.database.get_async_session", return_value=mock_session):
        with patch("services.event_log.emit"):
            result = await set_user_bundle(user_id, body, mock_request, current_user)

    assert result.user_id == user_id
    assert result.bundle_name is None
    # Verify DELETE was called
    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args[0]
    assert "DELETE" in str(call_args[0])
