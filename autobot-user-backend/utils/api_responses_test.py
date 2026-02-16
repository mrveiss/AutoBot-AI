"""
Tests for API Response Utilities

Verifies that API response factories provide correct structure, status codes,
and content for all response types.
"""

import json

import pytest
from fastapi import status
from fastapi.responses import JSONResponse

from backend.utils.api_responses import (
    ErrorResponse,
    PaginatedResponse,
    StandardResponse,
    bad_request,
    conflict,
    error_response,
    forbidden,
    internal_error,
    not_found,
    paginated_response,
    raise_bad_request,
    raise_conflict,
    raise_forbidden,
    raise_internal_error,
    raise_not_found,
    raise_unauthorized,
    service_unavailable,
    success_response,
    unauthorized,
)


class TestSuccessResponse:
    """Test suite for success_response()"""

    def test_basic_success_response(self):
        """Test basic success response"""
        response = success_response()

        assert isinstance(response, JSONResponse)
        assert response.status_code == status.HTTP_200_OK

        # Parse JSON content
        content = json.loads(response.body.decode())

        assert content["success"] is True
        assert "timestamp" in content
        assert content.get("data") is None
        assert content.get("message") is None

    def test_success_response_with_data(self):
        """Test success response with data"""
        test_data = {"id": "123", "name": "Test"}
        response = success_response(data=test_data)

        content = json.loads(response.body.decode())

        assert content["success"] is True
        assert content["data"] == test_data

    def test_success_response_with_message(self):
        """Test success response with message"""
        response = success_response(message="Operation completed")

        content = json.loads(response.body.decode())

        assert content["success"] is True
        assert content["message"] == "Operation completed"

    def test_success_response_with_custom_status_code(self):
        """Test success response with custom status code"""
        response = success_response(status_code=201)

        assert response.status_code == status.HTTP_201_CREATED

    def test_success_response_with_additional_fields(self):
        """Test success response with extra fields"""
        response = success_response(
            data={"item": "test"}, workflow_id="abc123", execution_time=1.5
        )

        content = json.loads(response.body.decode())

        assert content["success"] is True
        assert content["workflow_id"] == "abc123"
        assert content["execution_time"] == 1.5

    def test_success_response_content_type(self):
        """Test success response has correct content type"""
        response = success_response()

        assert response.media_type == "application/json; charset=utf-8"


class TestPaginatedResponse:
    """Test suite for paginated_response()"""

    def test_basic_pagination(self):
        """Test basic pagination"""
        items = [{"id": i} for i in range(20)]
        response = paginated_response(items=items, total=100, page=1, page_size=20)

        content = json.loads(response.body.decode())

        assert content["success"] is True
        assert len(content["data"]) == 20
        assert content["pagination"]["page"] == 1
        assert content["pagination"]["page_size"] == 20
        assert content["pagination"]["total_items"] == 100
        assert content["pagination"]["total_pages"] == 5
        assert content["pagination"]["has_next"] is True
        assert content["pagination"]["has_previous"] is False

    def test_pagination_last_page(self):
        """Test pagination on last page"""
        items = [{"id": i} for i in range(10)]
        response = paginated_response(items=items, total=100, page=5, page_size=20)

        content = json.loads(response.body.decode())

        assert content["pagination"]["page"] == 5
        assert content["pagination"]["has_next"] is False
        assert content["pagination"]["has_previous"] is True

    def test_pagination_middle_page(self):
        """Test pagination on middle page"""
        items = [{"id": i} for i in range(20)]
        response = paginated_response(items=items, total=100, page=3, page_size=20)

        content = json.loads(response.body.decode())

        assert content["pagination"]["page"] == 3
        assert content["pagination"]["has_next"] is True
        assert content["pagination"]["has_previous"] is True

    def test_pagination_with_message(self):
        """Test pagination with message"""
        items = [{"id": 1}]
        response = paginated_response(
            items=items, total=1, page=1, page_size=20, message="Workflows retrieved"
        )

        content = json.loads(response.body.decode())

        assert content["message"] == "Workflows retrieved"


class TestErrorResponse:
    """Test suite for error_response()"""

    def test_basic_error_response(self):
        """Test basic error response"""
        response = error_response(message="Something went wrong")

        assert isinstance(response, JSONResponse)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        content = json.loads(response.body.decode())

        assert content["success"] is False
        assert content["error"] == "Something went wrong"
        assert "timestamp" in content

    def test_error_response_with_custom_status_code(self):
        """Test error response with custom status code"""
        response = error_response(message="Not found", status_code=404)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_error_response_with_error_code(self):
        """Test error response with error code"""
        response = error_response(
            message="Resource not found", error_code="RESOURCE_404"
        )

        content = json.loads(response.body.decode())

        assert content["error_code"] == "RESOURCE_404"

    def test_error_response_with_details(self):
        """Test error response with details"""
        details = {"field": "username", "issue": "too_short"}
        response = error_response(message="Validation error", details=details)

        content = json.loads(response.body.decode())

        assert content["details"] == details


class TestNotFoundHelper:
    """Test suite for not_found()"""

    def test_not_found_default(self):
        """Test not_found with default message"""
        response = not_found()

        assert response.status_code == status.HTTP_404_NOT_FOUND

        content = json.loads(response.body.decode())

        assert content["success"] is False
        assert content["error"] == "Resource not found"

    def test_not_found_custom_message(self):
        """Test not_found with custom message"""
        response = not_found("Workflow not found")

        content = json.loads(response.body.decode())

        assert content["error"] == "Workflow not found"

    def test_not_found_with_error_code(self):
        """Test not_found with error code"""
        response = not_found("Workflow not found", error_code="WORKFLOW_404")

        content = json.loads(response.body.decode())

        assert content["error_code"] == "WORKFLOW_404"


