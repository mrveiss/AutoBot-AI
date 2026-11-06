# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One app-wide 409 for a busy chat session, through the same decorator the routes use (#20862)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from chat_history.session_lease import ChatFileUnreadable, SessionLeaseLost, SessionLeaseTimeout, StaleGenerationError
from initialization.session_lease_handlers import register_session_lease_handlers


@pytest.fixture()
def client():
    app = FastAPI()
    register_session_lease_handlers(app)

    @app.get("/busy")
    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="busy", error_code_prefix="T")
    async def busy():
        raise SessionLeaseTimeout("s1", "backend-2-1:save_session:aa", 30.0)

    @app.get("/stale")
    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="stale", error_code_prefix="T")
    async def stale():
        raise StaleGenerationError("s1", 3, 7)

    @app.get("/lost")
    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="lost", error_code_prefix="T")
    async def lost():
        raise SessionLeaseLost("file lock on s1_chat.json was not free within 30.0s; nothing written")

    @app.get("/unreadable")
    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="unreadable", error_code_prefix="T")
    async def unreadable():
        raise ChatFileUnreadable("s1", ValueError("bad"))

    return TestClient(app, raise_server_exceptions=False)


def test_a_lease_timeout_is_a_409_naming_the_holder(client):
    response = client.get("/busy")
    assert response.status_code == 409
    assert "backend-2-1:save_session:aa" in response.json()["detail"]


def test_a_stale_generation_is_a_409(client):
    response = client.get("/stale")
    assert response.status_code == 409
    assert "older than the file's 7" in response.json()["detail"]


@pytest.mark.parametrize("path", ["/lost", "/unreadable"])
def test_every_other_lease_error_is_covered_by_the_same_handler(client, path):
    response = client.get(path)
    assert response.status_code == 409
    assert "s1" in response.json()["detail"]
