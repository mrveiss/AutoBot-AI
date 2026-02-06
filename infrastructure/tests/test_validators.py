"""
Tests for Common Validators

Verifies that validation utilities provide correct validation logic,
error messages, and edge case handling.
"""

import pytest

from src.utils.validators import (
    sanitize_alphanumeric,
    sanitize_string,
    validate_collection_size,
    validate_email,
    validate_file_extension,
    validate_file_size,
    validate_filename_safe,
    validate_in_choices,
    validate_non_empty_collection,
    validate_non_empty_string,
    validate_password,
    validate_string_length,
    validate_string_pattern,
    validate_url,
    validate_username,
    validate_uuid,
)


class TestStringValidators:
    """Test suite for string validators"""

    def test_validate_non_empty_string_valid(self):
        """Test valid non-empty string"""
        result = validate_non_empty_string("hello", "Test")
        assert result == "hello"

    def test_validate_non_empty_string_with_whitespace(self):
        """Test string with whitespace gets stripped"""
        result = validate_non_empty_string("  hello  ", "Test", strip=True)
        assert result == "hello"

    def test_validate_non_empty_string_empty_raises(self):
        """Test empty string raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_non_empty_string("", "Test")
        assert "Test cannot be empty" in str(exc_info.value)

    def test_validate_non_empty_string_none_raises(self):
        """Test None raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_non_empty_string(None, "Test")
        assert "Test cannot be None" in str(exc_info.value)

    def test_validate_non_empty_string_whitespace_only_raises(self):
        """Test whitespace-only string raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_non_empty_string("   ", "Test", strip=True)
        assert "Test cannot be empty" in str(exc_info.value)

    def test_validate_string_length_valid(self):
        """Test valid string length"""
        result = validate_string_length("hello", "Test", min_length=3, max_length=10)
        assert result == "hello"

    def test_validate_string_length_too_short_raises(self):
        """Test too short string raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_string_length("ab", "Test", min_length=3)
        assert "too short" in str(exc_info.value)
        assert "minimum 3" in str(exc_info.value)

    def test_validate_string_length_too_long_raises(self):
        """Test too long string raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_string_length("a" * 100, "Test", max_length=50)
        assert "too long" in str(exc_info.value)
        assert "maximum 50" in str(exc_info.value)

    def test_validate_string_pattern_valid(self):
        """Test valid pattern match"""
        result = validate_string_pattern("abc123", r"^[a-z0-9]+$", "Code")
        assert result == "abc123"

    def test_validate_string_pattern_invalid_raises(self):
        """Test invalid pattern raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_string_pattern("abc-123", r"^[a-z0-9]+$", "Code")
        assert "invalid characters" in str(exc_info.value)

    def test_validate_string_pattern_custom_error(self):
        """Test custom error message"""
        with pytest.raises(ValueError) as exc_info:
            validate_string_pattern(
                "abc-123", r"^[a-z0-9]+$", "Code", error_message="Custom error"
            )
        assert "Custom error" in str(exc_info.value)


class TestStringSanitizers:
    """Test suite for string sanitizers"""

    def test_sanitize_string_strip(self):
        """Test strip whitespace"""
        result = sanitize_string("  hello  ", strip=True)
        assert result == "hello"

    def test_sanitize_string_lowercase(self):
        """Test lowercase conversion"""
        result = sanitize_string("  HELLO  ", strip=True, lowercase=True)
        assert result == "hello"

    def test_sanitize_string_uppercase(self):
        """Test uppercase conversion"""
        result = sanitize_string("  hello  ", strip=True, uppercase=True)
        assert result == "HELLO"

    def test_sanitize_string_uppercase_precedence(self):
        """Test uppercase takes precedence over lowercase"""
        result = sanitize_string("hello", lowercase=True, uppercase=True)
        assert result == "HELLO"

    def test_sanitize_alphanumeric_basic(self):
        """Test basic alphanumeric sanitization"""
        result = sanitize_alphanumeric("hello_world-123", allowed_chars="_-.")
        assert result == "hello_world-123"

    def test_sanitize_alphanumeric_removes_special(self):
        """Test removes special characters"""
        result = sanitize_alphanumeric("hello@world#123", allowed_chars="")
        assert result == "helloworld123"

    def test_sanitize_alphanumeric_lowercase(self):
        """Test lowercase conversion"""
        result = sanitize_alphanumeric("Hello_World", allowed_chars="_", lowercase=True)
        assert result == "hello_world"

    def test_sanitize_alphanumeric_empty_raises(self):
        """Test empty result raises error"""
        with pytest.raises(ValueError) as exc_info:
            sanitize_alphanumeric("@#$%", allowed_chars="")
        assert "no valid characters" in str(exc_info.value)


