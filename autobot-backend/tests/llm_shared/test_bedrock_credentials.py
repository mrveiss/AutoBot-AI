# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for AWS Bedrock credential validation (GH#9640, #20084).

They exercise production's ``validate_credential_pair``. The key values are AWS's published
``EXAMPLE`` placeholders and malformed variants of them: fake inputs, not credentials.

Tests cover:
- Valid IAM user credentials (AKIA prefix)
- Valid STS temporary credentials (ASIA prefix)
- IAM role authentication (both absent)
- Invalid access key formats (wrong prefix, wrong length, invalid chars)
- Invalid secret key formats (wrong length, invalid chars)
- Security warnings for long-lived credentials
"""

import logging

import pytest

from llm_shared.providers.bedrock_credentials import validate_credential_pair

_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
_LOGGER = "llm_shared.providers.bedrock_credentials"


class TestBedrockCredentialValidation:
    """Test AWS credential format validation at provider initialization."""

    def test_valid_iam_user_credentials(self, caplog):
        """Valid IAM user credentials (AKIA prefix) pass with a warning."""
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            validate_credential_pair(_ACCESS_KEY, _SECRET_KEY)
        assert any("long-lived IAM user credentials" in record.message for record in caplog.records)

    def test_valid_sts_temporary_credentials(self, caplog):
        """Valid STS temporary credentials (ASIA prefix) pass with an info message."""
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            validate_credential_pair("ASIAIOSFODNN7EXAMPLE", _SECRET_KEY)  # pragma: allowlist secret
        assert any("STS temporary credentials" in record.message for record in caplog.records)

    @pytest.mark.parametrize(("access_key", "secret_key"), [(None, None), ("", "")])
    def test_iam_role_authentication(self, caplog, access_key, secret_key):
        """Both absent, as None or empty strings, means IAM role authentication."""
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            validate_credential_pair(access_key, secret_key)
        assert any("IAM role authentication" in record.message for record in caplog.records)

    @pytest.mark.parametrize(
        "access_key",
        [
            "ZKIAIOSFODNN7EXAMPLE",  # prefix is neither AKIA nor ASIA
            "AKIAIOSFODNN7EX",  # too short
            "AKIAiosfodnn7example",  # lowercase after the prefix
            "akiaIOSFODNN7EXAMPLE",  # lowercase AKIA
            "asiaIOSFODNN7EXAMPLE",  # lowercase ASIA
            "AKIA-IOSFODNN7EXAMP",  # special character
            12345,  # not a string: reachable through a vault row's json.loads
        ],
    )
    def test_invalid_access_key_is_refused(self, access_key):
        with pytest.raises(ValueError, match="AWS access key has an unexpected format"):
            validate_credential_pair(access_key, _SECRET_KEY)

    @pytest.mark.parametrize(
        "secret_key",
        [
            "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEX",  # too short
            "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEYEXTRA",  # too long
            "wJalrXUtnFEMI/K7MDEN@/bPxRfiCYEXAMPLEKEY",  # 40 characters, @ is not base64
        ],
    )
    def test_invalid_secret_key_is_refused_without_quoting_it(self, secret_key):
        with pytest.raises(ValueError, match="AWS secret key has an unexpected format") as caught:
            validate_credential_pair(_ACCESS_KEY, secret_key)
        assert secret_key not in str(caught.value), "the error names the field, never its value"

    @pytest.mark.parametrize(
        ("access_key", "secret_key"),
        [(_ACCESS_KEY, None), (None, _SECRET_KEY), ("", _SECRET_KEY), (_ACCESS_KEY, "")],
    )
    def test_incomplete_credentials_are_refused(self, access_key, secret_key):
        with pytest.raises(ValueError, match="AWS credentials are incomplete"):
            validate_credential_pair(access_key, secret_key)
