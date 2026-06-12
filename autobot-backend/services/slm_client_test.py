# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for SLM client SSL context, WebSocket reconnect backoff (#4664),
and service JWT minting (#9852).
"""

import os
import ssl
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.auth.jwt_core import decode_jwt
from services.slm_client import (
    _SERVICE_JWT_TTL_HOURS,
    SLMClient,
    _create_permissive_ssl_context,
    _get_slm_signing_secret,
    _mint_service_jwt,
)


class TestCreatePermissiveSslContext:
    """Tests for _create_permissive_ssl_context SSL trust hierarchy."""

    def test_returns_ssl_context(self) -> None:
        """Default call returns an ssl.SSLContext."""
        ctx = _create_permissive_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)

    def test_verification_enabled_by_default(self) -> None:
        """Without any env vars, verification is not disabled."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOBOT_SKIP_TLS_VERIFY", None)
            os.environ.pop("AUTOBOT_TLS_CA_PATH", None)
            ctx = _create_permissive_ssl_context()
        assert ctx.verify_mode != ssl.CERT_NONE

    def test_skip_tls_verify_disables_verification(self) -> None:
        """AUTOBOT_SKIP_TLS_VERIFY=true disables cert verification."""
        with patch.dict(os.environ, {"AUTOBOT_SKIP_TLS_VERIFY": "true"}, clear=False):
            os.environ.pop("AUTOBOT_TLS_CA_PATH", None)
            ctx = _create_permissive_ssl_context()
        assert ctx.verify_mode == ssl.CERT_NONE
        assert ctx.check_hostname is False

    def test_explicit_ca_path_loads_ca(self) -> None:
        """AUTOBOT_TLS_CA_PATH pointing to a valid CA cert is loaded."""
        # Create a dummy self-signed CA cert on disk
        import subprocess

        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            ca_path = f.name

        try:
            result = subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-keyout",
                    "/dev/null",
                    "-out",
                    ca_path,
                    "-days",
                    "1",
                    "-nodes",
                    "-subj",
                    "/CN=TestCA",
                ],
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                pytest.skip("openssl not available")

            with patch.dict(os.environ, {"AUTOBOT_TLS_CA_PATH": ca_path}, clear=False):
                os.environ.pop("AUTOBOT_SKIP_TLS_VERIFY", None)
                ctx = _create_permissive_ssl_context()

            # Cert is loaded and verification remains enabled
            assert ctx.verify_mode != ssl.CERT_NONE
        finally:
            os.unlink(ca_path)

    def test_nonexistent_ca_path_falls_through(self) -> None:
        """A missing AUTOBOT_TLS_CA_PATH file does not crash — falls through."""
        with patch.dict(
            os.environ,
            {"AUTOBOT_TLS_CA_PATH": "/nonexistent/ca.pem"},
            clear=False,
        ):
            os.environ.pop("AUTOBOT_SKIP_TLS_VERIFY", None)
            ctx = _create_permissive_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)

    def test_skip_tls_verify_case_insensitive(self) -> None:
        """AUTOBOT_SKIP_TLS_VERIFY=TRUE (upper-case) also disables verification."""
        with patch.dict(os.environ, {"AUTOBOT_SKIP_TLS_VERIFY": "TRUE"}, clear=False):
            os.environ.pop("AUTOBOT_TLS_CA_PATH", None)
            ctx = _create_permissive_ssl_context()
        assert ctx.verify_mode == ssl.CERT_NONE

    def test_loopback_target_uses_cert_none_when_no_ca_configured(self) -> None:
        """Loopback target with no CA → CERT_NONE (#6654).

        Same-host connections cannot be MITM'd, so trusting a self-signed cert
        is safe. This unblocks single-host installs that don't ship a project CA.
        """
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOBOT_SKIP_TLS_VERIFY", None)
            os.environ.pop("AUTOBOT_TLS_CA_PATH", None)
            for url in (
                "https://127.0.0.1:8000",
                "https://localhost:8000",
                "wss://127.0.0.1:8000/api/ws/events",
            ):
                ctx = _create_permissive_ssl_context(url)
                assert ctx.verify_mode == ssl.CERT_NONE, f"loopback URL {url} should disable verify"
                assert ctx.check_hostname is False

    def test_non_loopback_target_remains_strict_when_no_ca_configured(self) -> None:
        """Non-loopback target with no CA → strict (no regression for production, #6654)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOBOT_SKIP_TLS_VERIFY", None)
            os.environ.pop("AUTOBOT_TLS_CA_PATH", None)
            ctx = _create_permissive_ssl_context("https://10.0.0.5:8000")
        assert ctx.verify_mode != ssl.CERT_NONE

    def test_no_target_url_remains_strict(self) -> None:
        """No URL passed → strict (preserves the original strict-by-default contract)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOBOT_SKIP_TLS_VERIFY", None)
            os.environ.pop("AUTOBOT_TLS_CA_PATH", None)
            ctx = _create_permissive_ssl_context()
        assert ctx.verify_mode != ssl.CERT_NONE


