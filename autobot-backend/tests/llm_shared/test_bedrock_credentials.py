# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for Bedrock provider AWS credential validation (MVA-3006)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def mock_secrets_service():
    """Mock SecretsService to avoid database dependencies."""
    with patch("llm_shared.providers.bedrock.get_secrets_service") as mock:
        service = MagicMock()
        service.get_secret.side_effect = Exception("No secret found")
        mock.return_value = service
        yield mock


@pytest.fixture()
def mock_boto3():
    """Mock boto3 to avoid AWS dependencies."""
    with patch("llm_shared.providers.bedrock.boto3") as mock:
        yield mock


class TestBedrockCredentialValidation:
    """Test AWS credential format validation and type detection."""

    def test_valid_iam_user_credentials(self, mock_secrets_service, mock_boto3):
        """Valid IAM user credentials (AKIA) should pass validation with warning."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
        assert is_valid is True
        assert error is None

    def test_valid_sts_temporary_credentials(self, mock_secrets_service, mock_boto3):
        """Valid STS temporary credentials (ASIA) should pass validation."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key="ASIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
        assert is_valid is True
        assert error is None

    def test_iam_role_credentials_none(self, mock_secrets_service, mock_boto3):
        """IAM role (both None) should be valid for EC2/ECS environments."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key=None,
            secret_key=None,
        )
        assert is_valid is True
        assert error is None

    def test_invalid_access_key_format_short(self, mock_secrets_service, mock_boto3):
        """Access key that's too short should fail validation."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key="AKIA1234",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
        assert is_valid is False
        assert "Invalid AWS access key format" in error

    def test_invalid_access_key_format_wrong_prefix(self, mock_secrets_service, mock_boto3):
        """Access key with wrong prefix should fail validation."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key="XKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
        assert is_valid is False
        assert "Invalid AWS access key format" in error

    def test_invalid_access_key_format_lowercase(self, mock_secrets_service, mock_boto3):
        """Access key with lowercase characters should fail validation."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key="AKIAiosfodnn7example",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
        assert is_valid is False
        assert "Invalid AWS access key format" in error

    def test_invalid_secret_key_too_short(self, mock_secrets_service, mock_boto3):
        """Secret key shorter than 40 characters should fail validation."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="tooshort",
        )
        assert is_valid is False
        assert "Invalid AWS secret key length" in error
        assert "Expected 40 characters" in error

    def test_invalid_secret_key_too_long(self, mock_secrets_service, mock_boto3):
        """Secret key longer than 40 characters should fail validation."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEYTOOLONG",
        )
        assert is_valid is False
        assert "Invalid AWS secret key length" in error

    def test_missing_access_key_only(self, mock_secrets_service, mock_boto3):
        """Missing access key with provided secret key should fail."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key=None,
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
        assert is_valid is False
        assert "must be provided together" in error

    def test_missing_secret_key_only(self, mock_secrets_service, mock_boto3):
        """Missing secret key with provided access key should fail."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key=None,
        )
        assert is_valid is False
        assert "must be provided together" in error

    def test_long_lived_credentials_warning(self, mock_secrets_service, mock_boto3, caplog):
        """Long-lived IAM credentials (AKIA) should log a security warning."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
        assert is_valid is True
        assert error is None
        # Check that warning about long-lived credentials was logged
        assert any("long-lived IAM user credentials" in record.message for record in caplog.records)

    def test_temporary_credentials_info_log(self, mock_secrets_service, mock_boto3, caplog):
        """STS temporary credentials (ASIA) should log an info message."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key="ASIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
        assert is_valid is True
        assert error is None
        # Check that info about temporary credentials was logged
        assert any("STS temporary credentials" in record.message for record in caplog.records)


class TestBedrockCredentialResolutionValidation:
    """Test that credential validation is integrated into credential resolution."""

    @patch.dict("os.environ", {"AWS_ACCESS_KEY_ID": "INVALID", "AWS_SECRET_ACCESS_KEY": "secret"})
    def test_invalid_credentials_raise_valueerror(self, mock_secrets_service, mock_boto3):
        """Invalid credentials should raise ValueError during resolution."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        with pytest.raises(ValueError) as exc_info:
            provider._resolve_credentials()
        assert "credential validation failed" in str(exc_info.value).lower()

    @patch.dict(
        "os.environ",
        {
            "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
            "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        },
    )
    def test_valid_credentials_pass_resolution(self, mock_secrets_service, mock_boto3):
        """Valid credentials should successfully resolve."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        access_key, secret_key, region = provider._resolve_credentials()
        assert access_key == "AKIAIOSFODNN7EXAMPLE"
        assert secret_key == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert region == "us-east-1"  # default region

    @patch.dict("os.environ", {}, clear=True)
    def test_iam_role_credentials_pass_resolution(self, mock_secrets_service, mock_boto3):
        """IAM role (no explicit credentials) should successfully resolve."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        access_key, secret_key, region = provider._resolve_credentials()
        assert access_key is None
        assert secret_key is None
        assert region == "us-east-1"  # default region


class TestBedrockCredentialFormatEdgeCases:
    """Test edge cases for credential format validation."""

    def test_access_key_with_special_characters(self, mock_secrets_service, mock_boto3):
        """Access key with special characters should fail validation."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key="AKIA@#$%ODNN7EXAMPL",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
        assert is_valid is False
        assert "Invalid AWS access key format" in error

    def test_access_key_exactly_20_chars_akia(self, mock_secrets_service, mock_boto3):
        """AKIA access key with exactly 20 characters should pass."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key="AKIAIOSFODNN7EXAMPLE",  # exactly 20 chars
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
        assert is_valid is True
        assert error is None

    def test_access_key_exactly_20_chars_asia(self, mock_secrets_service, mock_boto3):
        """ASIA access key with exactly 20 characters should pass."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key="ASIAIOSFODNN7EXAMPLE",  # exactly 20 chars
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
        assert is_valid is True
        assert error is None

    def test_secret_key_exactly_40_chars(self, mock_secrets_service, mock_boto3):
        """Secret key with exactly 40 characters should pass."""
        from llm_shared.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        is_valid, error = provider._validate_credentials(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLE",  # exactly 40 chars
        )
        assert is_valid is True
        assert error is None
