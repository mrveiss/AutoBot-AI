# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Credential redaction for log/trace safety (GH#9037).

Ensures API keys and sensitive credentials never appear in logs, traces,
or audit records.

#18205: ``redact_dict`` is a thin composition over ``secret_redaction.redact_nested`` and masks a
credential value with the canonical fixed-width placeholder (it used to reveal ``value[:4]...value[-4:]``).
``redact_api_key`` returns that placeholder too, so no path here reveals any part of a key.

#13708: ``redact_string`` also runs the cross-service content scanner
(``autobot_shared.secret_redaction``) after its own patterns, so a credential
in free text this module's narrower ``API_KEY_PATTERNS`` never covered --
PEM blocks, basic-auth URLs, "password is X" phrasing -- is caught too. Every
caller of this module's ``redact_dict``/``redact_string`` gets the wider
coverage for free, including ``llc/services/replay_service.py``'s read-time
redaction, which previously had no content scanner at all in that path.


Boundary: this module is one of three that own a secret detector — see
``docs/developer/REDACTION_BOUNDARY.md`` for which redactor owns which shape of
the problem, and add a new detector there rather than starting another (#16688).
"""

import re
from typing import Any, Dict

from autobot_shared.secret_redaction import (
    BROAD_FRAGMENTS,
    REDACTED_PLACEHOLDER,
    MatchPolicy,
    redact_content,
    redact_nested,
)

# Patterns for common API key formats
API_KEY_PATTERNS = [
    re.compile(r"(sk-[a-zA-Z0-9]{20,})"),  # OpenAI/Anthropic style
    re.compile(r"(gsk_[a-zA-Z0-9]{20,})"),  # Groq
    re.compile(r"([a-zA-Z0-9]{32,})"),  # Generic 32+ char keys
    re.compile(r"(Bearer\s+[a-zA-Z0-9\-._~+/]+=*)"),  # Bearer tokens
]

# Keys in dicts that should be redacted (#16688, #17336). The vocabulary and the
# matching rule are the canonical ones: ``redact_dict`` calls
# ``is_credential_entry(key, value, MatchPolicy.BROAD)``, which normalizes the key
# (lowercase, "_" and "-" stripped) before substring-matching it against
# ``secret_redaction.BROAD_FRAGMENTS`` -- the credential nouns PLUS the
# authorization terms (``Authorization``, ``auth_header``, ``x_auth``). Nothing
# is hand-copied here, so a noun added to the shared vocabulary reaches this
# module's dict/log redaction automatically. ``SENSITIVE_KEYS`` is kept as the
# public name for that vocabulary.
SENSITIVE_KEYS = frozenset(BROAD_FRAGMENTS)


def redact_api_key(value: str) -> str:
    """Redact an API key for safe logging.

    Args:
        value: The API key or token to redact.

    Returns:
        The fixed-width placeholder. No part of the key is kept: eight
        characters of a key are a disclosure (#18205).
    """
    return REDACTED_PLACEHOLDER


def redact_string(text: str) -> str:
    """Redact any API keys found in a string.

    Args:
        text: Text that may contain sensitive values.

    Returns:
        Text with API keys replaced by redacted versions.
    """
    for pattern in API_KEY_PATTERNS:
        text = pattern.sub(lambda m: redact_api_key(m.group(1)), text)
    # #13708: catches PEM blocks, basic-auth URLs, and phrasing this module's
    # own API_KEY_PATTERNS never covered. Runs second so a value the loop
    # above already masked doesn't get scanned a second time.
    return redact_content(text)


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive values from a dictionary, at any depth (dicts, lists, tuples, sets).

    A thin composition over ``secret_redaction.redact_nested`` (#18205), the one recursive mapping
    redactor; this function only picks the LLM layer's two deviations from its defaults:

    * ``exempt_counts=False``: this layer always masked a count of a credential noun
      (``max_tokens: 4096``), and the #17336/#17337 rule is that no name leaves a caller's
      masked set; only the template export and the API config readout unmask counts.
    * ``extra_scan=redact_string``: every string left unmasked also goes through this module's
      ``API_KEY_PATTERNS`` (the 32+ character generic key among them), which ``redact_content`` does not cover.

    A credential value is masked with the canonical fixed-width placeholder, never a fragment of it.
    """
    return redact_nested(
        data, MatchPolicy.BROAD, exempt_counts=False, extra_scan=redact_string, mask_credential_urls=True
    )


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