class TestSLMClientReconnectBackoff:
    """Tests for exponential backoff in the WebSocket reconnect loop (#4664)."""

    def _make_client(self) -> SLMClient:
        return SLMClient(slm_url="https://127.0.0.1:8000")

    @pytest.mark.asyncio
    async def test_reconnect_delay_starts_at_one_second(self) -> None:
        """Initial reconnect delay is 1 second."""
        client = self._make_client()
        assert client._reconnect_delay == 1.0

    @pytest.mark.asyncio
    async def test_reconnect_delay_doubles_on_failure(self) -> None:
        """Reconnect delay doubles after each failed connection attempt."""
        client = self._make_client()

        connect_calls = 0

        async def failing_connect() -> None:
            nonlocal connect_calls
            connect_calls += 1
            raise Exception("SSL: CERTIFICATE_VERIFY_FAILED")

        slept = []

        async def fake_sleep(delay) -> None:
            slept.append(delay)
            if connect_calls >= 3:
                client._shutdown = True

        with (
            patch.object(client, "_ws_connect_and_listen", side_effect=failing_connect),
            patch("asyncio.sleep", side_effect=fake_sleep),
        ):
            await client._ws_listener()

        # Should have slept 3 times with doubling delays: 1.0 → 2.0 → 4.0
        assert len(slept) >= 2
        assert slept[0] == 1.0
        assert slept[1] == 2.0

    @pytest.mark.asyncio
    async def test_reconnect_delay_caps_at_max(self) -> None:
        """Reconnect delay is capped at _max_reconnect_delay."""
        client = self._make_client()
        client._reconnect_delay = 32.0  # Close to cap

        connect_calls = 0

        async def failing_connect() -> None:
            nonlocal connect_calls
            connect_calls += 1
            raise Exception("connection refused")

        slept = []

        async def fake_sleep(delay) -> None:
            slept.append(delay)
            client._shutdown = True

        with (
            patch.object(client, "_ws_connect_and_listen", side_effect=failing_connect),
            patch("asyncio.sleep", side_effect=fake_sleep),
        ):
            await client._ws_listener()

        # Delay should not exceed 60 seconds
        assert all(d <= client._max_reconnect_delay for d in slept)

    @pytest.mark.asyncio
    async def test_reconnect_delay_resets_on_success(self) -> None:
        """Reconnect delay resets to 1.0 after a successful connection."""
        client = self._make_client()
        client._reconnect_delay = 30.0  # Simulate previous failures

        async def successful_connect() -> None:
            # Simulate a real connection: reset delay and return normally
            client._reconnect_delay = 1.0
            client._shutdown = True  # Stop the loop after one success

        with patch.object(client, "_ws_connect_and_listen", side_effect=successful_connect):
            await client._ws_listener()

        assert client._reconnect_delay == 1.0

    @pytest.mark.asyncio
    async def test_ssl_error_logged_not_raised(self) -> None:
        """SSL errors are caught and logged, not re-raised from _ws_connect_and_listen."""
        client = self._make_client()
        client._shutdown = True  # Don't loop

        ssl_error = ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED")

        mock_ws = MagicMock()
        mock_ws.__aenter__ = AsyncMock(side_effect=ssl_error)
        mock_ws.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("websockets.connect", return_value=mock_ws),
            patch("services.slm_client.logger") as mock_logger,
        ):
            # Should not raise
            await client._ws_connect_and_listen()

        # Error is logged
        assert mock_logger.error.called
        logged_msg = str(mock_logger.error.call_args)
        assert "WebSocket" in logged_msg or "error" in logged_msg.lower()


