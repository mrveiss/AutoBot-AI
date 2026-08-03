# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for #13259: POST /auth/refresh discarded the refreshed JWT.

This is the user-visible half of #13259: response_model=DataResponse[AuthRefreshData]
validated the flat {"success", "token", "expiresIn"} dict against the
{success, data, message, timestamp} envelope, so `token` and `expiresIn` were
silently dropped on every call and the client never received the refreshed
JWT. The fix declares response_model=AuthRefreshData directly.
"""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import router


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/auth")
    return TestClient(app)


class TestRefreshTokenResponsePayload:
    def test_refresh_returns_the_new_jwt_and_expiry_on_the_wire(self):
        client = _make_client()

        mock_middleware = MagicMock()
        mock_middleware.create_jwt_token.return_value = "brand-new-jwt-token"
        mock_middleware.jwt_expiry_hours = 2

        with (
            patch(
                "api.auth._decode_refresh_token",
                return_value={"username": "alice", "role": "admin", "email": "alice@example.com"},
            ),
            patch("api.auth.get_auth_middleware", return_value=mock_middleware),
        ):
            response = client.post(
                "/api/auth/refresh",
                headers={"Authorization": "Bearer old-token"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["token"] == "brand-new-jwt-token"
        assert body["expiresIn"] == 2 * 3600
        assert body["success"] is True
        mock_middleware.create_jwt_token.assert_called_once()
