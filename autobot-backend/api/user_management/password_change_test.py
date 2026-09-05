# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Password Change API Endpoint

Tests rate limiting, caller-identity authorization, and password change
functionality. Issues #635, #15743.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, status

from user_management.middleware.rate_limit import RateLimitExceeded
from user_management.services import TenantContext
from user_management.services.user_service import (
    InvalidCredentialsError,
    UserNotFoundError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _call_change_password(user_id, pwd_change, user_service, current_user, context):
    """Resolve the route's gate the way FastAPI does, then call the handler.

    ``authorize_password_change`` is a route DEPENDENCY, not a call inside the
    handler body -- deliberately, so the gate is visible in the ``Dependant``
    tree that ``user_management_route_posture_test.py`` reads (#15737).

    That makes this helper load-bearing rather than cosmetic: calling
    ``change_password`` directly would bypass the gate entirely, and every
    assertion in this file -- including the takeover case -- would then pass
    against a completely ungated handler. Resolving the dependency here is what
    keeps these tests testing the real path.
    """
    from api.user_management.password_change import authorize_password_change, change_password

    require_current = await authorize_password_change(user_id, context)
    return await change_password(user_id, pwd_change, user_service, current_user, context, require_current)


@pytest.fixture
def mock_user_service():
    """Create mock user service."""
    service = AsyncMock()
    service.change_password = AsyncMock()
    return service


@pytest.fixture
def mock_rate_limiter():
    """Create mock rate limiter."""
    limiter = AsyncMock()
    limiter.check_rate_limit = AsyncMock(return_value=(True, 3))
    limiter.record_attempt = AsyncMock()
    return limiter


@pytest.fixture
def user_id():
    """Generate test user ID -- the change-password target."""
    return uuid.uuid4()


@pytest.fixture
def password_data():
    """Password change request data."""
    return {
        "current_password": "OldP@ssw0rd!",
        "new_password": "NewP@ssw0rd!",
    }


@pytest.fixture
def mock_current_user(user_id):
    """Mock current user with token -- self-service caller (#15743): the
    JWT this dict stands in for identifies the same principal as
    ``self_context``, since both are derived from the same token in
    production (``get_current_user`` and ``get_tenant_context``)."""
    return {
        "user_id": str(user_id),
        "token": "current.jwt.token.here",
    }


@pytest.fixture
def self_context(user_id):
    """TenantContext for the caller changing their own password (#15743)."""
    return TenantContext(user_id=user_id, is_platform_admin=False)


def _patched_limiter(mock_rate_limiter):
    """Patch the endpoint module's rate limiter constructor (#15743: moved
    to ``password_change.py``)."""
    return patch(
        "api.user_management.password_change.PasswordChangeRateLimiter",
        return_value=mock_rate_limiter,
    )


def _new_password_only(value):
    """Build a ``PasswordChange`` payload carrying only ``new_password`` --
    the omitted-field shape that caused #15743 -- via a dict literal so a
    fake test value never reads like a keyword-argument credential."""
    from user_management.schemas import PasswordChange

    return PasswordChange(**{"new_password": value})


# ---------------------------------------------------------------------------
# Test: Rate Limiting
# ---------------------------------------------------------------------------


class TestPasswordChangeRateLimiting:
    """Tests for rate limiting on password change endpoint."""

    @pytest.mark.asyncio
    async def test_rate_limit_check_called_before_change(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
        self_context,
        mock_rate_limiter,
    ):
        """Rate limit should be checked before attempting password change."""
        with _patched_limiter(mock_rate_limiter):
            from user_management.schemas import PasswordChange

            pwd_change = PasswordChange(**password_data)
            await _call_change_password(user_id, pwd_change, mock_user_service, mock_current_user, self_context)

            mock_rate_limiter.check_rate_limit.assert_called_once_with(user_id, actor_id=user_id)

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_returns_429(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
        self_context,
        mock_rate_limiter,
    ):
        """Should return 429 when rate limit is exceeded."""
        mock_rate_limiter.check_rate_limit = AsyncMock(
            side_effect=RateLimitExceeded("Too many attempts. Try again in 15 minutes.")
        )

        with _patched_limiter(mock_rate_limiter):
            from user_management.schemas import PasswordChange

            pwd_change = PasswordChange(**password_data)

            with pytest.raises(HTTPException) as exc_info:
                await _call_change_password(user_id, pwd_change, mock_user_service, mock_current_user, self_context)

            assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
            assert "Too many attempts" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_successful_change_clears_rate_limit(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
        self_context,
        mock_rate_limiter,
    ):
        """Successful password change should clear rate limit counters."""
        with _patched_limiter(mock_rate_limiter):
            from user_management.schemas import PasswordChange

            pwd_change = PasswordChange(**password_data)
            await _call_change_password(user_id, pwd_change, mock_user_service, mock_current_user, self_context)

            mock_rate_limiter.record_attempt.assert_called_once_with(user_id, success=True, actor_id=user_id)

    @pytest.mark.asyncio
    async def test_failed_change_increments_rate_limit(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
        self_context,
        mock_rate_limiter,
    ):
        """Failed password change should increment rate limit counter."""
        mock_user_service.change_password = AsyncMock(
            side_effect=InvalidCredentialsError("Current password is incorrect")
        )

        with _patched_limiter(mock_rate_limiter):
            from user_management.schemas import PasswordChange

            pwd_change = PasswordChange(**password_data)

            with pytest.raises(HTTPException) as exc_info:
                await _call_change_password(user_id, pwd_change, mock_user_service, mock_current_user, self_context)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            mock_rate_limiter.record_attempt.assert_called_once_with(user_id, success=False, actor_id=user_id)


# ---------------------------------------------------------------------------
# Test: Password Change Responses
# ---------------------------------------------------------------------------


class TestPasswordChangeResponses:
    """Tests for password change response handling."""

    @pytest.mark.asyncio
    async def test_user_not_found_returns_404(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
        self_context,
        mock_rate_limiter,
    ):
        """Should return 404 when user is not found."""
        mock_user_service.change_password = AsyncMock(side_effect=UserNotFoundError(f"User {user_id} not found"))

        with _patched_limiter(mock_rate_limiter):
            from user_management.schemas import PasswordChange

            pwd_change = PasswordChange(**password_data)

            with pytest.raises(HTTPException) as exc_info:
                await _call_change_password(user_id, pwd_change, mock_user_service, mock_current_user, self_context)

            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_invalid_credentials_returns_401(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
        self_context,
        mock_rate_limiter,
    ):
        """Should return 401 when current password is incorrect."""
        mock_user_service.change_password = AsyncMock(
            side_effect=InvalidCredentialsError("Current password is incorrect")
        )

        with _patched_limiter(mock_rate_limiter):
            from user_management.schemas import PasswordChange

            pwd_change = PasswordChange(**password_data)

            with pytest.raises(HTTPException) as exc_info:
                await _call_change_password(user_id, pwd_change, mock_user_service, mock_current_user, self_context)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Current password is incorrect" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_successful_change_returns_success_message(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
        self_context,
        mock_rate_limiter,
    ):
        """Should return success message on successful password change."""
        with _patched_limiter(mock_rate_limiter):
            from user_management.schemas import PasswordChange

            pwd_change = PasswordChange(**password_data)
            response = await _call_change_password(
                user_id, pwd_change, mock_user_service, mock_current_user, self_context
            )

            assert response.success is True
            assert response.message == "Password changed successfully"