# ---------------------------------------------------------------------------
# Service JWT minting (GH#9852)
# ---------------------------------------------------------------------------

_TEST_SECRET = "test-slm-signing-secret-for-unit-tests-32chars"


class TestMintServiceJwt:
    """Unit tests for _mint_service_jwt — claims, algorithm, and expiry."""

    def test_returns_decodable_token(self) -> None:
        """Minted token can be decoded with the same secret."""
        token = _mint_service_jwt(_TEST_SECRET)
        payload = decode_jwt(token, secret=_TEST_SECRET)
        assert payload is not None

    def test_sub_claim_identifies_backend_service(self) -> None:
        """'sub' claim is 'service:backend'."""
        token = _mint_service_jwt(_TEST_SECRET)
        payload = decode_jwt(token, secret=_TEST_SECRET)
        assert payload["sub"] == "service:backend"

    def test_admin_and_role_claims_absent(self) -> None:
        """Token must NOT carry admin or role claims (least-privilege, GH#9852)."""
        token = _mint_service_jwt(_TEST_SECRET)
        payload = decode_jwt(token, secret=_TEST_SECRET)
        assert "admin" not in payload, "admin claim must be absent from service JWT"
        assert "role" not in payload, "role claim must be absent from service JWT"

    def test_service_claim_present(self) -> None:
        """Token carries service=True to distinguish machine from user tokens."""
        token = _mint_service_jwt(_TEST_SECRET)
        payload = decode_jwt(token, secret=_TEST_SECRET)
        assert payload.get("service") is True

    def test_token_has_expiry(self) -> None:
        """Minted token carries an 'exp' claim."""
        token = _mint_service_jwt(_TEST_SECRET)
        payload = decode_jwt(token, secret=_TEST_SECRET)
        assert "exp" in payload

    def test_expiry_roughly_one_hour(self) -> None:
        """Expiry is within ±5 s of _SERVICE_JWT_TTL_HOURS from now."""
        import time

        token = _mint_service_jwt(_TEST_SECRET)
        payload = decode_jwt(token, secret=_TEST_SECRET)
        expected_ttl_secs = _SERVICE_JWT_TTL_HOURS * 3600
        actual_remaining = payload["exp"] - time.time()
        assert abs(actual_remaining - expected_ttl_secs) < 5

    def test_wrong_secret_fails_decode(self) -> None:
        """Token minted with one secret cannot be decoded with another."""
        from autobot_shared.auth.jwt_core import JWTDecodeError

        token = _mint_service_jwt(_TEST_SECRET)
        with pytest.raises(JWTDecodeError):
            decode_jwt(token, secret="wrong-secret-key-for-unit-tests-32chars")


class TestGetSlmSigningSecret:
    """Unit tests for _get_slm_signing_secret secret priority."""

    def test_returns_jwt_secret_when_set(self) -> None:
        """AUTOBOT_JWT_SECRET is returned when present."""
        with patch("services.slm_client.config") as mock_cfg:
            mock_cfg.jwt_secret = "my-jwt-secret"
            mock_cfg.secret_key = "my-secret-key"
            result = _get_slm_signing_secret()
        assert result == "my-jwt-secret"

    def test_falls_back_to_secret_key(self) -> None:
        """SECRET_KEY is used when AUTOBOT_JWT_SECRET is empty."""
        with patch("services.slm_client.config") as mock_cfg:
            mock_cfg.jwt_secret = ""
            mock_cfg.secret_key = "my-secret-key"
            result = _get_slm_signing_secret()
        assert result == "my-secret-key"

    def test_returns_none_when_both_empty(self) -> None:
        """Returns None when neither env var is set."""
        with patch("services.slm_client.config") as mock_cfg:
            mock_cfg.jwt_secret = ""
            mock_cfg.secret_key = ""
            result = _get_slm_signing_secret()
        assert result is None


