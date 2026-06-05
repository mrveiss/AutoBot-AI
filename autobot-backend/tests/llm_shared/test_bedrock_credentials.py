# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for AWS Bedrock credential validation (GH#9640).

Tests cover:
- Valid IAM user credentials (AKIA prefix)
- Valid STS temporary credentials (ASIA prefix)
- IAM role authentication (both None)
- Invalid access key formats (wrong prefix, wrong length, invalid chars)
- Invalid secret key formats (wrong length, invalid chars)
- Security warnings for long-lived credentials
"""

import logging
import re

import pytest


# Extract the validation logic to test it in isolation
def validate_credentials(access_key: str | None, secret_key: str | None, logger=None) -> None:
    """
    Validate AWS credential format at initialization.

    This is extracted from BedrockProvider._validate_credentials() for testing.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    # Treat empty strings as None (falsy values = IAM role)
    if not access_key:
        access_key = None
    if not secret_key:
        secret_key = None

    # If both are None, using IAM role authentication - no validation needed
    if access_key is None and secret_key is None:
        logger.info("Using IAM role authentication (no explicit credentials)")
        return

    # If only one is provided, that's an error
    if (access_key is None) != (secret_key is None):
        raise ValueError(
            "AWS credentials incomplete: both access_key_id and secret_access_key "
            "must be provided, or both must be None for IAM role authentication."
        )

    # Validate access key format
    if access_key:
        # AWS access keys are 20 characters: AKIA (IAM) or ASIA (STS) + 16 alphanumeric
        if not re.match(r"^(AKIA|ASIA)[0-9A-Z]{16}$", access_key):
            raise ValueError(
                f"Invalid AWS access key format: {access_key[:8]}... "
                "Expected AKIA or ASIA followed by 16 alphanumeric characters."
            )

        # Security warning for long-lived IAM user credentials
        if access_key.startswith("AKIA"):
            logger.warning(
                "Using long-lived IAM user credentials (AKIA prefix). "
                "For production, consider using STS temporary credentials (ASIA prefix) "
                "or IAM role authentication for enhanced security."
            )
        elif access_key.startswith("ASIA"):
            logger.info("Using STS temporary credentials (ASIA prefix) - recommended")

    # Validate secret key format
    if secret_key:
        # AWS secret keys are exactly 40 characters (base64-encoded 30 bytes)
        if len(secret_key) != 40:
            raise ValueError(
                f"Invalid AWS secret key length: {len(secret_key)} characters. " "Expected exactly 40 characters."
            )

        # Validate character set (base64: A-Za-z0-9+/)
        if not re.match(r"^[A-Za-z0-9+/]{40}$", secret_key):
            raise ValueError(
                "Invalid AWS secret key format: must contain only base64 characters " "(A-Z, a-z, 0-9, +, /)."
            )


