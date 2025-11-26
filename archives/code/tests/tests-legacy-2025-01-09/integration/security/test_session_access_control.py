"""
Integration tests for session access control
Tests complete authorization flow across API endpoints
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock, Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api.chat import router as chat_router
from backend.security.session_ownership import SessionOwnershipValidator


@pytest.fixture
def app():
    """Create test FastAPI app."""
    app = FastAPI()
    app.include_router(chat_router, prefix="/api")

    # Mock app state
    app.state.chat_history_manager = Mock()
    app.state.chat_workflow_manager = Mock()

    return app


@pytest.fixture
def client(app):
    """Test client for making requests."""
    return TestClient(app)


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.sadd = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.smembers = AsyncMock(return_value=set())
    return redis


def test_unauthorized_session_access_returns_403(client, mock_redis):
    """Test that unauthorized users cannot access other users' sessions."""
    session_id = "723f7122-fa77-4d54-9145-6f1f335724ae"

    with patch('backend.security.session_ownership.get_redis_manager') as mock_manager:
        # Setup Redis mock
        redis_manager_instance = AsyncMock()
        redis_manager_instance.main = AsyncMock(return_value=mock_redis)
        mock_manager.return_value = redis_manager_instance

        # Session owned by different user
        mock_redis.get = AsyncMock(return_value=b"otheruser")

        with patch('backend.security.session_ownership.auth_middleware') as mock_auth:
            mock_auth.get_user_from_request.return_value = {
                "username": "testuser",
                "role": "user"
            }
            mock_auth.enable_auth = True
            mock_auth.security_layer.audit_log = Mock()

            # Try to access session owned by different user
            response = client.get(
                f"/api/chat/sessions/{session_id}",
                headers={"Authorization": "Bearer fake-token"}
            )

            assert response.status_code == 403
            assert "permission" in response.json()["error"]["message"].lower()


def test_authorized_session_access_returns_200(client, mock_redis):
    """Test that users can access their own sessions."""
    session_id = "723f7122-fa77-4d54-9145-6f1f335724ae"

    with patch('backend.security.session_ownership.get_redis_manager') as mock_manager:
        redis_manager_instance = AsyncMock()
        redis_manager_instance.main = AsyncMock(return_value=mock_redis)
        mock_manager.return_value = redis_manager_instance

        # Session owned by requesting user
        mock_redis.get = AsyncMock(return_value=b"testuser")

        with patch('backend.security.session_ownership.auth_middleware') as mock_auth:
            mock_auth.get_user_from_request.return_value = {
                "username": "testuser",
                "role": "user"
            }
            mock_auth.enable_auth = True
            mock_auth.security_layer.audit_log = Mock()

            with patch('backend.api.chat.get_chat_history_manager') as mock_history:
                mock_history.return_value.get_session_messages = AsyncMock(return_value=[])

                response = client.get(
                    f"/api/chat/sessions/{session_id}",
                    headers={"Authorization": "Bearer fake-token"}
                )

                # Should succeed for owner
                assert response.status_code == 200


def test_unauthenticated_access_returns_401(client, mock_redis):
    """Test that unauthenticated requests are rejected."""
    session_id = "723f7122-fa77-4d54-9145-6f1f335724ae"

    with patch('backend.security.session_ownership.get_redis_manager') as mock_manager:
        redis_manager_instance = AsyncMock()
        redis_manager_instance.main = AsyncMock(return_value=mock_redis)
        mock_manager.return_value = redis_manager_instance

        with patch('backend.security.session_ownership.auth_middleware') as mock_auth:
            # No user authenticated
            mock_auth.get_user_from_request.return_value = None

            response = client.get(f"/api/chat/sessions/{session_id}")

            assert response.status_code == 401


def test_legacy_session_migration(client, mock_redis):
    """Test that legacy sessions without owner are migrated."""
    session_id = "723f7122-fa77-4d54-9145-6f1f335724ae"

    with patch('backend.security.session_ownership.get_redis_manager') as mock_manager:
        redis_manager_instance = AsyncMock()
        redis_manager_instance.main = AsyncMock(return_value=mock_redis)
        mock_manager.return_value = redis_manager_instance

        # No owner stored (legacy session)
        mock_redis.get = AsyncMock(return_value=None)

        with patch('backend.security.session_ownership.auth_middleware') as mock_auth:
            mock_auth.get_user_from_request.return_value = {
                "username": "testuser",
                "role": "user"
            }
            mock_auth.enable_auth = True

            with patch('backend.api.chat.get_chat_history_manager') as mock_history:
                mock_history.return_value.get_session_messages = AsyncMock(return_value=[])

                response = client.get(
                    f"/api/chat/sessions/{session_id}",
                    headers={"Authorization": "Bearer fake-token"}
                )

                # Should succeed and assign ownership
                assert response.status_code == 200
                # Verify owner was set
                assert mock_redis.set.called


def test_auth_disabled_allows_all_access(client, mock_redis):
    """Test that when auth is disabled, all users can access any session."""
    session_id = "723f7122-fa77-4d54-9145-6f1f335724ae"

    with patch('backend.security.session_ownership.get_redis_manager') as mock_manager:
        redis_manager_instance = AsyncMock()
        redis_manager_instance.main = AsyncMock(return_value=mock_redis)
        mock_manager.return_value = redis_manager_instance

        with patch('backend.security.session_ownership.auth_middleware') as mock_auth:
            mock_auth.get_user_from_request.return_value = {
                "username": "admin",
                "role": "admin",
                "auth_disabled": True
            }
            mock_auth.enable_auth = False

            with patch('backend.api.chat.get_chat_history_manager') as mock_history:
                mock_history.return_value.get_session_messages = AsyncMock(return_value=[])

                response = client.get(f"/api/chat/sessions/{session_id}")

                assert response.status_code == 200