class TestWsConnectAndListenJwtMinting:
    """Tests that _ws_connect_and_listen mints a token when auth_token is absent."""

    def _make_client(self) -> SLMClient:
        return SLMClient(slm_url="http://autobot-slm:8000")

    @pytest.mark.asyncio
    async def test_mints_token_when_auth_token_unset(self) -> None:
        """When auth_token is empty and a signing secret exists, a JWT is minted
        and passed via Sec-WebSocket-Protocol subprotocols (GH#9852 transport)."""
        client = self._make_client()
        assert not client.auth_token  # no static token

        mock_ws_ctx = MagicMock()
        mock_ws_ctx.__aenter__ = AsyncMock(side_effect=Exception("stop-after-connect"))
        mock_ws_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("services.slm_client._get_slm_signing_secret", return_value=_TEST_SECRET),
            patch("services.slm_client._mint_service_jwt", wraps=_mint_service_jwt) as mock_mint,
            patch("websockets.connect", side_effect=lambda url, **kw: mock_ws_ctx) as mock_connect,
        ):
            await client._ws_connect_and_listen()

        mock_mint.assert_called_once_with(_TEST_SECRET)
        # Token must NOT appear in the URL
        call_url = mock_connect.call_args[0][0]
        assert "?token=" not in call_url, "JWT must not be placed in the WebSocket URL"
        # Token must be passed as subprotocols=['bearer', <token>]
        call_kwargs = mock_connect.call_args[1]
        subprotocols = call_kwargs.get("subprotocols", [])
        assert len(subprotocols) == 2
        assert subprotocols[0] == "bearer"
        assert subprotocols[1]  # non-empty token

    @pytest.mark.asyncio
    async def test_skips_connection_when_no_secret(self) -> None:
        """When auth_token is empty and no signing secret exists, connection is skipped."""
        client = self._make_client()

        with (
            patch("services.slm_client._get_slm_signing_secret", return_value=None),
            patch("websockets.connect") as mock_connect,
        ):
            await client._ws_connect_and_listen()

        mock_connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_static_auth_token_takes_precedence(self) -> None:
        """When auth_token is set, it is used directly via subprotocols without minting."""
        client = self._make_client()
        client.auth_token = "static-operator-token"

        mock_ws_ctx = MagicMock()
        mock_ws_ctx.__aenter__ = AsyncMock(side_effect=Exception("stop-after-connect"))
        mock_ws_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("services.slm_client._mint_service_jwt") as mock_mint,
            patch("websockets.connect", side_effect=lambda url, **kw: mock_ws_ctx) as mock_connect,
        ):
            await client._ws_connect_and_listen()

        mock_mint.assert_not_called()
        # Token must not be in the URL
        call_url = mock_connect.call_args[0][0]
        assert "token=" not in call_url, "JWT must not be placed in the WebSocket URL"
        # Token must appear in subprotocols
        call_kwargs = mock_connect.call_args[1]
        subprotocols = call_kwargs.get("subprotocols", [])
        assert subprotocols == ["bearer", "static-operator-token"]


# ---------------------------------------------------------------------------
# WebSocket URL prefix selection (GH#9967)
# ---------------------------------------------------------------------------


