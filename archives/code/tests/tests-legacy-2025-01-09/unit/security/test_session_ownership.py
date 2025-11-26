"""
Unit tests for session ownership validation
Tests access control for conversation data
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from backend.security.session_ownership import SessionOwnershipValidator
from fastapi import HTTPException


@pytest.fixture
async def mock_redis():
    """Mock Redis client for testing."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=b"testuser")
    redis.sadd = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.smembers = AsyncMock(return_value={b"session1", b"session2"})
    return redis


@pytest.fixture
def validator(mock_redis):
    """Session ownership validator instance."""
    return SessionOwnershipValidator(mock_redis)


@pytest.mark.asyncio
async def test_set_session_owner(validator, mock_redis):
    """Test setting session owner."""
    result = await validator.set_session_owner("test-session-id", "testuser")

    assert result is True
    mock_redis.set.assert_called_once()
    assert mock_redis.set.call_args[0][0] == "chat_session_owner:test-session-id"
    assert mock_redis.set.call_args[0][1] == "testuser"
    mock_redis.sadd.assert_called_once()


@pytest.mark.asyncio
async def test_get_session_owner_bytes(validator, mock_redis):
    """Test retrieving session owner (bytes response)."""
    mock_redis.get = AsyncMock(return_value=b"testuser")
    owner = await validator.get_session_owner("test-session-id")

    assert owner == "testuser"
    mock_redis.get.assert_called_once_with("chat_session_owner:test-session-id")


@pytest.mark.asyncio
async def test_get_session_owner_str(validator, mock_redis):
    """Test retrieving session owner (string response)."""
    mock_redis.get = AsyncMock(return_value="testuser")
    owner = await validator.get_session_owner("test-session-id")

    assert owner == "testuser"


@pytest.mark.asyncio
async def test_get_session_owner_not_found(validator, mock_redis):
    """Test retrieving non-existent session owner."""
    mock_redis.get = AsyncMock(return_value=None)
    owner = await validator.get_session_owner("test-session-id")

    assert owner is None


@pytest.mark.asyncio
async def test_validate_ownership_success(validator, mock_redis):
    """Test successful ownership validation."""
    mock_request = Mock()
    mock_request.client = Mock()
    mock_request.client.host = "127.0.0.1"

    with patch('backend.security.session_ownership.auth_middleware') as mock_auth:
        mock_auth.get_user_from_request.return_value = {
            "username": "testuser",
            "role": "user"
        }
        mock_auth.enable_auth = True
        mock_auth.security_layer.audit_log = Mock()

        result = await validator.validate_ownership("test-session-id", mock_request)

        assert result["authorized"] is True
        assert result["user_data"]["username"] == "testuser"
        assert result["reason"] == "owner_match"
        mock_auth.security_layer.audit_log.assert_called_once()


@pytest.mark.asyncio
async def test_validate_ownership_unauthorized(validator, mock_redis):
    """Test unauthorized access attempt."""
    mock_redis.get = AsyncMock(return_value=b"otheruser")  # Different owner

    mock_request = Mock()
    mock_request.client = Mock()
    mock_request.client.host = "127.0.0.1"

    with patch('backend.security.session_ownership.auth_middleware') as mock_auth:
        mock_auth.get_user_from_request.return_value = {
            "username": "testuser",
            "role": "user"
        }
        mock_auth.enable_auth = True
        mock_auth.security_layer.audit_log = Mock()

        with pytest.raises(HTTPException) as exc_info:
            await validator.validate_ownership("test-session-id", mock_request)

        assert exc_info.value.status_code == 403
        assert "permission" in exc_info.value.detail.lower()
        # Verify audit log was called for unauthorized access
        mock_auth.security_layer.audit_log.assert_called_once()
        call_args = mock_auth.security_layer.audit_log.call_args
        assert call_args[1]["action"] == "unauthorized_conversation_access"
        assert call_args[1]["outcome"] == "denied"


