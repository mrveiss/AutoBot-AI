# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for autobot_shared.tls — canonical SSL context factory (#6702).

Lifted from services/slm_client_test.py::TestCreatePermissiveSslContext and
adapted to test get_internal_tls_context directly.
"""

import os
import ssl
import tempfile
from unittest.mock import patch

import pytest

from autobot_shared.tls import _is_loopback_target, get_internal_tls_context


class TestGetInternalTlsContext:
    """Tests for get_internal_tls_context trust hierarchy."""

    def test_returns_ssl_context(self) -> None:
        """Default call returns an ssl.SSLContext."""
        ctx = get_internal_tls_context()
        assert isinstance(ctx, ssl.SSLContext)

    def test_verification_enabled_by_default(self) -> None:
        """Without any env vars, verification is not disabled."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOBOT_SKIP_TLS_VERIFY", None)
            os.environ.pop("AUTOBOT_TLS_CA_PATH", None)
            ctx = get_internal_tls_context()
        assert ctx.verify_mode != ssl.CERT_NONE

    def test_skip_tls_verify_disables_verification(self) -> None:
        """AUTOBOT_SKIP_TLS_VERIFY=true disables cert verification."""
        with patch.dict(os.environ, {"AUTOBOT_SKIP_TLS_VERIFY": "true"}, clear=False):
            os.environ.pop("AUTOBOT_TLS_CA_PATH", None)
            ctx = get_internal_tls_context()
        assert ctx.verify_mode == ssl.CERT_NONE
        assert ctx.check_hostname is False

    def test_skip_tls_verify_case_insensitive(self) -> None:
        """AUTOBOT_SKIP_TLS_VERIFY=TRUE (upper-case) also disables verification."""
        with patch.dict(os.environ, {"AUTOBOT_SKIP_TLS_VERIFY": "TRUE"}, clear=False):
            os.environ.pop("AUTOBOT_TLS_CA_PATH", None)
            ctx = get_internal_tls_context()
        assert ctx.verify_mode == ssl.CERT_NONE

    def test_explicit_ca_path_loads_ca(self) -> None:
        """AUTOBOT_TLS_CA_PATH pointing to a valid CA cert is loaded."""
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
                ctx = get_internal_tls_context()

            assert ctx.verify_mode != ssl.CERT_NONE
        finally:
            os.unlink(ca_path)

    def test_explicit_ca_path_argument_takes_precedence(self) -> None:
        """Explicit ca_path= argument bypasses the env-var chain."""
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

            # Even with SKIP_TLS_VERIFY set, explicit ca_path wins
            with patch.dict(os.environ, {"AUTOBOT_SKIP_TLS_VERIFY": "true"}, clear=False):
                ctx = get_internal_tls_context(ca_path=ca_path)

            assert ctx.verify_mode != ssl.CERT_NONE
        finally:
            os.unlink(ca_path)

    def test_nonexistent_ca_path_falls_through(self) -> None:
        """A missing AUTOBOT_TLS_CA_PATH file does not crash — falls through."""
        with patch.dict(os.environ, {"AUTOBOT_TLS_CA_PATH": "/nonexistent/ca.pem"}, clear=False):
            os.environ.pop("AUTOBOT_SKIP_TLS_VERIFY", None)
            ctx = get_internal_tls_context()
        assert isinstance(ctx, ssl.SSLContext)

    def test_loopback_target_uses_cert_none_when_no_ca_configured(self) -> None:
        """Loopback target with no CA → CERT_NONE (#6654)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOBOT_SKIP_TLS_VERIFY", None)
            os.environ.pop("AUTOBOT_TLS_CA_PATH", None)
            for url in (
                "https://127.0.0.1:8000",
                "https://localhost:8000",
                "wss://127.0.0.1:8000/api/ws/events",
            ):
                ctx = get_internal_tls_context(url)
                assert ctx.verify_mode == ssl.CERT_NONE, f"loopback URL {url} should disable verify"
                assert ctx.check_hostname is False

    def test_non_loopback_target_remains_strict_when_no_ca_configured(self) -> None:
        """Non-loopback target with no CA → strict (production safety, #6654)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOBOT_SKIP_TLS_VERIFY", None)
            os.environ.pop("AUTOBOT_TLS_CA_PATH", None)
            ctx = get_internal_tls_context("https://10.0.0.5:8000")
        assert ctx.verify_mode != ssl.CERT_NONE

    def test_no_target_url_remains_strict(self) -> None:
        """No URL passed → strict (preserves original strict-by-default contract)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOBOT_SKIP_TLS_VERIFY", None)
            os.environ.pop("AUTOBOT_TLS_CA_PATH", None)
            ctx = get_internal_tls_context()
        assert ctx.verify_mode != ssl.CERT_NONE


class TestIsLoopbackTarget:
    """Tests for the loopback host detection helper."""

    def test_localhost(self) -> None:
        assert _is_loopback_target("https://localhost:8000") is True

    def test_127(self) -> None:
        assert _is_loopback_target("https://127.0.0.1:8000") is True

    def test_ipv6_loopback(self) -> None:
        assert _is_loopback_target("https://[::1]:8000") is True

    def test_non_loopback(self) -> None:
        assert _is_loopback_target("https://10.0.0.5:8000") is False

    def test_none_url(self) -> None:
        assert _is_loopback_target(None) is False

    def test_empty_string(self) -> None:
        assert _is_loopback_target("") is False
