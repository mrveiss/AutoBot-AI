# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for the shared HMAC-SHA256 signing helper (Issue #3827).

Covers:
  - ``autobot_shared.http_client.sign_request`` standalone correctness
  - ``ServiceHTTPClient._sign_request`` delegates to the shared helper
    (algorithm parity with ``ServiceAuthManager.generate_signature``)
"""

import hashlib
import hmac
import time
from unittest.mock import MagicMock, patch

from autobot_shared.http_client import sign_request


class TestSignRequestHelper:
    """Pure-function tests for autobot_shared.http_client.sign_request."""

    def _expected_signature(
        self,
        service_id: str,
        service_key: str,
        method: str,
        path: str,
        timestamp: int,
    ) -> str:
        message = f"{service_id}:{method}:{path}:{timestamp}"
        return hmac.new(
            service_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def test_returns_three_headers(self):
        headers = sign_request("svc-a", "deadbeef" * 8, "GET", "/api/x", 1700000000)
        assert set(headers.keys()) == {
            "X-Service-ID",
            "X-Service-Signature",
            "X-Service-Timestamp",
        }

    def test_service_id_header_value(self):
        headers = sign_request("main-backend", "key123", "POST", "/infer", 1700000000)
        assert headers["X-Service-ID"] == "main-backend"

    def test_timestamp_header_is_string(self):
        ts = 1700000042
        headers = sign_request("svc", "key", "GET", "/", ts)
        assert headers["X-Service-Timestamp"] == str(ts)

    def test_signature_matches_manual_hmac(self):
        service_id = "npu-worker"
        service_key = "abc123def456" * 4
        method = "POST"
        path = "/api/process"
        timestamp = 1700001234

        headers = sign_request(service_id, service_key, method, path, timestamp)
        expected = self._expected_signature(service_id, service_key, method, path, timestamp)
        assert headers["X-Service-Signature"] == expected

    def test_signature_is_hex_string(self):
        headers = sign_request("svc", "key", "GET", "/", 1700000000)
        sig = headers["X-Service-Signature"]
        # SHA-256 hex digest is always 64 lowercase hex characters
        assert len(sig) == 64
        assert all(c in "0123456789abcdef" for c in sig)

    def test_different_methods_produce_different_signatures(self):
        get_sig = sign_request(*("svc", "key", "GET", "/path", 1700000000))["X-Service-Signature"]
        post_sig = sign_request(*("svc", "key", "POST", "/path", 1700000000))["X-Service-Signature"]
        assert get_sig != post_sig

    def test_different_timestamps_produce_different_signatures(self):
        sig1 = sign_request("svc", "key", "GET", "/", 1700000000)["X-Service-Signature"]
        sig2 = sign_request("svc", "key", "GET", "/", 1700000001)["X-Service-Signature"]
        assert sig1 != sig2

    def test_different_paths_produce_different_signatures(self):
        sig1 = sign_request("svc", "key", "GET", "/a", 1700000000)["X-Service-Signature"]
        sig2 = sign_request("svc", "key", "GET", "/b", 1700000000)["X-Service-Signature"]
        assert sig1 != sig2

    def test_parity_with_service_auth_manager(self):
        """sign_request must produce the same digest as ServiceAuthManager.generate_signature."""
        from security.service_auth import ServiceAuthManager

        service_id = "main-backend"
        service_key = "cafebabe" * 8
        method = "DELETE"
        path = "/api/session/42"
        timestamp = 1700005000

        auth_mgr = ServiceAuthManager(redis_client=None)
        expected = auth_mgr.generate_signature(service_id, service_key, method, path, timestamp)
        actual = sign_request(service_id, service_key, method, path, timestamp)["X-Service-Signature"]
        assert actual == expected


class TestServiceHTTPClientSignRequest:
    """ServiceHTTPClient._sign_request must delegate to the shared helper."""

    def _make_service_client(self) -> "ServiceHTTPClient":
        from utils.service_client import ServiceHTTPClient

        # Patch get_http_client so ServiceHTTPClient.__init__ doesn't try to
        # create a real HTTPClientManager (which would need an event loop).
        with patch("utils.service_client.get_http_client", return_value=MagicMock()):
            return ServiceHTTPClient(
                service_id="test-service",
                service_key="deadcafe" * 8,
            )

    def test_sign_request_calls_shared_helper(self):
        client = self._make_service_client()
        url = "http://10.0.0.5:8080/api/inference"

        with patch("utils.service_client._sign_request", wraps=sign_request) as mock_helper:
            client._sign_request("POST", url)

        mock_helper.assert_called_once()
        call_args = mock_helper.call_args
        assert call_args[0][0] == "test-service"
        assert call_args[0][2] == "POST"
        assert call_args[0][3] == "/api/inference"

    def test_sign_request_returns_correct_headers(self):
        client = self._make_service_client()
        url = "http://10.0.0.5:8080/api/inference"

        headers = client._sign_request("GET", url)

        assert headers["X-Service-ID"] == "test-service"
        assert "X-Service-Signature" in headers
        assert "X-Service-Timestamp" in headers
        assert len(headers["X-Service-Signature"]) == 64

    def test_sign_request_path_only_not_full_url(self):
        """Only the path component must go into the HMAC — not host or query string."""
        client = self._make_service_client()
        url = "http://10.0.0.5:9000/api/process?debug=true"

        headers = client._sign_request("POST", url)
        timestamp = int(headers["X-Service-Timestamp"])

        # Recompute expected signature using path only
        expected_headers = sign_request("test-service", "deadcafe" * 8, "POST", "/api/process", timestamp)
        assert headers["X-Service-Signature"] == expected_headers["X-Service-Signature"]

    def test_timestamp_is_recent(self):
        client = self._make_service_client()
        before = int(time.time())
        headers = client._sign_request("GET", "http://10.0.0.1/x")
        after = int(time.time())

        ts = int(headers["X-Service-Timestamp"])
        assert before <= ts <= after