def test_list_chats_filtered_by_user(client, mock_redis):
    """Test that /chats endpoint only returns user's own sessions."""
    user1_sessions = {b"session1", b"session2", b"session3"}
    user2_sessions = {b"session4", b"session5"}

    with patch('backend.security.session_ownership.get_redis_manager') as mock_manager:
        redis_manager_instance = AsyncMock()
        redis_manager_instance.main = AsyncMock(return_value=mock_redis)
        mock_manager.return_value = redis_manager_instance

        # Mock user1's sessions
        mock_redis.smembers = AsyncMock(return_value=user1_sessions)

        with patch('backend.api.chat.auth_middleware') as mock_auth:
            mock_auth.get_user_from_request.return_value = {
                "username": "user1",
                "role": "user"
            }

            with patch('backend.api.chat.get_chat_history_manager') as mock_history:
                # Return all sessions
                mock_history.return_value.list_sessions_fast.return_value = [
                    {"session_id": "session1"},
                    {"session_id": "session2"},
                    {"session_id": "session3"},
                    {"session_id": "session4"},  # user2's session
                    {"session_id": "session5"},  # user2's session
                ]

                response = client.get("/api/chats")

                assert response.status_code == 200
                data = response.json()
                # Should only return user1's 3 sessions
                assert data["count"] == 3


def test_audit_logging_on_unauthorized_access(client, mock_redis):
    """Test that unauthorized access attempts are logged."""
    session_id = "723f7122-fa77-4d54-9145-6f1f335724ae"

    with patch('backend.security.session_ownership.get_redis_manager') as mock_manager:
        redis_manager_instance = AsyncMock()
        redis_manager_instance.main = AsyncMock(return_value=mock_redis)
        mock_manager.return_value = redis_manager_instance

        # Session owned by different user
        mock_redis.get = AsyncMock(return_value=b"otheruser")

        with patch('backend.security.session_ownership.auth_middleware') as mock_auth:
            mock_auth.get_user_from_request.return_value = {
                "username": "testuser",
                "role": "user"
            }
            mock_auth.enable_auth = True
            mock_auth.security_layer.audit_log = Mock()

            response = client.get(f"/api/chat/sessions/{session_id}")

            # Verify audit log was called
            mock_auth.security_layer.audit_log.assert_called_once()
            call_kwargs = mock_auth.security_layer.audit_log.call_args[1]
            assert call_kwargs["action"] == "unauthorized_conversation_access"
            assert call_kwargs["outcome"] == "denied"
            assert "testuser" in str(call_kwargs["details"])


def test_audit_logging_on_successful_access(client, mock_redis):
    """Test that successful access is logged."""
    session_id = "723f7122-fa77-4d54-9145-6f1f335724ae"

    with patch('backend.security.session_ownership.get_redis_manager') as mock_manager:
        redis_manager_instance = AsyncMock()
        redis_manager_instance.main = AsyncMock(return_value=mock_redis)
        mock_manager.return_value = redis_manager_instance

        # Session owned by requesting user
        mock_redis.get = AsyncMock(return_value=b"testuser")

        with patch('backend.security.session_ownership.auth_middleware') as mock_auth:
            mock_auth.get_user_from_request.return_value = {
                "username": "testuser",
                "role": "user"
            }
            mock_auth.enable_auth = True
            mock_auth.security_layer.audit_log = Mock()

            with patch('backend.api.chat.get_chat_history_manager') as mock_history:
                mock_history.return_value.get_session_messages = AsyncMock(return_value=[])

                response = client.get(f"/api/chat/sessions/{session_id}")

                # Verify audit log was called for successful access
                assert mock_auth.security_layer.audit_log.called
                call_kwargs = mock_auth.security_layer.audit_log.call_args[1]
                assert call_kwargs["action"] == "conversation_accessed"
                assert call_kwargs["outcome"] == "success"


def test_delete_session_with_ownership_check(client, mock_redis):
    """Test that delete endpoint validates ownership."""
    session_id = "723f7122-fa77-4d54-9145-6f1f335724ae"

    with patch('backend.security.session_ownership.get_redis_manager') as mock_manager:
        redis_manager_instance = AsyncMock()
        redis_manager_instance.main = AsyncMock(return_value=mock_redis)
        mock_manager.return_value = redis_manager_instance

        # Session owned by different user
        mock_redis.get = AsyncMock(return_value=b"otheruser")

        with patch('backend.security.session_ownership.auth_middleware') as mock_auth:
            mock_auth.get_user_from_request.return_value = {
                "username": "testuser",
                "role": "user"
            }
            mock_auth.enable_auth = True
            mock_auth.security_layer.audit_log = Mock()

            response = client.delete(f"/api/chat/sessions/{session_id}")

            # Should be rejected - user doesn't own session
            assert response.status_code == 403


@pytest.mark.asyncio
async def test_performance_validation_under_10ms():
    """Test that ownership validation completes under 10ms."""
    import time

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=b"testuser")

    validator = SessionOwnershipValidator(mock_redis)

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

        # Run 100 validations and measure average time
        times = []
        for _ in range(100):
            start = time.time()
            await validator.validate_ownership("test-session-id", mock_request)
            end = time.time()
            times.append((end - start) * 1000)  # Convert to ms

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # Assert performance requirements
        assert avg_time < 10, f"Average validation time {avg_time}ms exceeds 10ms requirement"
        assert max_time < 50, f"Max validation time {max_time}ms is too high"