class TestCollectionValidators:
    """Test suite for collection validators"""

    def test_validate_non_empty_collection_valid(self):
        """Test valid non-empty collection"""
        result = validate_non_empty_collection([1, 2, 3], "IDs")
        assert result == [1, 2, 3]

    def test_validate_non_empty_collection_empty_raises(self):
        """Test empty collection raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_non_empty_collection([], "IDs")
        assert "IDs cannot be empty" in str(exc_info.value)

    def test_validate_non_empty_collection_none_raises(self):
        """Test None raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_non_empty_collection(None, "IDs")
        assert "IDs cannot be None" in str(exc_info.value)

    def test_validate_collection_size_valid(self):
        """Test valid collection size"""
        result = validate_collection_size([1, 2, 3], "IDs", min_size=1, max_size=10)
        assert result == [1, 2, 3]

    def test_validate_collection_size_too_small_raises(self):
        """Test too small collection raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_collection_size([1], "IDs", min_size=3)
        assert "too small" in str(exc_info.value)
        assert "minimum 3" in str(exc_info.value)

    def test_validate_collection_size_too_large_raises(self):
        """Test too large collection raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_collection_size([1] * 100, "IDs", max_size=50)
        assert "too large" in str(exc_info.value)
        assert "maximum 50" in str(exc_info.value)


class TestChoiceValidators:
    """Test suite for choice validators"""

    def test_validate_in_choices_valid(self):
        """Test valid choice"""
        result = validate_in_choices("apple", {"apple", "banana"}, "Fruit")
        assert result == "apple"

    def test_validate_in_choices_invalid_raises(self):
        """Test invalid choice raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_in_choices("orange", {"apple", "banana"}, "Fruit")
        assert "Invalid Fruit" in str(exc_info.value)
        assert "apple" in str(exc_info.value)
        assert "banana" in str(exc_info.value)

    def test_validate_in_choices_case_insensitive(self):
        """Test case-insensitive matching"""
        result = validate_in_choices(
            "APPLE", {"apple", "banana"}, "Fruit", case_sensitive=False
        )
        assert result == "APPLE"

    def test_validate_in_choices_case_sensitive_raises(self):
        """Test case-sensitive matching fails"""
        with pytest.raises(ValueError):
            validate_in_choices(
                "APPLE", {"apple", "banana"}, "Fruit", case_sensitive=True
            )


class TestFileValidators:
    """Test suite for file validators"""

    def test_validate_file_extension_valid(self):
        """Test valid file extension"""
        result = validate_file_extension("doc.txt", {".txt", ".md"}, "Document")
        assert result == "doc.txt"

    def test_validate_file_extension_invalid_raises(self):
        """Test invalid extension raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_file_extension("doc.exe", {".txt", ".md"}, "Document")
        assert "Invalid Document extension" in str(exc_info.value)
        assert ".txt" in str(exc_info.value)
        assert ".md" in str(exc_info.value)

    def test_validate_file_extension_case_insensitive(self):
        """Test extension matching is case-insensitive"""
        result = validate_file_extension("doc.TXT", {".txt", ".md"}, "Document")
        assert result == "doc.TXT"

    def test_validate_filename_safe_valid(self):
        """Test valid safe filename"""
        result = validate_filename_safe("document.txt", "Filename")
        assert result == "document.txt"

    def test_validate_filename_safe_path_traversal_raises(self):
        """Test path traversal raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_filename_safe("../etc/passwd", "Filename")
        assert "path traversal" in str(exc_info.value)

    def test_validate_filename_safe_too_long_raises(self):
        """Test too long filename raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_filename_safe("a" * 300, "Filename", max_length=255)
        assert "too long" in str(exc_info.value)

    def test_validate_filename_safe_dangerous_chars_raises(self):
        """Test dangerous characters raise error"""
        with pytest.raises(ValueError) as exc_info:
            validate_filename_safe("file<name>.txt", "Filename")
        assert "dangerous characters" in str(exc_info.value)

    def test_validate_file_size_valid(self):
        """Test valid file size"""
        result = validate_file_size(1024, "File", max_size=10 * 1024 * 1024)
        assert result == 1024

    def test_validate_file_size_too_large_raises(self):
        """Test too large file raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_file_size(100 * 1024 * 1024, "File", max_size=50 * 1024 * 1024)
        assert "too large" in str(exc_info.value)
        assert "50.00 MB" in str(exc_info.value)

    def test_validate_file_size_too_small_raises(self):
        """Test too small file raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_file_size(100, "File", min_size=1024)
        assert "too small" in str(exc_info.value)


