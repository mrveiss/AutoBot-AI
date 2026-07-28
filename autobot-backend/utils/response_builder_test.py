# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Tests for API Response Builder Utilities.

Covers the canonical response envelope (issue #12753 fork-convergence:
response_builder.py absorbed the unique capabilities of the retired
api_responses.py — bad_request_response/conflict_response, raise_*
HTTPException helpers, and **extra_fields passthrough).
"""

import json

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from utils.response_builder import (
    bad_request_response,
    conflict_response,
    created_response,
    error_response,
    forbidden_response,
    no_content_response,
    not_found_response,
    paginated_response,
    raise_bad_request,
    raise_conflict,
    raise_forbidden,
    raise_internal_error,
    raise_not_found,
    raise_unauthorized,
    server_error_response,
    service_unavailable_response,
    success_response,
    unauthorized_response,
    validation_error_response,
)


def _content(response: JSONResponse) -> dict:
    return json.loads(response.body.decode())


class TestSuccessResponse:
    def test_always_emits_full_envelope(self):
        response = success_response()
        content = _content(response)
        assert content["success"] is True
        assert content["data"] is None
        assert content["message"] is None
        assert content["error"] is None
        assert content["error_code"] is None
        assert "timestamp" in content

    def test_with_data_and_message(self):
        response = success_response(data={"id": "123"}, message="ok")
        content = _content(response)
        assert content["data"] == {"id": "123"}
        assert content["message"] == "ok"

    def test_extra_fields_merge(self):
        response = success_response(data={"id": "1"}, workflow_id="abc123")
        content = _content(response)
        assert content["workflow_id"] == "abc123"


class TestErrorResponse:
    def test_default_status_400(self):
        response = error_response("bad input")
        assert response.status_code == 400
        content = _content(response)
        assert content["success"] is False
        assert content["error"] == "bad input"

    def test_extra_fields_merge(self):
        response = error_response("boom", status_code=429, retry_after=30)
        content = _content(response)
        assert content["retry_after"] == 30


class TestPaginatedResponse:
    def test_pagination_keys_are_response_builder_shape(self):
        response = paginated_response(items=[1, 2], total=42, page=3, page_size=20)
        content = _content(response)
        pagination = content["data"]["pagination"]
        assert pagination["total"] == 42
        assert pagination["has_prev"] is True
        assert pagination["has_next"] is False
        assert content["data"]["items"] == [1, 2]


class TestBadRequestResponse:
    def test_bad_request_response(self):
        response = bad_request_response("Invalid input", error_code="BAD")
        assert response.status_code == 400
        content = _content(response)
        assert content["error"] == "Invalid input"
        assert content["error_code"] == "BAD"


class TestConflictResponse:
    def test_conflict_response(self):
        response = conflict_response("Already exists", error_code="EXISTS")
        assert response.status_code == 409
        content = _content(response)
        assert content["error_code"] == "EXISTS"


class TestConvenienceResponses:
    def test_not_found_response(self):
        response = not_found_response("Workflow", "abc")
        assert response.status_code == 404

    def test_unauthorized_response(self):
        assert unauthorized_response().status_code == 401

    def test_forbidden_response(self):
        assert forbidden_response().status_code == 403

    def test_server_error_response(self):
        assert server_error_response().status_code == 500

    def test_service_unavailable_response(self):
        response = service_unavailable_response("Redis", retry_after=30)
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "30"

    def test_validation_error_response(self):
        response = validation_error_response(["field required"])
        assert response.status_code == 422

    def test_created_response(self):
        response = created_response(data={"id": "1"}, location="/items/1")
        assert response.status_code == 201
        assert response.headers["location"] == "/items/1"

    def test_no_content_response(self):
        assert no_content_response().status_code == 204


class TestHTTPExceptionCompatibility:
    @pytest.mark.parametrize(
        "raiser,expected_status",
        [
            (raise_not_found, 404),
            (raise_bad_request, 400),
            (raise_unauthorized, 401),
            (raise_forbidden, 403),
            (raise_internal_error, 500),
            (raise_conflict, 409),
        ],
    )
    def test_raise_helpers_raise_http_exception(self, raiser, expected_status):
        with pytest.raises(HTTPException) as exc_info:
            raiser("boom")
        assert exc_info.value.status_code == expected_status
        assert exc_info.value.detail == "boom"