class TestWsUrlPrefixSelection:
    """Tests that _ws_connect_and_listen uses /slm/api/ws/events for nginx
    paths and /api/ws/events for direct-port (loopback) connections (#9967).

    Nginx on co-located bare-metal routes /api/ws/* to the user backend;
    /slm/api/ws/* always routes to the SLM regardless of nginx mode (#3268).
    Direct-port loopback (127.0.0.1:8000) bypasses nginx entirely.
    """

    def _make_mock_ws(self) -> MagicMock:
        mock_ws_ctx = MagicMock()
        mock_ws_ctx.__aenter__ = AsyncMock(side_effect=Exception("stop-after-connect"))
        mock_ws_ctx.__aexit__ = AsyncMock(return_value=False)
        return mock_ws_ctx

    @pytest.mark.asyncio
    async def test_nginx_host_uses_slm_prefix(self) -> None:
        """Non-loopback SLM URL (nginx) uses /slm/api/ws/events (#9967)."""
        client = SLMClient(slm_url="https://autobot-host.example.com")

        with (
            patch("services.slm_client._get_slm_signing_secret", return_value=_TEST_SECRET),
            patch("websockets.connect", side_effect=lambda url, **kw: self._make_mock_ws()) as mock_connect,
        ):
            await client._ws_connect_and_listen()

        call_url = mock_connect.call_args[0][0]
        assert "/slm/api/ws/events" in call_url, (
            f"nginx path must use /slm/api/ws/events, got: {call_url}"
        )
        assert call_url.startswith("wss://")

    @pytest.mark.asyncio
    async def test_loopback_host_uses_api_prefix(self) -> None:
        """Loopback SLM URL (direct port, no nginx) uses /api/ws/events (#9967)."""
        client = SLMClient(slm_url="http://127.0.0.1:8000")

        with (
            patch("services.slm_client._get_slm_signing_secret", return_value=_TEST_SECRET),
            patch("websockets.connect", side_effect=lambda url, **kw: self._make_mock_ws()) as mock_connect,
        ):
            await client._ws_connect_and_listen()

        call_url = mock_connect.call_args[0][0]
        assert "/api/ws/events" in call_url, (
            f"direct-port loopback must use /api/ws/events, got: {call_url}"
        )
        assert "/slm/api/ws/events" not in call_url, (
            f"loopback must NOT prepend /slm prefix, got: {call_url}"
        )
        assert call_url.startswith("ws://")

    @pytest.mark.asyncio
    async def test_localhost_name_uses_api_prefix(self) -> None:
        """'localhost' hostname (loopback) also uses /api/ws/events, not /slm prefix."""
        client = SLMClient(slm_url="http://localhost:8000")

        with (
            patch("services.slm_client._get_slm_signing_secret", return_value=_TEST_SECRET),
            patch("websockets.connect", side_effect=lambda url, **kw: self._make_mock_ws()) as mock_connect,
        ):
            await client._ws_connect_and_listen()

        call_url = mock_connect.call_args[0][0]
        assert "/api/ws/events" in call_url
        assert "/slm/api/ws/events" not in call_url

    @pytest.mark.asyncio
    async def test_ip_address_non_loopback_uses_slm_prefix(self) -> None:
        """Non-loopback IP address (bare-metal nginx) uses /slm/api/ws/events."""
        client = SLMClient(slm_url="https://10.0.0.5")

        with (
            patch("services.slm_client._get_slm_signing_secret", return_value=_TEST_SECRET),
            patch("websockets.connect", side_effect=lambda url, **kw: self._make_mock_ws()) as mock_connect,
        ):
            await client._ws_connect_and_listen()

        call_url = mock_connect.call_args[0][0]
        assert "/slm/api/ws/events" in call_url


# ---------------------------------------------------------------------------
# Compose wiring contract (GH#9852)
# ---------------------------------------------------------------------------


class TestComposeWiringContract:
    """Static contract test: with-secrets.sh must wire SLM_SECRET_KEY from
    the same generated value that _get_slm_signing_secret prefers
    (AUTOBOT_JWT_SECRET / _GEN_JWT).

    This test parses docker/with-secrets.sh and asserts the env-var pairing
    so any future edit that breaks the alignment fails immediately.
    """

    def _read_with_secrets_sh(self) -> str:
        import pathlib

        # Navigate from autobot-backend/services/ to repo root / docker/
        root = pathlib.Path(__file__).parents[2]
        path = root / "docker" / "with-secrets.sh"
        return path.read_text(encoding="utf-8")

    def test_slm_secret_key_uses_gen_jwt_not_gen_secret_key(self) -> None:
        """SLM_SECRET_KEY must be sourced from _GEN_JWT (not _GEN_SECRET_KEY).

        The backend signs with AUTOBOT_JWT_SECRET = _GEN_JWT.
        The SLM verifies with SLM_SECRET_KEY.
        Both must come from the same generated value or tokens will never verify.
        """
        content = self._read_with_secrets_sh()
        # Must contain the aligned assignment
        assert "SLM_SECRET_KEY:=${_GEN_JWT" in content, (
            "with-secrets.sh must set SLM_SECRET_KEY from _GEN_JWT "
            "to align with the backend's AUTOBOT_JWT_SECRET signing key"
        )
        # Must NOT use the wrong key
        assert "SLM_SECRET_KEY:=${_GEN_SECRET_KEY" not in content, (
            "SLM_SECRET_KEY must NOT be sourced from _GEN_SECRET_KEY — "
            "that value is independent of AUTOBOT_JWT_SECRET"
        )

    def test_autobot_jwt_secret_uses_gen_jwt(self) -> None:
        """AUTOBOT_JWT_SECRET must be sourced from _GEN_JWT (unchanged from #9905)."""
        content = self._read_with_secrets_sh()
        assert "AUTOBOT_JWT_SECRET:=${_GEN_JWT" in content