@pytest.mark.asyncio
async def test_validate_ownership_no_auth(validator, mock_redis):
    """Test validation when not authenticated."""
    mock_request = Mock()
    mock_request.client = Mock()
    mock_request.client.host = "127.0.0.1"

    with patch('backend.security.session_ownership.auth_middleware') as mock_auth:
        mock_auth.get_user_from_request.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await validator.validate_ownership("test-session-id", mock_request)

        assert exc_info.value.status_code == 401
        assert "authentication required" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_validate_ownership_auth_disabled(validator, mock_redis):
    """Test validation when auth is disabled (development mode)."""
    mock_request = Mock()
    mock_request.client = Mock()
    mock_request.client.host = "127.0.0.1"

    with patch('backend.security.session_ownership.auth_middleware') as mock_auth:
        mock_auth.get_user_from_request.return_value = {
            "username": "admin",
            "role": "admin",
            "auth_disabled": True
        }
        mock_auth.enable_auth = False

        result = await validator.validate_ownership("test-session-id", mock_request)

        assert result["authorized"] is True
        assert result["reason"] == "auth_disabled"


@pytest.mark.asyncio
async def test_validate_ownership_legacy_migration(validator, mock_redis):
    """Test handling of legacy sessions without owner."""
    mock_redis.get = AsyncMock(return_value=None)  # No owner stored
    mock_redis.set = AsyncMock(return_value=True)

    mock_request = Mock()
    mock_request.client = Mock()
    mock_request.client.host = "127.0.0.1"

    with patch('backend.security.session_ownership.auth_middleware') as mock_auth:
        mock_auth.get_user_from_request.return_value = {
            "username": "testuser",
            "role": "user"
        }
        mock_auth.enable_auth = True

        result = await validator.validate_ownership("test-session-id", mock_request)

        assert result["authorized"] is True
        assert result["reason"] == "legacy_migration"
        # Verify owner was set for legacy session
        mock_redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_get_user_sessions(validator, mock_redis):
    """Test retrieving all user sessions."""
    sessions = await validator.get_user_sessions("testuser")

    assert len(sessions) == 2
    assert "session1" in sessions
    assert "session2" in sessions
    mock_redis.smembers.assert_called_once_with("user_chat_sessions:testuser")


@pytest.mark.asyncio
async def test_get_user_sessions_empty(validator, mock_redis):
    """Test retrieving sessions when user has none."""
    mock_redis.smembers = AsyncMock(return_value=set())
    sessions = await validator.get_user_sessions("testuser")

    assert sessions == []


@pytest.mark.asyncio
async def test_get_user_sessions_error(validator, mock_redis):
    """Test error handling in get_user_sessions."""
    mock_redis.smembers = AsyncMock(side_effect=Exception("Redis error"))
    sessions = await validator.get_user_sessions("testuser")

    assert sessions == []


@pytest.mark.asyncio
async def test_set_session_owner_error(validator, mock_redis):
    """Test error handling in set_session_owner."""
    mock_redis.set = AsyncMock(side_effect=Exception("Redis error"))
    result = await validator.set_session_owner("test-session-id", "testuser")

    assert result is False


@pytest.mark.asyncio
async def test_validate_ownership_audit_log_error(validator, mock_redis):
    """Test that audit log errors don't break validation."""
    mock_request = Mock()
    mock_request.client = Mock()
    mock_request.client.host = "127.0.0.1"

    with patch('backend.security.session_ownership.auth_middleware') as mock_auth:
        mock_auth.get_user_from_request.return_value = {
            "username": "testuser",
            "role": "user"
        }
        mock_auth.enable_auth = True
        # Make audit log raise exception
        mock_auth.security_layer.audit_log = Mock(side_effect=Exception("Audit error"))

        # Should still succeed despite audit log error
        result = await validator.validate_ownership("test-session-id", mock_request)

        assert result["authorized"] is True


@pytest.mark.asyncio
async def test_ownership_key_generation(validator):
    """Test Redis key generation for ownership."""
    key = validator._get_ownership_key("test-session-123")
    assert key == "chat_session_owner:test-session-123"


@pytest.mark.asyncio
async def test_user_sessions_key_generation(validator):
    """Test Redis key generation for user sessions."""
    key = validator._get_user_sessions_key("testuser")
    assert key == "user_chat_sessions:testuser"
