# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One app-wide 409 for a busy chat session, through the same decorator the routes use (#20862)."""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from chat_history.session_lease import (
    ChatFileUnreadable,
    LeaseStoreUnavailable,
    SessionLeaseError,
    SessionLeaseLost,
    SessionLeaseTimeout,
    StaleGenerationError,
)
from initialization.session_lease_handlers import register_session_lease_handlers

_HOST, _PID = "node-zq7-internal", 48211
_HOLDER = "%s-%d:save_session:aa" % (_HOST, _PID)


@pytest.fixture()
def client():
    app = FastAPI()
    register_session_lease_handlers(app)

    @app.get("/busy")
    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="busy", error_code_prefix="T")
    async def busy():
        raise SessionLeaseTimeout("s1", _HOLDER, 30.0)

    @app.get("/stale")
    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="stale", error_code_prefix="T")
    async def stale():
        raise StaleGenerationError("s1", 3, 7)

    @app.get("/lost")
    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="lost", error_code_prefix="T")
    async def lost():
        raise SessionLeaseLost("file lock on s1_chat.json was not free within 30.0s; nothing written")

    @app.get("/forged")
    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="forged", error_code_prefix="T")
    async def forged():
        raise SessionLeaseTimeout("s\x1b[31m1\nFORGED", "backend-2-1:save_session:aa", 30.0)

    @app.get("/unreadable")
    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="unreadable", error_code_prefix="T")
    async def unreadable():
        raise ChatFileUnreadable("s1", ValueError("bad"))

    @app.get("/unreachable")
    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="unreachable", error_code_prefix="T")
    async def unreachable():
        raise LeaseStoreUnavailable("s1")

    @app.get("/misconfigured")
    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="misconfigured", error_code_prefix="T")
    async def misconfigured():
        raise SessionLeaseError("chat lease Redis database 'nope' is not a known database")

    return TestClient(app, raise_server_exceptions=False)


def test_a_lease_timeout_is_a_409_with_a_code_and_no_holder(client):
    response = client.get("/busy")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "chat_session_busy"
    assert _HOST not in response.text and str(_PID) not in response.text and "save_session" not in response.text


def test_the_holder_stays_in_the_server_log(client, caplog):
    client.get("/busy")
    assert _HOLDER in caplog.text


def test_control_the_old_handler_returned_the_holder_so_the_check_can_fail():
    app = FastAPI()

    @app.exception_handler(SessionLeaseTimeout)
    async def legacy(request, exc):  # the handler before this fix
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/busy")
    async def busy():
        raise SessionLeaseTimeout("s1", _HOLDER, 30.0)

    text = TestClient(app, raise_server_exceptions=False).get("/busy").text
    assert _HOST in text and str(_PID) in text


def test_a_stale_generation_is_a_409_without_generations(client):
    response = client.get("/stale")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "chat_session_conflict"
    assert "older than" not in response.text


def test_a_lost_lease_or_file_lock_is_still_a_409(client):
    response = client.get("/lost")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "chat_session_conflict" and "s1_chat" not in response.text


def test_an_unreachable_lease_store_is_a_503_not_a_conflict(client):
    response = client.get("/unreachable")
    assert response.status_code == 503 and response.json()["detail"]["code"] == "chat_session_store_unavailable"


def test_a_misconfigured_lease_database_is_a_typed_500_that_does_not_name_it(client):
    response = client.get("/misconfigured")  # a retry cannot fix it, so it is not a retryable 409
    assert response.status_code == 500 and response.json()["detail"]["code"] == "chat_session_lease_error"
    assert "nope" not in response.text


def test_an_unreadable_chat_file_is_a_typed_500_without_the_decode_cause(client):
    response = client.get("/unreadable")
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "chat_session_unreadable"
    assert "bad" not in response.text and "ValueError" not in response.text


def test_control_characters_in_the_path_or_the_session_id_do_not_reach_the_log(client, caplog):
    response = client.get("/forged")
    assert response.status_code == 409
    assert "\x1b" not in caplog.text and "\nFORGED" not in caplog.text
    assert "chat session write conflict" in caplog.text