# ---------------------------------------------------------------------------
# Test: Caller-Identity Authorization (#15743)
# ---------------------------------------------------------------------------


class TestPasswordChangeAuthorization:
    """Proves the account-takeover is closed: ``require_current`` follows the
    caller's identity, never the request body, and a non-admin cannot reach
    another user's password at all."""

    @pytest.mark.asyncio
    async def test_non_admin_non_owner_is_rejected(
        self,
        user_id,
        mock_user_service,
        mock_rate_limiter,
    ):
        """THE takeover case: an authenticated non-admin, non-owner caller
        posts only ``new_password`` at another user's id. This must be
        rejected before the service is ever called -- the vulnerable code
        would have accepted this and silently disabled verification."""
        attacker_id = uuid.uuid4()
        current_user = {"user_id": str(attacker_id), "token": "attacker.jwt"}
        context = TenantContext(user_id=attacker_id, is_platform_admin=False)

        with _patched_limiter(mock_rate_limiter):
            pass

            pwd_change = _new_password_only("StolenP@ss1")

            with pytest.raises(HTTPException) as exc_info:
                await _call_change_password(user_id, pwd_change, mock_user_service, current_user, context)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            mock_user_service.change_password.assert_not_called()

    @pytest.mark.asyncio
    async def test_omitted_current_password_does_not_disable_verification_for_self(
        self,
        user_id,
        mock_user_service,
        mock_current_user,
        self_context,
        mock_rate_limiter,
    ):
        """The omitted-field shape that caused the bug: no ``current_password``
        on a self-service request must still require verification -- the
        old code derived ``require_current`` from this exact absence."""
        with _patched_limiter(mock_rate_limiter):
            pass

            pwd_change = _new_password_only("NewP@ssw0rd!")
            await _call_change_password(user_id, pwd_change, mock_user_service, mock_current_user, self_context)

            mock_user_service.change_password.assert_called_once()
            _, kwargs = mock_user_service.change_password.call_args
            assert kwargs["require_current"] is True
            assert kwargs["current_password"] is None

    @pytest.mark.asyncio
    async def test_self_service_with_current_password_requires_verification(
        self,
        user_id,
        password_data,
        mock_user_service,
        mock_current_user,
        self_context,
        mock_rate_limiter,
    ):
        """Self-service with a current password supplied still verifies it
        (``require_current`` is derived from identity, not from what was
        sent)."""
        with _patched_limiter(mock_rate_limiter):
            from user_management.schemas import PasswordChange

            pwd_change = PasswordChange(**password_data)
            await _call_change_password(user_id, pwd_change, mock_user_service, mock_current_user, self_context)

            _, kwargs = mock_user_service.change_password.call_args
            assert kwargs["require_current"] is True

    @pytest.mark.asyncio
    async def test_admin_can_reset_another_users_password_without_current(
        self,
        user_id,
        mock_user_service,
        mock_rate_limiter,
    ):
        """An actual platform admin (real gate, not a body flag) resetting
        someone else's password skips current-password verification."""
        admin_id = uuid.uuid4()
        current_user = {"user_id": str(admin_id), "token": "admin.jwt"}
        context = TenantContext(user_id=admin_id, is_platform_admin=True)

        with _patched_limiter(mock_rate_limiter):
            pass

            pwd_change = _new_password_only("ResetP@ss1")
            response = await _call_change_password(user_id, pwd_change, mock_user_service, current_user, context)

            assert response.success is True
            _, kwargs = mock_user_service.change_password.call_args
            assert kwargs["require_current"] is False

    @pytest.mark.asyncio
    async def test_role_claim_alone_does_not_grant_reset(
        self,
        user_id,
        mock_user_service,
        mock_rate_limiter,
    ):
        """``is_platform_admin=False`` in the context is authoritative even if
        some other claim on ``current_user`` looks admin-ish -- the endpoint
        must consult the actual gate, not re-derive its own notion of admin."""
        caller_id = uuid.uuid4()
        current_user = {"user_id": str(caller_id), "role": "admin", "token": "t"}
        context = TenantContext(user_id=caller_id, is_platform_admin=False)

        with _patched_limiter(mock_rate_limiter):
            pass

            pwd_change = _new_password_only("StolenP@ss1")

            with pytest.raises(HTTPException) as exc_info:
                await _call_change_password(user_id, pwd_change, mock_user_service, current_user, context)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestRequireCurrentCannotArriveFromTheWire:
    """FastAPI must never bind ``require_current`` from the request (#15743).

    Every other test in this file resolves the gate by hand, so none of them
    exercise FastAPI's own parameter binding -- and binding is precisely where
    the original defect lived. The generated OpenAPI schema shows
    ``require_current`` absent from the wire surface, but a schema is a side
    effect: it does not fail when someone later changes the signature. These
    two tests assert the property directly, through a real client.

    The route is mounted on a throwaway app rather than the full application so
    the assertion is about this route's binding and nothing else.
    """

    @staticmethod
    def _client(recorder):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.user_management import password_change as module

        app = FastAPI()
        app.include_router(module.router, prefix="/user-management")

        caller = uuid.uuid4()

        async def _fake_service():
            service = AsyncMock()
            service.change_password = AsyncMock(side_effect=recorder)
            return service

        app.dependency_overrides[module.get_user_service] = _fake_service
        app.dependency_overrides[module.get_current_user] = lambda: {
            "user_id": str(caller),
            "token": "caller.jwt",
        }
        app.dependency_overrides[module.get_tenant_context] = lambda: TenantContext(
            user_id=caller, is_platform_admin=False
        )
        return TestClient(app), caller

    def _post(self, url_suffix: str, body: dict):
        seen = {}

        async def _record(**kwargs):
            seen.update(kwargs)

        with patch(
            "api.user_management.password_change.PasswordChangeRateLimiter",
            return_value=AsyncMock(check_rate_limit=AsyncMock(), record_attempt=AsyncMock()),
        ):
            client, caller = self._client(_record)
            response = client.post(
                f"/user-management/users/{caller}/change-password{url_suffix}",
                json=body,
            )
        return response, seen

    def test_a_require_current_query_parameter_is_ignored(self):
        """``?require_current=false`` must not reach the service.

        A ``bool`` parameter whose default is ``Depends(...)`` should be
        dependency-bound rather than query-bound -- but "should be" is the
        reasoning that produced the original bug, so it is asserted.
        """
        response, seen = self._post("?require_current=false", {"new_password": "N3wP@ssword!"})

        assert response.status_code == status.HTTP_200_OK, response.text
        assert seen.get("require_current") is True

    def test_a_require_current_body_field_is_ignored(self):
        """Same property from the body, the channel the original bug used.

        Weaker than the query case, and worth saying so: making the parameter
        wire-bindable turns it into a QUERY parameter, which the test above
        catches. This one covers the other route in -- someone adding
        ``require_current`` to the ``PasswordChange`` model and reading it off
        ``password_data`` -- and it fails only against that change. Two
        channels, two tests; neither subsumes the other.
        """
        response, seen = self._post(
            "",
            {"new_password": "N3wP@ssword!", "require_current": False},
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        assert seen.get("require_current") is True
