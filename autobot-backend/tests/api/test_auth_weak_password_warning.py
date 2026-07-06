# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the login-time soft weak-password warning (#10199).

Covers:
- check_password_weakness helper (all three weakness criteria).
- /login response includes password_warning when password is weak.
- /login response omits password_warning when password is strong.
- Login ALWAYS succeeds (token present) regardless of weakness.
- The submitted plaintext password is not present in log output.
"""

from unittest.mock import MagicMock, patch

import pytest

from autobot_shared.security.password_weakness import check_password_weakness

# ---------------------------------------------------------------------------
# Helper tests — check_password_weakness
# ---------------------------------------------------------------------------


class TestCheckPasswordWeakness:
    def test_none_for_strong_password(self):
        assert check_password_weakness("Tr0ub4dor&3xact!") is None

    def test_none_for_long_unique_password(self):
        assert check_password_weakness("CorrectHorseBatteryStaple2026!") is None

    def test_flags_short_password(self):
        reason = check_password_weakness("short1A!")
        assert reason is not None
        assert "short" in reason.lower() or "minimum" in reason.lower()

    def test_flags_common_password(self):
        # "qwerty123" is 9 chars (below _MIN_LENGTH=12), so also short — use a
        # value that is long enough to bypass the length gate but still common.
        # "iloveyou" is 8 chars; use "correcthorse" style padding to keep
        # the membership test in isolation OR simply assert any weakness fires.
        # "password" is only 8 chars so the length gate fires first (both are
        # valid weakness signals; the test just verifies *some* reason is returned).
        reason = check_password_weakness("password")
        assert reason is not None  # either too-short or common-password reason

    def test_flags_common_password_over_length_gate(self):
        """A 12+-char common password hits the common-password check."""
        # "password123456" is 14 chars and lowercased in set membership check.
        # It's not in _COMMON_PASSWORDS as-is; use one that is: "password1" is 9
        # chars — pad to verify. Instead, test with a known-set member that is long.
        # The set has "autobot123" (10 chars) and "autobot" (7). Neither passes
        # length gate alone. Add a long enough value to the set check:
        # easiest: mock _COMMON_PASSWORDS via the module attribute.
        import autobot_shared.security.password_weakness as mod

        original = mod._COMMON_PASSWORDS
        try:
            mod._COMMON_PASSWORDS = frozenset({"correcthorsebattery"})
            reason = check_password_weakness("correcthorsebattery")
            assert reason is not None
            assert "common" in reason.lower() or "commonly" in reason.lower()
        finally:
            mod._COMMON_PASSWORDS = original

    def test_common_check_is_case_insensitive(self):
        # "QWERTY" is only 6 chars so length gate fires first — that's fine;
        # both are weakness signals. Use a value that IS long enough: mock set.
        import autobot_shared.security.password_weakness as mod

        original = mod._COMMON_PASSWORDS
        try:
            mod._COMMON_PASSWORDS = frozenset({"longcommonpassword"})
            reason = check_password_weakness("LONGCOMMONPASSWORD")
            assert reason is not None
        finally:
            mod._COMMON_PASSWORDS = original

    def test_flags_seeded_default_password(self):
        """When login password equals the configured seed password, flag it."""
        with patch(
            "autobot_shared.security.password_weakness._get_seeded_default",
            return_value="SeedP@ssw0rd2026",
        ):
            reason = check_password_weakness("SeedP@ssw0rd2026")
        assert reason is not None
        assert "default" in reason.lower()

    def test_no_flag_when_seed_password_is_empty(self):
        """If AUTOBOT_ADMIN_PASSWORD is unset, seeded default is '' — no false positive."""
        with patch(
            "autobot_shared.security.password_weakness._get_seeded_default",
            return_value="",
        ):
            # Strong password that just happens to be tested without a seed value
            result = check_password_weakness("SeedP@ssw0rd2026")
        assert result is None

    def test_empty_password_returns_none(self):
        """Empty string should not raise; schema validation catches it before we do."""
        assert check_password_weakness("") is None

    def test_seeded_check_takes_priority_over_length(self):
        """If password equals seed AND is short, the seeded-default reason is returned."""
        with patch(
            "autobot_shared.security.password_weakness._get_seeded_default",
            return_value="short",
        ):
            reason = check_password_weakness("short")
        assert reason is not None
        assert "default" in reason.lower()


# ---------------------------------------------------------------------------
# Integration-style tests — login endpoint
# ---------------------------------------------------------------------------


def _make_request() -> MagicMock:
    req = MagicMock()
    req.client.host = "127.0.0.1"
    return req


def _mock_auth_data(username: str = "admin") -> dict:
    return {
        "username": username,
        "user_id": "00000000-0000-0000-0000-000000000001",
        "role": "admin",
        "email": f"{username}@autobot.local",
        "last_login": None,
        "org_id": None,
    }


class TestLoginWeakPasswordWarning:
    @pytest.mark.asyncio
    async def test_weak_password_login_succeeds_with_warning(self):
        """Login with a weak password still returns 200 + token + password_warning."""
        from api.auth import login
        from api.schemas_agent import LoginRequest

        user_data = _mock_auth_data()

        with (
            patch("api.auth._authenticate_and_build_user_data", return_value=user_data),
            patch(
                "api.auth.get_auth_middleware",
                return_value=MagicMock(
                    create_jwt_token=MagicMock(return_value="fake.jwt.token"),
                    create_session=MagicMock(return_value="fake-session-id"),
                ),
            ),
            patch("api.auth._emit_event"),
            patch(
                "autobot_shared.security.password_weakness._get_seeded_default",
                return_value="",
            ),
        ):
            req = _make_request()
            # "password" is in the common-password set → weak
            login_req = LoginRequest(username="admin", password="password")
            response = await login(request=req, login_data=login_req)

        assert response.success is True, "Login must succeed even with a weak password"
        assert response.token == "fake.jwt.token", "Token must be present"
        assert response.password_warning is not None, "Weak password must trigger warning"
        assert response.password_warning.weak is True
        assert response.password_warning.reason != ""

    @pytest.mark.asyncio
    async def test_strong_password_login_has_no_warning(self):
        """Login with a strong password returns 200 + token + no password_warning."""
        from api.auth import login
        from api.schemas_agent import LoginRequest

        user_data = _mock_auth_data()

        with (
            patch("api.auth._authenticate_and_build_user_data", return_value=user_data),
            patch(
                "api.auth.get_auth_middleware",
                return_value=MagicMock(
                    create_jwt_token=MagicMock(return_value="fake.jwt.token"),
                    create_session=MagicMock(return_value="fake-session-id"),
                ),
            ),
            patch("api.auth._emit_event"),
            patch(
                "autobot_shared.security.password_weakness._get_seeded_default",
                return_value="",
            ),
        ):
            req = _make_request()
            # Long, unique password — should not trigger any warning
            login_req = LoginRequest(username="admin", password="Tr0ub4dor&3-Exact-2026!")
            response = await login(request=req, login_data=login_req)

        assert response.success is True
        assert response.token == "fake.jwt.token"
        assert response.password_warning is None, "Strong password must produce no warning"

    @pytest.mark.asyncio
    async def test_seeded_default_password_triggers_warning(self):
        """Login with the operator-configured seed password triggers the warning."""
        from api.auth import login
        from api.schemas_agent import LoginRequest

        user_data = _mock_auth_data()
        seed_pw = "OperatorSeedPass99!"

        with (
            patch("api.auth._authenticate_and_build_user_data", return_value=user_data),
            patch(
                "api.auth.get_auth_middleware",
                return_value=MagicMock(
                    create_jwt_token=MagicMock(return_value="fake.jwt.token"),
                    create_session=MagicMock(return_value="fake-session-id"),
                ),
            ),
            patch("api.auth._emit_event"),
            patch(
                "autobot_shared.security.password_weakness._get_seeded_default",
                return_value=seed_pw,
            ),
        ):
            req = _make_request()
            login_req = LoginRequest(username="admin", password=seed_pw)
            response = await login(request=req, login_data=login_req)

        assert response.success is True
        assert response.token is not None
        assert response.password_warning is not None
        assert "default" in response.password_warning.reason.lower()

    @pytest.mark.asyncio
    async def test_password_not_present_in_log_on_warning(self, caplog):
        """Logged warning message must NOT contain the plaintext password.

        Uses a deliberately unique sentinel so any accidental inclusion is
        caught — the word itself would never appear in a log message naturally.
        """
        import logging

        from api.auth import login
        from api.schemas_agent import LoginRequest

        user_data = _mock_auth_data()
        # "xK9mQ2vR" is 8 chars (< 12 → triggers length warning) and contains
        # no common word, so the reason string will never include this literal.
        weak_pw = "xK9mQ2vR"

        with (
            patch("api.auth._authenticate_and_build_user_data", return_value=user_data),
            patch(
                "api.auth.get_auth_middleware",
                return_value=MagicMock(
                    create_jwt_token=MagicMock(return_value="fake.jwt.token"),
                    create_session=MagicMock(return_value="fake-session-id"),
                ),
            ),
            patch("api.auth._emit_event"),
            patch(
                "autobot_shared.security.password_weakness._get_seeded_default",
                return_value="",
            ),
            caplog.at_level(logging.INFO, logger="api.auth"),
        ):
            req = _make_request()
            login_req = LoginRequest(username="admin", password=weak_pw)
            response = await login(request=req, login_data=login_req)

        # Confirm a warning was indeed emitted (the password IS weak — too short)
        assert response.password_warning is not None, "Expected weakness warning for short password"

        # Confirm the plaintext is absent from every log record
        for record in caplog.records:
            assert (
                weak_pw not in record.getMessage()
            ), f"Plaintext password must not appear in log: {record.getMessage()!r}"
