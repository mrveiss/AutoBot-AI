# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for push subscription IDOR vulnerability fix (GH#8967)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.push import subscribe, unsubscribe, SubscribeRequest, UnsubscribeRequest


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
        result = await unsubscribe(body, current_user, session)

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