class TestFormatValidators:
    """Test suite for format validators"""

    def test_validate_email_valid(self):
        """Test valid email"""
        result = validate_email("user@example.com", "Email")
        assert result == "user@example.com"

    def test_validate_email_invalid_raises(self):
        """Test invalid email raises error"""
        invalid_emails = [
            "invalid",
            "invalid@",
            "@invalid.com",
            "invalid.com",
            "invalid@invalid",
        ]
        for email in invalid_emails:
            with pytest.raises(ValueError) as exc_info:
                validate_email(email, "Email")
            assert "Invalid Email format" in str(exc_info.value)

    def test_validate_url_valid(self):
        """Test valid URL"""
        result = validate_url("https://example.com", "URL")
        assert result == "https://example.com"

    def test_validate_url_http_valid(self):
        """Test HTTP URL valid when HTTPS not required"""
        result = validate_url("http://example.com", "URL", require_https=False)
        assert result == "http://example.com"

    def test_validate_url_http_https_required_raises(self):
        """Test HTTP fails when HTTPS required"""
        with pytest.raises(ValueError) as exc_info:
            validate_url("http://example.com", "URL", require_https=True)
        assert "must use HTTPS" in str(exc_info.value)

    def test_validate_url_invalid_raises(self):
        """Test invalid URL raises error"""
        invalid_urls = [
            "not-a-url",
            "://invalid",
            "http://",
            "example.com",  # Missing scheme
        ]
        for url in invalid_urls:
            with pytest.raises(ValueError) as exc_info:
                validate_url(url, "URL")
            assert "Invalid URL format" in str(exc_info.value)

    def test_validate_uuid_valid(self):
        """Test valid UUID"""
        result = validate_uuid("123e4567-e89b-12d3-a456-426614174000", "UUID")
        assert result == "123e4567-e89b-12d3-a456-426614174000"

    def test_validate_uuid_uppercase_valid(self):
        """Test uppercase UUID valid"""
        result = validate_uuid("123E4567-E89B-12D3-A456-426614174000", "UUID")
        assert result == "123E4567-E89B-12D3-A456-426614174000"

    def test_validate_uuid_invalid_raises(self):
        """Test invalid UUID raises error"""
        invalid_uuids = [
            "not-a-uuid",
            "123e4567",
            "123e4567-e89b-12d3-a456",
            "123e4567-e89b-12d3-a456-426614174000-extra",
        ]
        for uuid in invalid_uuids:
            with pytest.raises(ValueError) as exc_info:
                validate_uuid(uuid, "UUID")
            assert "Invalid UUID format" in str(exc_info.value)


class TestCompositeValidators:
    """Test suite for composite validators"""

    def test_validate_username_valid(self):
        """Test valid username"""
        result = validate_username("john_doe")
        assert result == "john_doe"

    def test_validate_username_uppercase_sanitized(self):
        """Test uppercase gets lowercased"""
        result = validate_username("John_Doe")
        assert result == "john_doe"

    def test_validate_username_whitespace_stripped(self):
        """Test whitespace gets stripped"""
        result = validate_username("  john_doe  ")
        assert result == "john_doe"

    def test_validate_username_too_short_raises(self):
        """Test too short username raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_username("ab", min_length=3)
        assert "too short" in str(exc_info.value)

    def test_validate_username_too_long_raises(self):
        """Test too long username raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_username("a" * 100, max_length=50)
        assert "too long" in str(exc_info.value)

    def test_validate_username_invalid_chars_removed(self):
        """Test invalid characters get removed"""
        result = validate_username("john@doe", allowed_special_chars="_-")
        assert result == "johndoe"

    def test_validate_password_valid(self):
        """Test valid password"""
        result = validate_password("MyP@ssw0rd!")
        assert result == "MyP@ssw0rd!"

    def test_validate_password_too_short_raises(self):
        """Test too short password raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_password("short", min_length=8)
        assert "too short" in str(exc_info.value)

    def test_validate_password_too_long_raises(self):
        """Test too long password raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_password("a" * 200, max_length=128)
        assert "too long" in str(exc_info.value)

    def test_validate_password_empty_raises(self):
        """Test empty password raises error"""
        with pytest.raises(ValueError) as exc_info:
            validate_password("")
        assert "cannot be empty" in str(exc_info.value)


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
