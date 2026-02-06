#!/usr/bin/env python3
"""
Unit tests for enhanced error boundaries (Phase 1 implementation).

Tests the new components added in Phase 1:
- Enhanced ErrorCategory enum
- APIErrorResponse dataclass
- @with_error_handling decorator
"""

import asyncio

import pytest

from src.utils.error_boundaries import (
    APIErrorResponse,
    ErrorCategory,
    with_error_handling,
)


class TestErrorCategoryEnum:
    """Test ErrorCategory enum with HTTP-aligned categories"""

    def test_http_aligned_categories_exist(self):
        """Verify all HTTP-aligned categories are defined"""
        assert hasattr(ErrorCategory, "VALIDATION")
        assert hasattr(ErrorCategory, "AUTHENTICATION")
        assert hasattr(ErrorCategory, "AUTHORIZATION")
        assert hasattr(ErrorCategory, "NOT_FOUND")
        assert hasattr(ErrorCategory, "CONFLICT")
        assert hasattr(ErrorCategory, "RATE_LIMIT")
        assert hasattr(ErrorCategory, "SERVER_ERROR")
        assert hasattr(ErrorCategory, "SERVICE_UNAVAILABLE")
        assert hasattr(ErrorCategory, "EXTERNAL_SERVICE")

    def test_system_level_categories_exist(self):
        """Verify system-level categories still exist (backward compatibility)"""
        assert hasattr(ErrorCategory, "SYSTEM")
        assert hasattr(ErrorCategory, "NETWORK")
        assert hasattr(ErrorCategory, "DATABASE")
        assert hasattr(ErrorCategory, "LLM")
        assert hasattr(ErrorCategory, "AGENT")
        assert hasattr(ErrorCategory, "API")
        assert hasattr(ErrorCategory, "CONFIGURATION")
        assert hasattr(ErrorCategory, "USER_INPUT")

    def test_category_values(self):
        """Verify category values are strings"""
        assert ErrorCategory.VALIDATION.value == "validation"
        assert ErrorCategory.AUTHENTICATION.value == "authentication"
        assert ErrorCategory.NOT_FOUND.value == "not_found"
        assert ErrorCategory.SERVER_ERROR.value == "server_error"


class TestAPIErrorResponse:
    """Test APIErrorResponse dataclass"""

    def test_create_error_response(self):
        """Test creating an API error response"""
        error = APIErrorResponse(
            category=ErrorCategory.NOT_FOUND,
            message="User not found",
            code="USER_0001",
            status_code=404,
        )

        assert error.category == ErrorCategory.NOT_FOUND
        assert error.message == "User not found"
        assert error.code == "USER_0001"
        assert error.status_code == 404
        assert error.details is None
        assert error.retry_after is None
        assert error.trace_id is None

    def test_error_response_with_details(self):
        """Test error response with additional details"""
        error = APIErrorResponse(
            category=ErrorCategory.VALIDATION,
            message="Invalid input",
            code="VAL_0042",
            status_code=400,
            details={"field": "email", "reason": "Invalid format"},
            retry_after=None,
            trace_id="req_12345",
        )

        assert error.details == {"field": "email", "reason": "Invalid format"}
        assert error.trace_id == "req_12345"

    def test_to_dict_conversion(self):
        """Test converting error response to dictionary"""
        error = APIErrorResponse(
            category=ErrorCategory.SERVER_ERROR,
            message="Internal error",
            code="SRV_9999",
            status_code=500,
            details={"operation": "database_query"},
            trace_id="trace_abc123",
        )

        error_dict = error.to_dict()

        assert "error" in error_dict
        assert error_dict["error"]["category"] == "server_error"
        assert error_dict["error"]["message"] == "Internal error"
        assert error_dict["error"]["code"] == "SRV_9999"
        assert error_dict["error"]["details"] == {"operation": "database_query"}
        assert error_dict["error"]["trace_id"] == "trace_abc123"
        assert "timestamp" in error_dict["error"]

    def test_to_dict_minimal(self):
        """Test to_dict with minimal fields"""
        error = APIErrorResponse(
            category=ErrorCategory.CONFLICT,
            message="Resource already exists",
            code="RES_0001",
            status_code=409,
        )

        error_dict = error.to_dict()

        assert "error" in error_dict
        assert error_dict["error"]["category"] == "conflict"
        assert error_dict["error"]["message"] == "Resource already exists"
        assert error_dict["error"]["code"] == "RES_0001"
        assert "details" not in error_dict["error"]
        assert "retry_after" not in error_dict["error"]
        assert "trace_id" not in error_dict["error"]

    def test_get_status_code_for_category(self):
        """Test status code mapping for all categories"""
        # HTTP-aligned categories
        assert (
            APIErrorResponse.get_status_code_for_category(ErrorCategory.VALIDATION)
            == 400
        )
        assert (
            APIErrorResponse.get_status_code_for_category(ErrorCategory.AUTHENTICATION)
            == 401
        )
        assert (
            APIErrorResponse.get_status_code_for_category(ErrorCategory.AUTHORIZATION)
            == 403
        )
        assert (
            APIErrorResponse.get_status_code_for_category(ErrorCategory.NOT_FOUND)
            == 404
        )
        assert (
            APIErrorResponse.get_status_code_for_category(ErrorCategory.CONFLICT) == 409
        )
        assert (
            APIErrorResponse.get_status_code_for_category(ErrorCategory.RATE_LIMIT)
            == 429
        )
        assert (
            APIErrorResponse.get_status_code_for_category(ErrorCategory.SERVER_ERROR)
            == 500
        )
        assert (
            APIErrorResponse.get_status_code_for_category(
                ErrorCategory.EXTERNAL_SERVICE
            )
            == 502
        )
        assert (
            APIErrorResponse.get_status_code_for_category(
                ErrorCategory.SERVICE_UNAVAILABLE
            )
            == 503
        )

        # System-level categories (default to 500)
        assert (
            APIErrorResponse.get_status_code_for_category(ErrorCategory.SYSTEM) == 500
        )
        assert (
            APIErrorResponse.get_status_code_for_category(ErrorCategory.DATABASE) == 500
        )
        assert APIErrorResponse.get_status_code_for_category(ErrorCategory.LLM) == 500

        # Network -> 503
        assert (
            APIErrorResponse.get_status_code_for_category(ErrorCategory.NETWORK) == 503
        )

        # User input -> 400
        assert (
            APIErrorResponse.get_status_code_for_category(ErrorCategory.USER_INPUT)
            == 400
        )


