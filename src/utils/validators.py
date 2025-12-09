# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Common Validators - Standardized Validation Utilities

This module provides reusable validation functions for common patterns across
the codebase. Eliminates duplicate validation logic in Pydantic models and
API endpoints.

CONSOLIDATES PATTERNS FROM:
===========================
- String validation (empty checks, length checks) - 50+ occurrences
- File validation (extension, size, filename) - 30+ occurrences
- Username/password validation - 10+ occurrences
- Entity/relation type validation - 20+ occurrences
- Collection validation (non-empty lists, size limits) - 40+ occurrences
- String sanitization (strip, lower, upper) - 151 occurrences

BENEFITS:
=========
✅ Eliminates 150+ lines of duplicate validation code
✅ Standardizes validation error messages
✅ Type-safe with proper type hints
✅ Reusable across Pydantic models and regular functions
✅ Composable validators for complex validation
✅ Consistent error handling

USAGE PATTERN:
==============
from src.utils.validators import (
    validate_non_empty_string,
    validate_string_length,
    validate_in_choices,
    sanitize_string
)

# In Pydantic models
class MyModel(BaseModel):
    username: str

    @validator("username")
    def validate_username(cls, v):
        v = sanitize_string(v)  # Strip and lowercase
        validate_non_empty_string(v, "Username")
        validate_string_length(v, "Username", min_length=3, max_length=50)
        return v

# Or standalone
def process_input(value: str):
    validate_non_empty_string(value, "Input")
    validate_string_length(value, "Input", max_length=255)
    return value.strip()
