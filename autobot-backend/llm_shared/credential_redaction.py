# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Credential redaction for log/trace safety (GH#9037).

Ensures API keys and sensitive credentials never appear in logs, traces,
or audit records.
"""

import re
from typing import Any, Dict

# Patterns for common API key formats
API_KEY_PATTERNS = [
    re.compile(r"(sk-[a-zA-Z0-9]{20,})"),  # OpenAI/Anthropic style
    re.compile(r"(gsk_[a-zA-Z0-9]{20,})"),  # Groq
    re.compile(r"([a-zA-Z0-9]{32,})"),  # Generic 32+ char keys
    re.compile(r"(Bearer\s+[a-zA-Z0-9\-._~+/]+=*)"),  # Bearer tokens
]

# Keys in dicts that should be redacted
SENSITIVE_KEYS = {
    "api_key",
    "apiKey",
    "api-key",
    "token",
    "bearer",
    "password",
    "secret",
    "credential",
    "auth",
    "authorization",
}


def redact_api_key(value: str) -> str:
    """Redact an API key for safe logging.

    Args:
        value: The API key or token to redact.

    Returns:
        Redacted string showing only first/last 4 chars.
    """
    if not value or len(value) < 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def redact_string(text: str) -> str:
    """Redact any API keys found in a string.

    Args:
        text: Text that may contain sensitive values.

    Returns:
        Text with API keys replaced by redacted versions.
    """
    for pattern in API_KEY_PATTERNS:
        text = pattern.sub(lambda m: redact_api_key(m.group(1)), text)
    return text


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive values from a dictionary.

    Args:
        data: Dictionary that may contain sensitive keys.

    Returns:
        New dictionary with sensitive values redacted.
    """
    redacted = {}
    for key, value in data.items():
        key_lower = key.lower().replace("_", "").replace("-", "")
        if any(sensitive in key_lower for sensitive in SENSITIVE_KEYS):
            # Redact this key's value
            if isinstance(value, str):
                redacted[key] = redact_api_key(value)
            else:
                redacted[key] = "***"
        elif isinstance(value, dict):
            # Recursively redact nested dicts
            redacted[key] = redact_dict(value)
        elif isinstance(value, str):
            # Redact any API keys in string values
            redacted[key] = redact_string(value)
        else:
            redacted[key] = value
    return redacted


def safe_repr(obj: Any, max_depth: int = 3) -> str:
    """Generate a safe string representation with redaction.

    Args:
        obj: Object to represent.
        max_depth: Maximum nesting depth to traverse.

    Returns:
        String representation with sensitive values redacted.
    """
    if max_depth <= 0:
        return "..."

    if isinstance(obj, dict):
        redacted = redact_dict(obj)
        items = [f"{k}={safe_repr(v, max_depth - 1)}" for k, v in redacted.items()]
        return "{" + ", ".join(items) + "}"
    elif isinstance(obj, (list, tuple)):
        items = [safe_repr(item, max_depth - 1) for item in obj]
        return "[" + ", ".join(items) + "]"
    elif isinstance(obj, str):
        return repr(redact_string(obj))
    else:
        return repr(obj)


class CredentialRedactionFilter:
    """Logging filter that redacts sensitive credentials.

    Can be added to Python logging handlers to automatically scrub
    API keys from log messages.
    """

    def filter(self, record) -> bool:
        """Filter a log record, redacting sensitive values.

        Args:
            record: LogRecord to filter.

        Returns:
            True (always allow the record through after redaction).
        """
        # Redact the message
        if isinstance(record.msg, str):
            record.msg = redact_string(record.msg)

        # Redact any args that are dicts
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_dict(record.args)
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(redact_dict(arg) if isinstance(arg, dict) else arg for arg in record.args)

        return True


__all__ = [
    "redact_api_key",
    "redact_string",
    "redact_dict",
    "safe_repr",
    "CredentialRedactionFilter",
]