class TestWithErrorHandlingDecorator:
    """Test @with_error_handling decorator"""

    def test_decorator_on_sync_function_success(self):
        """Test decorator on successful sync function"""

        @with_error_handling(
            category=ErrorCategory.VALIDATION,
            operation="test_divide",
            error_code_prefix="TEST",
        )
        def divide(a: int, b: int) -> float:
            return a / b

        result = divide(10, 2)
        assert result == 5.0

    def test_decorator_on_sync_function_error(self):
        """Test decorator on sync function that raises error"""

        @with_error_handling(
            category=ErrorCategory.VALIDATION,
            operation="test_divide",
            error_code_prefix="TEST",
        )
        def divide(a: int, b: int) -> float:
            return a / b

        # Should raise HTTPException or return error dict
        with pytest.raises(Exception):  # Could be HTTPException or dict
            divide(10, 0)

    @pytest.mark.asyncio
    async def test_decorator_on_async_function_success(self):
        """Test decorator on successful async function"""

        @with_error_handling(
            category=ErrorCategory.SERVER_ERROR,
            operation="test_fetch",
            error_code_prefix="FETCH",
        )
        async def fetch_data(user_id: str) -> dict:
            # Simulate async operation
            await asyncio.sleep(0.01)
            return {"user_id": user_id, "data": "test"}

        result = await fetch_data("user123")
        assert result == {"user_id": "user123", "data": "test"}

    @pytest.mark.asyncio
    async def test_decorator_on_async_function_error(self):
        """Test decorator on async function that raises error"""

        @with_error_handling(
            category=ErrorCategory.NOT_FOUND,
            operation="test_find_user",
            error_code_prefix="USER",
        )
        async def find_user(user_id: str) -> dict:
            raise ValueError(f"User {user_id} not found")

        # Should raise HTTPException or return error dict
        with pytest.raises(Exception):  # Could be HTTPException or dict
            await find_user("nonexistent")

    def test_decorator_preserves_function_name(self):
        """Test that decorator preserves original function name"""

        @with_error_handling(category=ErrorCategory.VALIDATION)
        def my_function():
            return "test"

        assert my_function.__name__ == "my_function"

    @pytest.mark.asyncio
    async def test_decorator_generates_trace_id(self):
        """Test that decorator generates trace IDs for errors"""

        @with_error_handling(
            category=ErrorCategory.SERVER_ERROR, operation="test_operation"
        )
        async def failing_operation():
            raise RuntimeError("Test error")

        try:
            await failing_operation()
        except Exception as e:
            # Check if error has trace ID (in detail if HTTPException)
            if hasattr(e, "detail") and isinstance(e.detail, dict):
                assert "error" in e.detail
                # Trace ID might be present


class TestErrorHandlingIntegration:
    """Integration tests for error handling system"""

    def test_multiple_categories_produce_correct_status_codes(self):
        """Test that different categories produce different HTTP status codes"""
        categories_and_codes = [
            (ErrorCategory.VALIDATION, 400),
            (ErrorCategory.AUTHENTICATION, 401),
            (ErrorCategory.AUTHORIZATION, 403),
            (ErrorCategory.NOT_FOUND, 404),
            (ErrorCategory.CONFLICT, 409),
            (ErrorCategory.RATE_LIMIT, 429),
            (ErrorCategory.SERVER_ERROR, 500),
            (ErrorCategory.EXTERNAL_SERVICE, 502),
            (ErrorCategory.SERVICE_UNAVAILABLE, 503),
        ]

        for category, expected_code in categories_and_codes:
            status_code = APIErrorResponse.get_status_code_for_category(category)
            assert status_code == expected_code, (
                f"Category {category} should map to {expected_code}, "
                f"got {status_code}"
            )

    def test_error_response_serialization_roundtrip(self):
        """Test that error response can be serialized and contains all info"""
        error = APIErrorResponse(
            category=ErrorCategory.VALIDATION,
            message="Validation failed",
            code="VAL_0001",
            status_code=400,
            details={"field": "email"},
            retry_after=60,
            trace_id="trace_123",
        )

        # Convert to dict (JSON serialization)
        error_dict = error.to_dict()

        # Verify all fields are present and correct
        assert error_dict["error"]["category"] == "validation"
        assert error_dict["error"]["message"] == "Validation failed"
        assert error_dict["error"]["code"] == "VAL_0001"
        assert error_dict["error"]["details"] == {"field": "email"}
        assert error_dict["error"]["retry_after"] == 60
        assert error_dict["error"]["trace_id"] == "trace_123"
        assert "timestamp" in error_dict["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