"""

import re
from collections.abc import Collection
from pathlib import Path
from typing import (
    Any,
    Iterable,
    Optional,
    Set,
    Union,
)
from urllib.parse import urlparse

from src.utils.path_validation import contains_path_traversal

# Issue #380: Pre-compiled regex patterns for validation
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# ============================================================================
# String Validators
# ============================================================================


def validate_non_empty_string(
    value: Optional[str], field_name: str = "Value", strip: bool = True
) -> str:
    """
    Validate that string is not None, not empty, and not just whitespace.

    Args:
        value: String to validate
        field_name: Name of field for error messages
        strip: Whether to strip whitespace before checking

    Returns:
        str: Original value (or stripped if strip=True)

    Raises:
        ValueError: If string is None, empty, or whitespace

    Examples:
        >>> validate_non_empty_string("hello", "Username")
        'hello'

        >>> validate_non_empty_string("  hello  ", "Username", strip=True)
        'hello'

        >>> validate_non_empty_string("", "Username")
        ValueError: Username cannot be empty
    """
    if value is None:
        raise ValueError(f"{field_name} cannot be None")

    if strip:
        value = value.strip()

    if not value or len(value) == 0:
        raise ValueError(f"{field_name} cannot be empty")

    return value


def validate_string_length(
    value: str,
    field_name: str = "Value",
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
) -> str:
    """
    Validate string length bounds.

    Args:
        value: String to validate
        field_name: Name of field for error messages
        min_length: Minimum allowed length (inclusive)
        max_length: Maximum allowed length (inclusive)

    Returns:
        str: Original value if valid

    Raises:
        ValueError: If length is out of bounds

    Examples:
        >>> validate_string_length("hello", "Username", min_length=3, max_length=20)
        'hello'

        >>> validate_string_length("ab", "Username", min_length=3)
        ValueError: Username too short (minimum 3 characters)

        >>> validate_string_length("a" * 100, "Username", max_length=50)
        ValueError: Username too long (maximum 50 characters)
    """
    length = len(value)

    if min_length is not None and length < min_length:
        raise ValueError(f"{field_name} too short (minimum {min_length} characters)")

    if max_length is not None and length > max_length:
        raise ValueError(f"{field_name} too long (maximum {max_length} characters)")

    return value


def validate_string_pattern(
    value: str,
    pattern: Union[str, re.Pattern],
    field_name: str = "Value",
    error_message: Optional[str] = None,
) -> str:
    """
    Validate string matches regex pattern.

    Args:
        value: String to validate
        pattern: Regex pattern (string or compiled)
        field_name: Name of field for error messages
        error_message: Custom error message (optional)

    Returns:
        str: Original value if matches

    Raises:
        ValueError: If pattern doesn't match

    Examples:
        >>> validate_string_pattern("abc123", r"^[a-z0-9]+$", "Code")
        'abc123'

        >>> validate_string_pattern("abc-123", r"^[a-z0-9]+$", "Code")
        ValueError: Code contains invalid characters
    """
    if isinstance(pattern, str):
        pattern = re.compile(pattern)

    if not pattern.match(value):
        if error_message:
            raise ValueError(error_message)
        else:
            raise ValueError(f"{field_name} contains invalid characters")

    return value


# ============================================================================
# String Sanitizers
# ============================================================================


def sanitize_string(
    value: str, strip: bool = True, lowercase: bool = False, uppercase: bool = False
) -> str:
    """
    Sanitize string with common transformations.

    Args:
        value: String to sanitize
        strip: Remove leading/trailing whitespace
        lowercase: Convert to lowercase
        uppercase: Convert to uppercase (takes precedence over lowercase)

    Returns:
        str: Sanitized string

    Examples:
        >>> sanitize_string("  Hello World  ")
        'Hello World'

        >>> sanitize_string("  Hello World  ", lowercase=True)
        'hello world'

        >>> sanitize_string("hello", uppercase=True)
        'HELLO'
    """
    if strip:
        value = value.strip()

    if uppercase:
        value = value.upper()
    elif lowercase:
        value = value.lower()

    return value


def sanitize_alphanumeric(
    value: str, allowed_chars: str = "_-.", strip: bool = True, lowercase: bool = False
) -> str:
    """
    Sanitize to alphanumeric with optional additional characters.

    Args:
        value: String to sanitize
        allowed_chars: Additional allowed characters besides alphanumeric
        strip: Strip whitespace first
        lowercase: Convert to lowercase

    Returns:
        str: Sanitized string with only allowed characters

    Raises:
        ValueError: If result is empty after sanitization

    Examples:
        >>> sanitize_alphanumeric("hello_world-123")
        'hello_world-123'

        >>> sanitize_alphanumeric("hello@world", allowed_chars="")
        'helloworld'
    """
    if strip:
        value = value.strip()

    if lowercase:
        value = value.lower()

    # Keep only alphanumeric and allowed chars
    result = "".join(c for c in value if c.isalnum() or c in allowed_chars)

    if not result:
        raise ValueError("String contains no valid characters")

    return result


# ============================================================================
# Collection Validators
# ============================================================================


def validate_non_empty_collection(
    value: Optional[Collection], field_name: str = "Collection"
) -> Collection:
    """
    Validate collection is not None or empty.

    Args:
        value: Collection to validate
        field_name: Name of field for error messages

    Returns:
        Collection: Original collection if valid

    Raises:
        ValueError: If None or empty

    Examples:
        >>> validate_non_empty_collection([1, 2, 3], "IDs")
        [1, 2, 3]

        >>> validate_non_empty_collection([], "IDs")
        ValueError: IDs cannot be empty
    """
    if value is None:
        raise ValueError(f"{field_name} cannot be None")

    if len(value) == 0:
        raise ValueError(f"{field_name} cannot be empty")

    return value


def validate_collection_size(
    value: Collection,
    field_name: str = "Collection",
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
) -> Collection:
    """
    Validate collection size bounds.

    Args:
        value: Collection to validate
        field_name: Name of field for error messages
        min_size: Minimum size (inclusive)
        max_size: Maximum size (inclusive)

    Returns:
        Collection: Original collection if valid

    Raises:
        ValueError: If size is out of bounds

    Examples:
        >>> validate_collection_size([1, 2, 3], "IDs", min_size=1, max_size=10)
        [1, 2, 3]

        >>> validate_collection_size([1] * 100, "IDs", max_size=50)
        ValueError: IDs too large (maximum 50 items)
    """
    size = len(value)

    if min_size is not None and size < min_size:
        raise ValueError(f"{field_name} too small (minimum {min_size} items)")

    if max_size is not None and size > max_size:
        raise ValueError(f"{field_name} too large (maximum {max_size} items)")

    return value


# ============================================================================
# Choice Validators
# ============================================================================


def validate_in_choices(
    value: Any,
    choices: Union[Set, Iterable],
    field_name: str = "Value",
    case_sensitive: bool = True,
) -> Any:
    """
    Validate value is in allowed choices.

    Args:
        value: Value to validate
        choices: Allowed values (set or iterable)
        field_name: Name of field for error messages
        case_sensitive: Whether string comparison is case-sensitive

    Returns:
        Any: Original value if valid

    Raises:
        ValueError: If value not in choices

    Examples:
        >>> validate_in_choices("apple", {"apple", "banana"}, "Fruit")
        'apple'

        >>> validate_in_choices("APPLE", {"apple", "banana"}, "Fruit", case_sensitive=False)
        'APPLE'

        >>> validate_in_choices("orange", {"apple", "banana"}, "Fruit")
        ValueError: Invalid Fruit. Must be one of: apple, banana
    """
    if not isinstance(choices, set):
        choices = set(choices)

    # Case-insensitive comparison for strings
    if not case_sensitive and isinstance(value, str):
        choices_lower = {str(c).lower() for c in choices}
        if value.lower() not in choices_lower:
            raise ValueError(
                f"Invalid {field_name}. Must be one of: {', '.join(str(c) for c in sorted(choices))}"
            )
    else:
        if value not in choices:
            raise ValueError(
                f"Invalid {field_name}. Must be one of: {', '.join(str(c) for c in sorted(choices))}"
            )

    return value


# ============================================================================
# File Validators
# ============================================================================


def validate_file_extension(
    filename: str, allowed_extensions: Set[str], field_name: str = "File"
) -> str:
    """
    Validate file has allowed extension.

    Args:
        filename: Filename to validate
        allowed_extensions: Set of allowed extensions (with or without leading dot)
        field_name: Name of field for error messages

    Returns:
        str: Original filename if valid

    Raises:
        ValueError: If extension not allowed

    Examples:
        >>> validate_file_extension("doc.txt", {".txt", ".md"}, "Document")
        'doc.txt'

        >>> validate_file_extension("doc.exe", {".txt", ".md"}, "Document")
        ValueError: Invalid Document extension. Must be one of: .md, .txt
    """
    # Normalize extensions to have leading dot
    normalized_extensions = {
        ext if ext.startswith(".") else f".{ext}" for ext in allowed_extensions
    }

    # Get file extension
    file_ext = Path(filename).suffix.lower()

    if file_ext not in normalized_extensions:
        raise ValueError(
            f"Invalid {field_name} extension. Must be one of: {', '.join(sorted(normalized_extensions))}"
        )

    return filename


def validate_filename_safe(
    filename: str, field_name: str = "Filename", max_length: int = 255
) -> str:
    """
    Validate filename is safe (no path traversal, reasonable length).

    Args:
        filename: Filename to validate
        field_name: Name of field for error messages
        max_length: Maximum filename length

    Returns:
        str: Original filename if valid

    Raises:
        ValueError: If filename is unsafe

    Examples:
        >>> validate_filename_safe("document.txt")
        'document.txt'

        >>> validate_filename_safe("../etc/passwd")
        ValueError: Filename contains path traversal characters
    """
    # Check for path traversal (Issue #328 - uses shared validation)
    if contains_path_traversal(filename):
        raise ValueError(f"{field_name} contains path traversal characters")

    # Check length
    if len(filename) > max_length:
        raise ValueError(f"{field_name} too long (maximum {max_length} characters)")

    # Check for dangerous characters
    dangerous_chars = ["<", ">", ":", '"', "|", "?", "*", "\0"]
    if any(char in filename for char in dangerous_chars):
        raise ValueError(f"{field_name} contains dangerous characters")

    return filename


def validate_file_size(
    size: int,
    field_name: str = "File",
    max_size: Optional[int] = None,
    min_size: Optional[int] = None,
) -> int:
    """
    Validate file size bounds.

    Args:
        size: File size in bytes
        field_name: Name of field for error messages
        max_size: Maximum size in bytes
        min_size: Minimum size in bytes

    Returns:
        int: Original size if valid

    Raises:
        ValueError: If size out of bounds

    Examples:
        >>> validate_file_size(1024, "Document", max_size=10*1024*1024)
        1024

        >>> validate_file_size(100*1024*1024, "Document", max_size=50*1024*1024)
        ValueError: Document too large (maximum 50.00 MB)
    """
    if min_size is not None and size < min_size:
        min_mb = min_size / (1024 * 1024)
        raise ValueError(f"{field_name} too small (minimum {min_mb:.2f} MB)")

    if max_size is not None and size > max_size:
        max_mb = max_size / (1024 * 1024)
        raise ValueError(f"{field_name} too large (maximum {max_mb:.2f} MB)")

    return size


# ============================================================================
# Format Validators
# ============================================================================


def validate_email(value: str, field_name: str = "Email") -> str:
    """
    Validate email format (basic check).

    Args:
        value: Email to validate
        field_name: Name of field for error messages

    Returns:
        str: Original email if valid

    Raises:
        ValueError: If email format invalid

    Examples:
        >>> validate_email("user@example.com")
        'user@example.com'

        >>> validate_email("invalid.email")
        ValueError: Invalid Email format
    """
    # Issue #380: Use pre-compiled pattern
    if not _EMAIL_RE.match(value):
        raise ValueError(f"Invalid {field_name} format")

    return value


def validate_url(
    value: str, field_name: str = "URL", require_https: bool = False
) -> str:
    """
    Validate URL format.

    Args:
        value: URL to validate
        field_name: Name of field for error messages
        require_https: Whether to require HTTPS scheme

    Returns:
        str: Original URL if valid

    Raises:
        ValueError: If URL format invalid

    Examples:
        >>> validate_url("https://example.com")
        'https://example.com'

        >>> validate_url("http://example.com", require_https=True)
        ValueError: URL must use HTTPS
    """
    try:
        parsed = urlparse(value)

        # Check basic structure
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid {field_name} format")

        # Check HTTPS requirement
        if require_https and parsed.scheme != "https":
            raise ValueError(f"{field_name} must use HTTPS")

        return value

    except ValueError as e:
        # Re-raise ValueError (our custom errors)
        raise e
    except Exception:
        # Catch other exceptions (parsing errors)
        raise ValueError(f"Invalid {field_name} format")


def validate_uuid(value: str, field_name: str = "UUID") -> str:
    """
    Validate UUID format.

    Args:
        value: UUID to validate
        field_name: Name of field for error messages

    Returns:
        str: Original UUID if valid

    Raises:
        ValueError: If UUID format invalid

    Examples:
        >>> validate_uuid("123e4567-e89b-12d3-a456-426614174000")
        '123e4567-e89b-12d3-a456-426614174000'

        >>> validate_uuid("not-a-uuid")
        ValueError: Invalid UUID format
    """
    # Issue #380: Use pre-compiled pattern
    if not _UUID_RE.match(value.lower()):
        raise ValueError(f"Invalid {field_name} format")

    return value


# ============================================================================
# Composite Validators
# ============================================================================


def validate_username(
    value: str,
    min_length: int = 3,
    max_length: int = 50,
    allowed_special_chars: str = "_-.",
) -> str:
    """
    Validate username with common rules.

    Combines: non-empty, length, alphanumeric+special, sanitization

    Args:
        value: Username to validate
        min_length: Minimum length
        max_length: Maximum length
        allowed_special_chars: Allowed special characters

    Returns:
        str: Sanitized username

    Raises:
        ValueError: If username invalid

    Examples:
        >>> validate_username("john_doe")
        'john_doe'

        >>> validate_username("  John.Doe  ")
        'john.doe'
    """
    # Sanitize
    value = sanitize_string(value, strip=True, lowercase=True)

    # Validate non-empty
    validate_non_empty_string(value, "Username", strip=False)

    # Validate length
    validate_string_length(value, "Username", min_length, max_length)

    # Validate alphanumeric + special chars
    value = sanitize_alphanumeric(
        value, allowed_chars=allowed_special_chars, strip=False
    )

    return value


def validate_password(value: str, min_length: int = 8, max_length: int = 128) -> str:
    """
    Validate password with common rules.

    Args:
        value: Password to validate
        min_length: Minimum length
        max_length: Maximum length

    Returns:
        str: Original password if valid

    Raises:
        ValueError: If password invalid

    Examples:
        >>> validate_password("MyP@ssw0rd!")
        'MyP@ssw0rd!'

        >>> validate_password("short")
        ValueError: Password too short (minimum 8 characters)
    """
    # Validate non-empty
    validate_non_empty_string(value, "Password", strip=False)

    # Validate length
    validate_string_length(value, "Password", min_length, max_length)

    return value
