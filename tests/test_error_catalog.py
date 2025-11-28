"""
Tests for Error Catalog Loader

Validates error catalog loading, retrieval, and caching functionality
"""

import pytest

from src.utils.error_catalog import (
    ErrorCatalog,
    get_error,
    get_error_message,
    validate_error_code,
)
from src.utils.error_boundaries import ErrorCategory


class TestErrorCatalog:
    """Test error catalog loader functionality"""

    def test_catalog_loads_successfully(self):
        """Test that catalog loads from default path"""
        catalog = ErrorCatalog.get_instance()
        catalog.reload_catalog()  # Force reload

        stats = catalog.get_catalog_stats()
        assert stats["total_errors"] > 0, "Catalog should contain errors"
        assert stats["version"] == "1.0.0", "Catalog version should match"

    def test_get_error_by_code(self):
        """Test retrieving error by code"""
        catalog = ErrorCatalog.get_instance()

        # Test knowledge base error
        kb_error = catalog.get_error("KB_0001")
        assert kb_error is not None, "KB_0001 should exist"
        assert kb_error.code == "KB_0001"
        assert kb_error.category == ErrorCategory.SERVER_ERROR
        assert "initialize knowledge base" in kb_error.message.lower()
        assert kb_error.status_code == 500
        assert kb_error.retry is True
        assert kb_error.retry_after == 30

        # Test LLM error
        llm_error = catalog.get_error("LLM_0001")
        assert llm_error is not None, "LLM_0001 should exist"
        assert llm_error.category == ErrorCategory.SERVICE_UNAVAILABLE
        assert llm_error.status_code == 503

        # Test authentication error
        auth_error = catalog.get_error("AUTH_0001")
        assert auth_error is not None, "AUTH_0001 should exist"
        assert auth_error.category == ErrorCategory.AUTHENTICATION
        assert auth_error.retry is False

    def test_get_nonexistent_error(self):
        """Test retrieving error that doesn't exist"""
        catalog = ErrorCatalog.get_instance()

        error = catalog.get_error("INVALID_9999")
        assert error is None, "Nonexistent error should return None"

    def test_get_error_message(self):
        """Test error message retrieval"""
        catalog = ErrorCatalog.get_instance()

        # Test with existing code
        message = catalog.get_error_message("KB_0001")
        assert "Failed to initialize knowledge base" in message

        # Test with nonexistent code (should use default)
        message = catalog.get_error_message("INVALID_9999", "Default message")
        assert message == "Default message"

    def test_validate_error_code(self):
        """Test error code validation"""
        catalog = ErrorCatalog.get_instance()

        # Valid codes
        assert catalog.validate_code("KB_0001") is True
        assert catalog.validate_code("LLM_0001") is True
        assert catalog.validate_code("AUTH_0001") is True

        # Invalid codes
        assert catalog.validate_code("INVALID_9999") is False
        assert catalog.validate_code("") is False

    def test_list_codes_by_component(self):
        """Test listing error codes by component"""
        catalog = ErrorCatalog.get_instance()

        # Test knowledge base codes
        kb_codes = catalog.list_codes_by_component("KB")
        assert len(kb_codes) > 0, "Should have KB codes"
        assert "KB_0001" in kb_codes
        assert all(code.startswith("KB_") for code in kb_codes)

        # Test LLM codes
        llm_codes = catalog.list_codes_by_component("LLM")
        assert len(llm_codes) > 0, "Should have LLM codes"
        assert "LLM_0001" in llm_codes

        # Test nonexistent component
        invalid_codes = catalog.list_codes_by_component("INVALID")
        assert len(invalid_codes) == 0

    def test_catalog_stats(self):
        """Test catalog statistics"""
        catalog = ErrorCatalog.get_instance()
        stats = catalog.get_catalog_stats()

        # Check required fields
        assert "total_errors" in stats
        assert "catalog_path" in stats
        assert "version" in stats
        assert "by_category" in stats
        assert "by_component" in stats

        # Check stats make sense
        assert stats["total_errors"] > 0
        assert stats["version"] == "1.0.0"

        # Check component counts
        assert "KB" in stats["by_component"]
        assert "LLM" in stats["by_component"]
        assert "AUTH" in stats["by_component"]

        # Check category counts
        assert len(stats["by_category"]) > 0

    def test_error_definition_to_dict(self):
        """Test ErrorDefinition to_dict conversion"""
        catalog = ErrorCatalog.get_instance()
        error = catalog.get_error("KB_0001")

        error_dict = error.to_dict()

        # Check all fields present
        assert "code" in error_dict
        assert "category" in error_dict
        assert "message" in error_dict
        assert "status_code" in error_dict
        assert "retry" in error_dict
        assert "retry_after" in error_dict
        assert "details" in error_dict

        # Check types
        assert isinstance(error_dict["code"], str)
        assert isinstance(error_dict["category"], str)
        assert isinstance(error_dict["status_code"], int)
        assert isinstance(error_dict["retry"], bool)

    def test_convenience_functions(self):
        """Test convenience functions"""
        # Test get_error
        error = get_error("KB_0001")
        assert error is not None
        assert error.code == "KB_0001"

        # Test get_error_message
        message = get_error_message("LLM_0001")
        assert "LLM service unavailable" in message

        # Test validate_error_code
        assert validate_error_code("KB_0001") is True
        assert validate_error_code("INVALID_9999") is False

    def test_singleton_pattern(self):
        """Test that ErrorCatalog is a singleton"""
        catalog1 = ErrorCatalog.get_instance()
        catalog2 = ErrorCatalog.get_instance()

        assert catalog1 is catalog2, "Should return same instance"

    def test_all_defined_error_codes(self):
        """Test that all expected error codes are defined"""
        catalog = ErrorCatalog.get_instance()

        # Knowledge base errors
        expected_kb_codes = [
            "KB_0001",
            "KB_0002",
            "KB_0003",
            "KB_0004",
            "KB_0005",
            "KB_0006",
            "KB_0007",
            "KB_0008",
        ]
        for code in expected_kb_codes:
            assert catalog.validate_code(code), f"{code} should be defined"

        # Authentication errors
        expected_auth_codes = ["AUTH_0001", "AUTH_0002", "AUTH_0003", "AUTH_0004"]
        for code in expected_auth_codes:
            assert catalog.validate_code(code), f"{code} should be defined"

        # LLM errors
        expected_llm_codes = [
            "LLM_0001",
            "LLM_0002",
            "LLM_0003",
            "LLM_0004",
            "LLM_0005",
            "LLM_0006",
        ]
        for code in expected_llm_codes:
            assert catalog.validate_code(code), f"{code} should be defined"

    def test_error_categories_valid(self):
        """Test that all error categories map to valid ErrorCategory enums"""
        catalog = ErrorCatalog.get_instance()

        valid_categories = {cat.value for cat in ErrorCategory}

        for error_code in catalog._catalog.keys():
            error = catalog.get_error(error_code)
            assert (
                error.category.value in valid_categories
            ), f"{error_code} has invalid category"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
