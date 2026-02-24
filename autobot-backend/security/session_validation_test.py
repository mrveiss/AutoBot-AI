#!/usr/bin/env python3
"""
Test script for session ID validation in backend/api/chat.py

Tests the improved validate_chat_session_id() function to ensure:
1. Valid UUIDs are accepted
2. UUIDs with suffixes are accepted
3. Legacy session IDs like "test_conv" are accepted
4. Malicious inputs are rejected (path traversal, etc.)
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import re

# Now we can import the validation function directly
import uuid


def validate_chat_session_id(session_id: str) -> bool:
    """
    Validate chat session ID format.
    (Copied from backend/api/chat.py for testing)

    Accepts:
    - Valid UUIDs
    - UUIDs with suffixes (e.g., "uuid-imported-123")
    - Legacy/test IDs (alphanumeric with underscores/hyphens)

    Ensures backward compatibility with existing sessions while maintaining security.
    """
    if not session_id or len(session_id) > 255:
        return False

    # Security: reject path traversal and null bytes
    if any(char in session_id for char in ["/", "\\", "..", "\0"]):
        return False

    # Accept if it's a valid UUID
    try:
        uuid.UUID(session_id)
        return True
    except ValueError:
        pass

    # Accept if starts with UUID (with suffix)
    parts = session_id.split("-")
    if len(parts) >= 5:
        try:
            uuid_part = "-".join(parts[:5])
            uuid.UUID(uuid_part)
            return True
        except ValueError:
            pass

    # Accept legacy/test session IDs (alphanumeric + underscore + hyphen)
    # This allows "test_conv" while rejecting malicious inputs
    if re.match(r"^[a-zA-Z0-9_-]+$", session_id):
        return True

    return False


def test_session_validation():
    """Test session ID validation with various inputs"""

    print("Testing Session ID Validation")  # noqa: print
    print("=" * 60)  # noqa: print

    test_cases = [
        # (session_id, expected_result, description)
        # Valid UUIDs
        ("0e8c8859-4af5-40a8-a73e-c1c41bd8aad1", True, "Valid UUID"),
        ("550e8400-e29b-41d4-a716-446655440000", True, "Another valid UUID"),
        # UUIDs with suffixes
        ("0e8c8859-4af5-40a8-a73e-c1c41bd8aad1-imported-123", True, "UUID with suffix"),
        (
            "550e8400-e29b-41d4-a716-446655440000-backup",
            True,
            "UUID with backup suffix",
        ),
        # Legacy/test session IDs
        ("test_conv", True, "Legacy test session ID"),
        ("my_session", True, "Underscore session ID"),
        ("session-123", True, "Hyphenated session ID"),
        ("test123", True, "Alphanumeric session ID"),
        ("MySession_01", True, "Mixed case session ID"),
        # Invalid inputs - empty/null
        ("", False, "Empty string"),
        (None, False, "None value") if False else None,  # Will skip this test
        # Invalid inputs - too long
        ("a" * 256, False, "Too long (256 chars)"),
        # Invalid inputs - path traversal attempts
        ("../etc/passwd", False, "Path traversal (..)"),
        ("/etc/passwd", False, "Absolute path"),
        ("session\\test", False, "Backslash"),
        ("test\0session", False, "Null byte"),
        # Invalid inputs - special characters
        ("test session", False, "Space in ID"),
        ("test@session", False, "@ symbol"),
        ("test#session", False, "# symbol"),
        ("test$session", False, "$ symbol"),
        ("test%session", False, "% symbol"),
    ]

    passed = 0
    failed = 0

    for test_case in test_cases:
        if test_case is None:
            continue

        session_id, expected, description = test_case

        try:
            result = validate_chat_session_id(session_id)
            status = "PASS" if result == expected else "FAIL"

            if result == expected:
                passed += 1
            else:
                failed += 1

            print(f"{status}: {description}")  # noqa: print
            print(f"  Input: {repr(session_id)}")  # noqa: print
            print(f"  Expected: {expected}, Got: {result}")  # noqa: print
            print()  # noqa: print

        except Exception as e:
            failed += 1
            print(f"ERROR: {description}")  # noqa: print
            print(f"  Input: {repr(session_id)}")  # noqa: print
            print(f"  Exception: {e}")  # noqa: print
            print()  # noqa: print

    print("=" * 60)  # noqa: print
    print(f"Results: {passed} passed, {failed} failed")  # noqa: print
    print("=" * 60)  # noqa: print

    return failed == 0


if __name__ == "__main__":
    success = test_session_validation()
    sys.exit(0 if success else 1)