class TestBadRequestHelper:
    """Test suite for bad_request()"""

    def test_bad_request_default(self):
        """Test bad_request with default message"""
        response = bad_request()

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        content = json.loads(response.body.decode())

        assert content["success"] is False
        assert content["error"] == "Invalid request"

    def test_bad_request_with_details(self):
        """Test bad_request with validation details"""
        details = {"field": "email", "issue": "invalid_format"}
        response = bad_request("Invalid input", details=details)

        content = json.loads(response.body.decode())

        assert content["details"] == details


class TestUnauthorizedHelper:
    """Test suite for unauthorized()"""

    def test_unauthorized_default(self):
        """Test unauthorized with default message"""
        response = unauthorized()

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        content = json.loads(response.body.decode())

        assert content["success"] is False
        assert content["error"] == "Unauthorized"

    def test_unauthorized_custom_message(self):
        """Test unauthorized with custom message"""
        response = unauthorized("Invalid token", error_code="AUTH_INVALID_TOKEN")

        content = json.loads(response.body.decode())

        assert content["error"] == "Invalid token"
        assert content["error_code"] == "AUTH_INVALID_TOKEN"


class TestForbiddenHelper:
    """Test suite for forbidden()"""

    def test_forbidden_default(self):
        """Test forbidden with default message"""
        response = forbidden()

        assert response.status_code == status.HTTP_403_FORBIDDEN

        content = json.loads(response.body.decode())

        assert content["success"] is False
        assert content["error"] == "Forbidden"


class TestInternalErrorHelper:
    """Test suite for internal_error()"""

    def test_internal_error_default(self):
        """Test internal_error with default message"""
        response = internal_error()

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        content = json.loads(response.body.decode())

        assert content["success"] is False
        assert content["error"] == "Internal server error"

    def test_internal_error_with_details(self):
        """Test internal_error with error details"""
        details = {"component": "database", "error_type": "connection_timeout"}
        response = internal_error(
            "Database connection failed", error_code="DB_ERROR", details=details
        )

        content = json.loads(response.body.decode())

        assert content["error"] == "Database connection failed"
        assert content["error_code"] == "DB_ERROR"
        assert content["details"] == details


class TestConflictHelper:
    """Test suite for conflict()"""

    def test_conflict_default(self):
        """Test conflict with default message"""
        response = conflict()

        assert response.status_code == status.HTTP_409_CONFLICT

        content = json.loads(response.body.decode())

        assert content["success"] is False
        assert content["error"] == "Resource conflict"

    def test_conflict_with_details(self):
        """Test conflict with details"""
        details = {"workflow_id": "abc123"}
        response = conflict(
            "Workflow already exists", error_code="WORKFLOW_EXISTS", details=details
        )

        content = json.loads(response.body.decode())

        assert content["error"] == "Workflow already exists"
        assert content["details"] == details


class TestServiceUnavailableHelper:
    """Test suite for service_unavailable()"""

    def test_service_unavailable_default(self):
        """Test service_unavailable with default message"""
        response = service_unavailable()

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

        content = json.loads(response.body.decode())

        assert content["success"] is False
        assert content["error"] == "Service temporarily unavailable"

    def test_service_unavailable_with_retry_after(self):
        """Test service_unavailable with Retry-After header"""
        response = service_unavailable("Redis connection unavailable", retry_after=30)

        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "30"


class TestRaiseHelpers:
    """Test suite for raise_* functions"""

    def test_raise_not_found(self):
        """Test raise_not_found raises HTTPException"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            raise_not_found("Resource not found")

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "Resource not found"

    def test_raise_bad_request(self):
        """Test raise_bad_request raises HTTPException"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            raise_bad_request("Invalid input")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == "Invalid input"

    def test_raise_unauthorized(self):
        """Test raise_unauthorized raises HTTPException"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            raise_unauthorized("Invalid token")

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    def test_raise_forbidden(self):
        """Test raise_forbidden raises HTTPException"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            raise_forbidden("Insufficient permissions")

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    def test_raise_internal_error(self):
        """Test raise_internal_error raises HTTPException"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            raise_internal_error("Database error")

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_raise_conflict(self):
        """Test raise_conflict raises HTTPException"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            raise_conflict("Resource already exists")

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT


class TestPydanticModels:
    """Test suite for Pydantic response models"""

    def test_standard_response_model(self):
        """Test StandardResponse model"""
        response = StandardResponse(message="Success", data={"id": "123"})

        assert response.success is True
        assert response.message == "Success"
        assert response.data == {"id": "123"}
        assert response.timestamp is not None

    def test_error_response_model(self):
        """Test ErrorResponse model"""
        response = ErrorResponse(error="Something went wrong", error_code="ERROR_500")

        assert response.success is False
        assert response.error == "Something went wrong"
        assert response.error_code == "ERROR_500"
        assert response.timestamp is not None

    def test_paginated_response_model(self):
        """Test PaginatedResponse model"""
        response = PaginatedResponse(
            data=[{"id": 1}, {"id": 2}],
            pagination={
                "page": 1,
                "page_size": 20,
                "total_items": 100,
                "total_pages": 5,
                "has_next": True,
                "has_previous": False,
            },
        )

        assert response.success is True
        assert len(response.data) == 2
        assert response.pagination["page"] == 1
        assert response.timestamp is not None


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
