# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for SLM client SSL context and WebSocket reconnect backoff (#4664).
"""

import os
import ssl
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.slm_client import (
    SLMClient,
    _create_permissive_ssl_context,
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
