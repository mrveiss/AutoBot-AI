# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AWS Error Sanitizer - Security hardening for boto3 exceptions.

Sanitizes boto3 error messages before returning to API clients or logging
to prevent information disclosure of AWS account IDs, IAM ARNs, and
credential details.

Security Impact: HIGH
- Prevents AWS account structure enumeration
- Prevents credential validity checks via error messages
- Mitigates targeted attacks based on infrastructure details
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


# Patterns for sensitive AWS information
# Note: IAM ARN must be checked before account ID to avoid partial replacements
IAM_ARN_PATTERN = re.compile(r"arn:aws:iam::\d{12}:[a-zA-Z0-9/_-]+")
AWS_ACCOUNT_ID_PATTERN = re.compile(r"\b\d{12}\b")
ACCESS_KEY_PATTERN = re.compile(r"(?:AKIA|ASIA|AIDA)[A-Z0-9]{12,}")

# Map of boto3 error codes to generic client-facing messages
ERROR_CODE_MAPPING = {
    # Authentication & Authorization
    "UnrecognizedClientException": "Authentication failed",
    "InvalidSignatureException": "Authentication failed",
    "SignatureDoesNotMatch": "Authentication failed",
    "AccessDeniedException": "Access denied",
    "UnauthorizedOperation": "Access denied",
    "InvalidClientTokenId": "Authentication failed",
    "ExpiredToken": "Session expired",
    "ExpiredTokenException": "Session expired",
    # Resource errors
    "ResourceNotFoundException": "Resource not found",
    "ValidationException": "Invalid request parameters",
    "ThrottlingException": "Rate limit exceeded",
    "ServiceUnavailable": "Service temporarily unavailable",
    "RequestLimitExceeded": "Rate limit exceeded",
    "TooManyRequestsException": "Rate limit exceeded",
    "ModelNotReadyException": "Model unavailable",
    "ModelStreamErrorException": "Model streaming error",
    # Model-specific errors
    "ModelErrorException": "Model processing error",
    "ModelTimeoutException": "Model request timeout",
    "ModelNotReadyException": "Model not ready",
}


def _sanitize_message(message: str) -> str:
    """
    Remove sensitive AWS information from error message.

    Args:
        message: Raw error message that may contain sensitive data

    Returns:
        Sanitized message with AWS account IDs, ARNs, and keys removed
    """
    if not message:
        return message

    # Important: Apply IAM ARN pattern BEFORE account ID pattern
    # to avoid partial replacements within ARNs
    sanitized = IAM_ARN_PATTERN.sub("[REDACTED_ARN]", message)

    # Remove AWS account IDs
    sanitized = AWS_ACCOUNT_ID_PATTERN.sub("[REDACTED_ACCOUNT]", sanitized)

    # Remove access keys if accidentally logged
    sanitized = ACCESS_KEY_PATTERN.sub("[REDACTED_KEY]", sanitized)

    return sanitized


def sanitize_boto3_error(
    exception: Exception, operation: str = "AWS operation", audit_log: bool = True
) -> Dict[str, Any]:
    """
    Sanitize boto3 exception for safe logging and client response.

    Args:
        exception: The boto3 exception to sanitize
        operation: Description of the operation that failed (for logging context)
        audit_log: If True, log full details to secure audit log

    Returns:
        Dictionary with:
            - client_message: Sanitized message safe for API clients
            - log_message: Sanitized message safe for general logs
            - error_code: Boto3 error code if available
            - should_retry: Whether the error is transient and retryable
    """
    error_code = None
    raw_message = str(exception)
    should_retry = False

    # Extract error code from boto3 ClientError
    if hasattr(exception, "response"):
        error_info = exception.response.get("Error", {})
        error_code = error_info.get("Code")
        raw_message = error_info.get("Message", raw_message)

        # Log full details to audit log (secure, detailed logging only)
        if audit_log:
            logger.warning(
                "AWS operation failed - AUDIT LOG",
                extra={
                    "operation": operation,
                    "error_code": error_code,
                    "raw_message": raw_message,
                    "request_id": error_info.get("RequestId"),
                    "http_status": exception.response.get("ResponseMetadata", {}).get("HTTPStatusCode"),
                    "security_context": "boto3_error_audit",
                },
            )

    # Determine if error is transient/retryable
    transient_codes = {
        "ThrottlingException",
        "ServiceUnavailable",
        "RequestLimitExceeded",
        "TooManyRequestsException",
        "ModelTimeoutException",
    }
    should_retry = error_code in transient_codes

    # Get generic client-facing message
    client_message = ERROR_CODE_MAPPING.get(error_code, "Service request failed")

    # Sanitize the raw message for general logging
    log_message = _sanitize_message(raw_message)

    return {
        "client_message": client_message,
        "log_message": log_message,
        "error_code": error_code,
        "should_retry": should_retry,
    }


def get_safe_error_string(exception: Exception, operation: str = "AWS operation") -> str:
    """
    Get a client-safe error string from a boto3 exception.

    This is a convenience function for cases where you just need a single
    sanitized error string to return in an error response.

    Args:
        exception: The boto3 exception
        operation: Description of the operation (for audit logging)

    Returns:
        Sanitized error message safe for API clients
    """
    sanitized = sanitize_boto3_error(exception, operation=operation)
    return sanitized["client_message"]
