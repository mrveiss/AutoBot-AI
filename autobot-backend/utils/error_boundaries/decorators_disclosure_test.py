# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``with_error_handling`` must not reflect internals to HTTP clients (#13740).

The decorator wraps 1900+ endpoints, so whatever it puts in the response body is
the API's default disclosure posture. It used to interpolate the caught
exception's type and message into ``message`` and repeat both under ``details``
— install paths, DSNs, Redis database indices and ORM column names all reached
the caller verbatim.

Debuggability is the other half of the contract: these tests also assert the
cause is still logged, against the trace_id the client is handed.
"""

import logging

import pytest
from fastapi import HTTPException

from utils.error_boundaries.decorators import with_error_handling
from utils.error_boundaries.types import APIErrorResponse, ErrorCategory

# A message shaped like the ones that actually leak here.
_LEAKY = "could not connect to /opt/autobot/run/redis.sock db=4 user=autobot_admin"


@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="leaky_operation")
async def _endpoint_that_fails():
    raise ConnectionError(_LEAKY)


@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="deliberate_operation")
async def _endpoint_that_raises_http():
    raise HTTPException(status_code=404, detail="Widget 7 not found")


def _body(exc: HTTPException) -> dict:
    return exc.detail["error"]


@pytest.mark.asyncio
async def test_the_exception_message_does_not_reach_the_client():
    with pytest.raises(HTTPException) as caught:
        await _endpoint_that_fails()

    rendered = str(caught.value.detail)
    assert _LEAKY not in rendered
    for fragment in ("/opt/autobot", "redis.sock", "db=4", "autobot_admin"):
        assert fragment not in rendered, fragment


@pytest.mark.asyncio
async def test_the_exception_type_does_not_reach_the_client():
    """The class name alone still tells a caller which subsystem failed."""
    with pytest.raises(HTTPException) as caught:
        await _endpoint_that_fails()

    assert "ConnectionError" not in str(caught.value.detail)
    assert "exception_type" not in _body(caught.value).get("details", {})
    assert "exception_message" not in _body(caught.value).get("details", {})


@pytest.mark.asyncio
async def test_the_client_still_gets_a_usable_error():
    with pytest.raises(HTTPException) as caught:
        await _endpoint_that_fails()

    body = _body(caught.value)
    assert caught.value.status_code == 500
    assert body["message"] == APIErrorResponse.get_client_message_for_category(ErrorCategory.SERVER_ERROR)
    assert body["details"]["operation"] == "leaky_operation"
    assert body["trace_id"].startswith("leaky_operation_")
    assert body["code"].startswith("API_")


@pytest.mark.asyncio
async def test_the_cause_is_still_logged_against_the_same_trace_id(caplog):
    """No diagnostic capability is lost — it moves from the body to the log."""
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as caught:
            await _endpoint_that_fails()

    trace_id = _body(caught.value)["trace_id"]
    logged = "\n".join(r.getMessage() for r in caplog.records)

    assert _LEAKY in logged, "the cause must survive somewhere"
    assert "ConnectionError" in logged
    assert trace_id in logged, "a bug report quoting the trace_id must resolve to this record"
    assert any(r.exc_info for r in caplog.records), "traceback not captured"


@pytest.mark.asyncio
async def test_a_deliberate_http_exception_is_untouched():
    """Endpoints that raise their own HTTPException still speak to the caller."""
    with pytest.raises(HTTPException) as caught:
        await _endpoint_that_raises_http()

    assert caught.value.status_code == 404
    assert caught.value.detail == "Widget 7 not found"


@pytest.mark.parametrize(
    ("category", "status"),
    [
        (ErrorCategory.VALIDATION, 400),
        (ErrorCategory.NOT_FOUND, 404),
        (ErrorCategory.RATE_LIMIT, 429),
        (ErrorCategory.SERVER_ERROR, 500),
    ],
)
def test_every_category_has_a_static_message(category, status):
    message = APIErrorResponse.get_client_message_for_category(category)
    assert message
    assert APIErrorResponse.get_status_code_for_category(category) == status


def test_the_sync_wrapper_is_sanitised_too():
    """1913 call sites; the sync path must not be the one that still leaks."""

    @with_error_handling(category=ErrorCategory.DATABASE, operation="sync_operation")
    def _sync_endpoint():
        raise RuntimeError(_LEAKY)

    with pytest.raises(HTTPException) as caught:
        _sync_endpoint()

    assert _LEAKY not in str(caught.value.detail)
    assert "RuntimeError" not in str(caught.value.detail)