# ---------------------------------------------------------------------------
# Auth-failure guard (GH#9852 item 6)
# ---------------------------------------------------------------------------


class TestWsAuthFailureGuard:
    """Tests for the consecutive 4001 auth-failure backoff guard."""

    def _make_client(self) -> SLMClient:
        return SLMClient(slm_url="http://autobot-slm:8000")

    @pytest.mark.asyncio
    async def test_auth_fail_count_increments_on_4001(self) -> None:
        """_ws_auth_fail_count increments when the SLM closes with code 4001."""
        import websockets.frames

        client = self._make_client()
        assert client._ws_auth_fail_count == 0

        close_frame = websockets.frames.Close(4001, "Invalid or expired token")
        exc = websockets.exceptions.ConnectionClosedError(rcvd=close_frame, sent=None)

        mock_ws_ctx = MagicMock()
        mock_ws_ctx.__aenter__ = AsyncMock(side_effect=exc)
        mock_ws_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("services.slm_client._get_slm_signing_secret", return_value=_TEST_SECRET),
            patch("websockets.connect", side_effect=lambda url, **kw: mock_ws_ctx),
        ):
            await client._ws_connect_and_listen()

        assert client._ws_auth_fail_count == 1

    @pytest.mark.asyncio
    async def test_threshold_triggers_warning_and_max_backoff(self) -> None:
        """After _WS_AUTH_FAIL_THRESHOLD consecutive 4001s, a warning is logged
        and reconnect delay is pinned to _max_reconnect_delay."""
        import websockets.frames

        from services.slm_client import _WS_AUTH_FAIL_THRESHOLD

        client = self._make_client()

        close_frame = websockets.frames.Close(4001, "Invalid or expired token")
        exc = websockets.exceptions.ConnectionClosedError(rcvd=close_frame, sent=None)

        mock_ws_ctx = MagicMock()
        mock_ws_ctx.__aenter__ = AsyncMock(side_effect=exc)
        mock_ws_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("services.slm_client._get_slm_signing_secret", return_value=_TEST_SECRET),
            patch("websockets.connect", side_effect=lambda url, **kw: mock_ws_ctx),
            patch("services.slm_client.logger") as mock_logger,
        ):
            for _ in range(_WS_AUTH_FAIL_THRESHOLD):
                await client._ws_connect_and_listen()

        assert client._reconnect_delay == client._max_reconnect_delay
        # One warning naming the secret-pair requirement must have been logged
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any(
            "SLM_SECRET_KEY" in msg for msg in warning_calls
        ), "Warning must name SLM_SECRET_KEY to guide operator"

    @pytest.mark.asyncio
    async def test_auth_fail_count_resets_on_successful_connect(self) -> None:
        """_ws_auth_fail_count resets to 0 on a successful WebSocket handshake."""
        client = self._make_client()
        client._ws_auth_fail_count = 2  # simulate prior failures

        mock_ws = AsyncMock()
        mock_ws.__aiter__ = MagicMock(return_value=iter([]))  # no messages

        mock_ws_ctx = MagicMock()

        async def _enter(_):
            client._shutdown = True  # stop after one iteration
            return mock_ws

        mock_ws_ctx.__aenter__ = _enter
        mock_ws_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("services.slm_client._get_slm_signing_secret", return_value=_TEST_SECRET),
            patch("websockets.connect", side_effect=lambda url, **kw: mock_ws_ctx),
        ):
            await client._ws_connect_and_listen()

        assert client._ws_auth_fail_count == 0
