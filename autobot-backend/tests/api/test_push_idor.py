# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for push subscription IDOR vulnerability fix (GH#8967)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.push import SubscribeRequest, UnsubscribeRequest, subscribe, unsubscribe


@pytest.mark.asyncio
async def test_subscribe_ignores_user_id_in_request_body():
    """Verify subscribe endpoint ignores attacker-supplied user_id (fail-closed design)."""
    body = SubscribeRequest(
        endpoint="https://example.com/endpoint",
        p256dh="dh_key",
        auth="auth_key",
        user_id="attacker_user_id",  # Attacker tries to hijack another user's subscription
    )
    current_user = {"user_id": "legitimate_user_id"}
    session = AsyncMock(spec=AsyncSession)

    # Mock the select query to return None (new subscription)
    mock_query = AsyncMock()
    mock_query.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_query

    with patch("api.push.logger") as mock_logger:
        result = await subscribe(body, current_user, session)

        # Verify IDOR attempt was logged
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args
        assert "IDOR attempt" in warning_call[0][0]
        assert "attacker_user_id" in str(warning_call[0])
        assert "legitimate_user_id" in str(warning_call[0])

        # Verify subscription was created with legitimate user's ID, not attacker's
        session.add.assert_called_once()
        added_subscription = session.add.call_args[0][0]
        assert added_subscription.user_id == "legitimate_user_id"
        assert result == {"status": "subscribed"}


@pytest.mark.asyncio
async def test_subscribe_accepts_user_id_matching_authenticated_user():
    """Verify subscribe endpoint accepts user_id if it matches authenticated user (no warning)."""
    body = SubscribeRequest(
        endpoint="https://example.com/endpoint",
        p256dh="dh_key",
        auth="auth_key",
        user_id="legitimate_user_id",
    )
    current_user = {"user_id": "legitimate_user_id"}
    session = AsyncMock(spec=AsyncSession)

    mock_query = AsyncMock()
    mock_query.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_query

    with patch("api.push.logger") as mock_logger:
        result = await subscribe(body, current_user, session)

        # No warning should be logged when user_id matches
        mock_logger.warning.assert_not_called()
        assert result == {"status": "subscribed"}


@pytest.mark.asyncio
async def test_unsubscribe_ignores_user_id_in_request_body():
    """Verify unsubscribe endpoint ignores attacker-supplied user_id (fail-closed design)."""
    body = UnsubscribeRequest(
        endpoint="https://example.com/endpoint",
        user_id="attacker_user_id",
    )
    current_user = {"user_id": "legitimate_user_id"}
    session = AsyncMock(spec=AsyncSession)

    # Mock the delete query
    mock_query = AsyncMock()
    mock_query.rowcount = 1
    session.execute.return_value = mock_query

    with patch("api.push.logger") as mock_logger:
        await unsubscribe(body, current_user, session)

        # Verify IDOR attempt was logged
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args
        assert "IDOR attempt" in warning_call[0][0]
        assert "attacker_user_id" in str(warning_call[0])
        assert "legitimate_user_id" in str(warning_call[0])

        # Verify delete query used legitimate user's ID
        delete_call = session.execute.call_args[0][0]
        # The delete statement should filter by legitimate user_id
        assert "legitimate_user_id" in str(delete_call)


@pytest.mark.asyncio
async def test_subscribe_endpoint_hijacking_returns_409():
    """Verify subscribe returns 409 when endpoint is already owned by a different user (IDOR fix).

    Attack: User B submits User A's push endpoint URL without any user_id in body.
    The previous upsert silently overwrote user_id — now it must raise 409.
    """
    body = SubscribeRequest(
        endpoint="https://example.com/user_a_endpoint",
        p256dh="attacker_dh_key",
        auth="attacker_auth_key",
        # No user_id in body — attacker registers normally, using their own JWT
    )
    current_user = {"user_id": "user_b_attacker"}
    session = AsyncMock(spec=AsyncSession)

    # Simulate: endpoint already owned by user_a
    existing = MagicMock()
    existing.user_id = "user_a_victim"
    mock_query = AsyncMock()
    mock_query.scalar_one_or_none.return_value = existing
    session.execute.return_value = mock_query

    with pytest.raises(HTTPException) as exc_info:
        await subscribe(body, current_user, session)

    assert exc_info.value.status_code == 409
    assert "different user" in exc_info.value.detail


@pytest.mark.asyncio
async def test_subscribe_own_endpoint_refresh_succeeds():
    """Verify the owner can refresh (update keys for) their own subscription."""
    body = SubscribeRequest(
        endpoint="https://example.com/user_a_endpoint",
        p256dh="new_dh_key",
        auth="new_auth_key",
    )
    current_user = {"user_id": "user_a"}
    session = AsyncMock(spec=AsyncSession)

    existing = MagicMock()
    existing.user_id = "user_a"
    mock_query = AsyncMock()
    mock_query.scalar_one_or_none.return_value = existing
    session.execute.return_value = mock_query

    result = await subscribe(body, current_user, session)

    assert result == {"status": "subscribed"}
    assert existing.p256dh == "new_dh_key"
    assert existing.auth == "new_auth_key"


@pytest.mark.asyncio
async def test_subscribe_rejects_non_https_endpoint():
    """Verify subscribe endpoint rejects non-HTTPS endpoints (SSRF prevention)."""
    import pytest as _pytest
    from pydantic import ValidationError

    with _pytest.raises(ValidationError) as exc_info:
        SubscribeRequest(
            endpoint="http://internal-service.local/push",  # HTTP, not HTTPS
            p256dh="dh_key",
            auth="auth_key",
        )
    assert "https" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_subscribe_requires_authentication():
    """Verify subscribe endpoint requires valid authentication."""
    body = SubscribeRequest(
        endpoint="https://example.com/endpoint",
        p256dh="dh_key",
        auth="auth_key",
    )
    current_user = {"username": ""}  # Invalid: no user_id or username
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(HTTPException) as exc_info:
        await subscribe(body, current_user, session)

    assert exc_info.value.status_code == 401
    assert "Cannot identify user" in exc_info.value.detail