class TestBedrockCredentialValidation:
    """Test AWS credential format validation at provider initialization."""

    def test_valid_iam_user_credentials(self, caplog):
        """Valid IAM user credentials (AKIA prefix) should pass validation with warning."""
        caplog.set_level(logging.WARNING)

        # Valid IAM user credentials
        access_key = "AKIAIOSFODNN7EXAMPLE"
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

        # Should not raise
        validate_credentials(access_key, secret_key)

        # Should log security warning for long-lived credentials
        assert any("long-lived IAM user credentials" in record.message for record in caplog.records)

    def test_valid_sts_temporary_credentials(self, caplog):
        """Valid STS temporary credentials (ASIA prefix) should pass validation."""
        caplog.set_level(logging.INFO)

        # Valid STS temporary credentials
        access_key = "ASIAIOSFODNN7EXAMPLE"
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

        # Should not raise
        validate_credentials(access_key, secret_key)

        # Should log info message for STS credentials (recommended)
        assert any("STS temporary credentials" in record.message for record in caplog.records)

    def test_iam_role_authentication(self, caplog):
        """IAM role authentication (both None) should pass validation."""
        caplog.set_level(logging.INFO)

        # Both None = IAM role authentication
        validate_credentials(None, None)

        # Should log info message about IAM role
        assert any("IAM role authentication" in record.message for record in caplog.records)

    def test_invalid_access_key_prefix(self):
        """Access key with invalid prefix should raise ValueError."""
        # Invalid prefix (not AKIA or ASIA)
        access_key = "ZKIAIOSFODNN7EXAMPLE"
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

        with pytest.raises(ValueError, match="Invalid AWS access key format"):
            validate_credentials(access_key, secret_key)

    def test_invalid_access_key_length(self):
        """Access key with invalid length should raise ValueError."""
        # Too short (should be 20 chars total)
        access_key = "AKIAIOSFODNN7EX"
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

        with pytest.raises(ValueError, match="Invalid AWS access key format"):
            validate_credentials(access_key, secret_key)

    def test_invalid_access_key_characters(self):
        """Access key with invalid characters should raise ValueError."""
        # Invalid characters (lowercase not allowed after prefix)
        access_key = "AKIAiosfodnn7example"
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

        with pytest.raises(ValueError, match="Invalid AWS access key format"):
            validate_credentials(access_key, secret_key)

    def test_invalid_secret_key_length(self):
        """Secret key with invalid length should raise ValueError."""
        access_key = "AKIAIOSFODNN7EXAMPLE"
        # Too short (should be exactly 40 chars)
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEX"

        with pytest.raises(ValueError, match="Invalid AWS secret key length"):
            validate_credentials(access_key, secret_key)

    def test_invalid_secret_key_characters(self):
        """Secret key with invalid characters should raise ValueError."""
        access_key = "AKIAIOSFODNN7EXAMPLE"
        # Invalid characters (@ not in base64, but exactly 40 chars)
        secret_key = "wJalrXUtnFEMI/K7MDEN@/bPxRfiCYEXAMPLEKEY"

        with pytest.raises(ValueError, match="Invalid AWS secret key format"):
            validate_credentials(access_key, secret_key)

    def test_incomplete_credentials_access_key_only(self):
        """Providing only access key should raise ValueError."""
        access_key = "AKIAIOSFODNN7EXAMPLE"
        secret_key = None

        with pytest.raises(ValueError, match="AWS credentials incomplete"):
            validate_credentials(access_key, secret_key)

    def test_incomplete_credentials_secret_key_only(self):
        """Providing only secret key should raise ValueError."""
        access_key = None
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

        with pytest.raises(ValueError, match="AWS credentials incomplete"):
            validate_credentials(access_key, secret_key)

    def test_mixed_case_akia_prefix(self):
        """AKIA prefix should be uppercase only."""
        access_key = "akiaIOSFODNN7EXAMPLE"
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

        with pytest.raises(ValueError, match="Invalid AWS access key format"):
            validate_credentials(access_key, secret_key)

    def test_mixed_case_asia_prefix(self):
        """ASIA prefix should be uppercase only."""
        access_key = "asiaIOSFODNN7EXAMPLE"
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

        with pytest.raises(ValueError, match="Invalid AWS access key format"):
            validate_credentials(access_key, secret_key)

    def test_access_key_with_special_characters(self):
        """Access key should not contain special characters."""
        access_key = "AKIA-IOSFODNN7EXAMP"
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

        with pytest.raises(ValueError, match="Invalid AWS access key format"):
            validate_credentials(access_key, secret_key)

    def test_secret_key_too_long(self):
        """Secret key longer than 40 characters should fail."""
        access_key = "AKIAIOSFODNN7EXAMPLE"
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEYEXTRA"

        with pytest.raises(ValueError, match="Invalid AWS secret key length"):
            validate_credentials(access_key, secret_key)

    def test_empty_string_credentials_not_none(self):
        """Empty strings should be treated as incomplete credentials."""
        access_key = ""
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

        # Empty string is falsy, so should be treated as incomplete
        with pytest.raises(ValueError, match="AWS credentials incomplete"):
            validate_credentials(access_key, secret_key)

    def test_both_empty_strings(self):
        """Both empty strings should be treated as IAM role authentication."""
        access_key = ""
        secret_key = ""

        # Both empty strings are falsy, treated like None (IAM role)
        # This should NOT raise
        validate_credentials(access_key, secret_key)
