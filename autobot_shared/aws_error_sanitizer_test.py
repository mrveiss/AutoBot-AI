# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for AWS error sanitizer.

Verifies that boto3 exceptions are properly sanitized to prevent
information disclosure of AWS account IDs, IAM ARNs, and credentials.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from .aws_error_sanitizer import (
    _sanitize_message,
    get_safe_error_string,
    sanitize_boto3_error,
)


class TestAWSErrorSanitizer(unittest.TestCase):
    """Test suite for AWS error sanitization."""

    def test_sanitize_aws_account_id(self):
        """AWS account IDs (12-digit numbers) should be redacted."""
        message = "Access denied for account 123456789012"
        sanitized = _sanitize_message(message)
        self.assertIn("[REDACTED_ACCOUNT]", sanitized)
        self.assertNotIn("123456789012", sanitized)

    def test_sanitize_iam_arn(self):
        """IAM ARNs should be redacted."""
        message = "User arn:aws:iam::123456789012:user/autobot is not authorized"
        sanitized = _sanitize_message(message)
        self.assertIn("[REDACTED_ARN]", sanitized)
        self.assertNotIn("arn:aws:iam::", sanitized)
        self.assertNotIn("123456789012", sanitized)

    def test_sanitize_access_key(self):
        """AWS access keys should be redacted."""
        message = "Invalid access key AKIAIOSFODNN7EXAMPLE"
        sanitized = _sanitize_message(message)
        self.assertIn("[REDACTED_KEY]", sanitized)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", sanitized)

    def test_sanitize_session_token(self):
        """AWS session tokens (ASIA prefix) should be redacted."""
        message = "Session token ASIATESTACCESSKEYID invalid"
        sanitized = _sanitize_message(message)
        self.assertIn("[REDACTED_KEY]", sanitized)
        self.assertNotIn("ASIATESTACCESSKEYID", sanitized)

    def test_sanitize_multiple_sensitive_items(self):
        """Multiple sensitive items in one message should all be redacted."""
        message = (
            "Access denied for arn:aws:iam::123456789012:user/autobot "
            "with key AKIAIOSFODNN7EXAMPLE in account 987654321098"
        )
        sanitized = _sanitize_message(message)
        self.assertIn("[REDACTED_ARN]", sanitized)
        self.assertIn("[REDACTED_KEY]", sanitized)
        self.assertIn("[REDACTED_ACCOUNT]", sanitized)
        self.assertNotIn("123456789012", sanitized)
        self.assertNotIn("987654321098", sanitized)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", sanitized)

    def test_sanitize_empty_message(self):
        """Empty messages should be handled gracefully."""
        self.assertEqual(_sanitize_message(""), "")
        self.assertEqual(_sanitize_message(None), None)

    def test_sanitize_boto3_error_with_client_error(self):
        """boto3 ClientError should be properly sanitized."""
        # Mock boto3 ClientError
        error = MagicMock()
        error.response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "User arn:aws:iam::123456789012:user/test not authorized",
                "RequestId": "test-request-id",
            },
            "ResponseMetadata": {"HTTPStatusCode": 403},
        }

        with patch("autobot_shared.aws_error_sanitizer.logger") as mock_logger:
            result = sanitize_boto3_error(error, operation="test_operation")

            # Check client message is generic
            self.assertEqual(result["client_message"], "Access denied")

            # Check log message is sanitized
            # ARN is redacted (which includes the account ID within it)
            self.assertIn("[REDACTED_ARN]", result["log_message"])
            self.assertNotIn("123456789012", result["log_message"])
            self.assertNotIn("arn:aws:iam::", result["log_message"])

            # Check error code is preserved
            self.assertEqual(result["error_code"], "AccessDeniedException")

            # Check audit logging occurred
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            self.assertIn("AUDIT LOG", call_args[0][0])
            self.assertEqual(call_args[1]["extra"]["error_code"], "AccessDeniedException")

    def test_sanitize_boto3_error_retryable(self):
        """Transient errors should be marked as retryable."""
        error = MagicMock()
        error.response = {"Error": {"Code": "ThrottlingException", "Message": "Rate limit exceeded"}}

        result = sanitize_boto3_error(error, audit_log=False)
        self.assertTrue(result["should_retry"])
        self.assertEqual(result["client_message"], "Rate limit exceeded")

    def test_sanitize_boto3_error_not_retryable(self):
        """Non-transient errors should not be marked as retryable."""
        error = MagicMock()
        error.response = {"Error": {"Code": "ValidationException", "Message": "Invalid parameter"}}

        result = sanitize_boto3_error(error, audit_log=False)
        self.assertFalse(result["should_retry"])

    def test_sanitize_boto3_error_unknown_code(self):
        """Unknown error codes should get generic message."""
        error = MagicMock()
        error.response = {
            "Error": {"Code": "UnknownErrorCode", "Message": "Something went wrong with account 123456789012"}
        }

        result = sanitize_boto3_error(error, audit_log=False)
        self.assertEqual(result["client_message"], "Service request failed")
        self.assertIn("[REDACTED_ACCOUNT]", result["log_message"])

    def test_sanitize_boto3_error_no_response(self):
        """Exceptions without response attribute should be handled."""
        error = Exception("Connection timeout for account 123456789012")

        with patch("autobot_shared.aws_error_sanitizer.logger"):
            result = sanitize_boto3_error(error, audit_log=False)
            self.assertEqual(result["client_message"], "Service request failed")
            self.assertIn("[REDACTED_ACCOUNT]", result["log_message"])
            self.assertIsNone(result["error_code"])

    def test_get_safe_error_string(self):
        """Convenience function should return sanitized client message."""
        error = MagicMock()
        error.response = {"Error": {"Code": "ModelNotReadyException", "Message": "Model not available"}}

        with patch("autobot_shared.aws_error_sanitizer.logger"):
            safe_message = get_safe_error_string(error, operation="test")
            self.assertEqual(safe_message, "Model not ready")

    def test_audit_log_disabled(self):
        """When audit_log=False, no audit logging should occur."""
        error = MagicMock()
        error.response = {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}}

        with patch("autobot_shared.aws_error_sanitizer.logger") as mock_logger:
            sanitize_boto3_error(error, audit_log=False)
            mock_logger.warning.assert_not_called()

    def test_sanitize_preserves_safe_content(self):
        """Safe error content should be preserved."""
        message = "Invalid request: missing required parameter 'modelId'"
        sanitized = _sanitize_message(message)
        self.assertEqual(sanitized, message)

    def test_all_authentication_errors_mapped(self):
        """All authentication error codes should map to generic message."""
        auth_errors = [
            "UnrecognizedClientException",
            "InvalidSignatureException",
            "SignatureDoesNotMatch",
            "InvalidClientTokenId",
        ]

        for error_code in auth_errors:
            error = MagicMock()
            error.response = {"Error": {"Code": error_code, "Message": "Auth failed"}}
            result = sanitize_boto3_error(error, audit_log=False)
            self.assertEqual(
                result["client_message"],
                "Authentication failed",
                f"Error code {error_code} should map to 'Authentication failed'",
            )


if __name__ == "__main__":
    unittest.main()
