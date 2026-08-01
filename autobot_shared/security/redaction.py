# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Canonical secret-redaction utilities (#12242).

A redactor is a security control, so there is exactly ONE implementation of it
shared across all backends — previously the SLM backend carried two independent
one-off copies (`_redact_app_log_line` in ``api/monitoring.py`` and
`_mask_secret_extra_vars` in ``api/code_sync.py``) with divergent coverage.

Two shapes are covered, sharing one canonical secret-key/pattern set:

* :func:`redact_text` — line/text level. Masks ``Authorization``/``Bearer``
  headers and ``api_key=/token=/secret=/password=`` style key/value pairs in raw
  log-line text.
* :func:`redact_mapping` — mapping/kv level. Masks dict values whose key matches
  a known secret key fragment.
"""

import re
from typing import Dict, Mapping

# ---------------------------------------------------------------------------
# Text / log-line redaction (union of the former monitoring._redact_app_log_line)
# ---------------------------------------------------------------------------

# ``Authorization: <anything>`` / ``Authorization=<anything>`` — masks the whole
# credential (covers ``Bearer <jwt>``, ``Basic <b64>``, raw tokens, etc.).
_AUTH_HEADER_RE = re.compile(r"(?i)(authorization\s*[:=]\s*).+")

# ``api_key=…`` / ``token: …`` / ``secret=…`` / ``password=…`` key/value pairs.
# The optional ``[a-z0-9_]*[_-]?`` prefix also matches prefixed keys such as
# ``client_secret=``, ``access_token:``, ``db_password=`` (#12333) — anchored
# so the secret word must sit immediately before the ``[:=]``, so ordinary
# prose (``the password reset flow``) and near-miss keys
# (``password_hash_algorithm=``) are never matched.
_SECRET_KV_RE = re.compile(
    r"(?i)\b([a-z0-9_]*[_-]?(?:api[_-]?key|token|secret|password|passwd))\b(\s*[:=]\s*)([^\s,;\"']+)"
)

# ---------------------------------------------------------------------------
# Mapping redaction (union of the former code_sync._mask_secret_extra_vars)
# ---------------------------------------------------------------------------

# Secret key fragments — a mapping value is masked when any fragment is a prefix
# of, or a substring of, the (lowercased) key.
_SECRET_KEY_FRAGMENTS = (
    "password",
    "secret",
    "token",
    "key",
    "pass",
    "credential",
    "cert",
    "private",
)

_MASK = "***"


def redact_text(text: str) -> str:
    """Redact common secret patterns from a line/blob of *text*.

    Masks ``Authorization``/``Bearer`` headers and
    ``api_key/token/secret/password`` key/value pairs. Non-secret text is
    returned unchanged.
    """
    text = _AUTH_HEADER_RE.sub(r"\1" + _MASK, text)
    text = _SECRET_KV_RE.sub(r"\1\2" + _MASK, text)
    return text


def redact_mapping(mapping: Mapping[str, str]) -> Dict[str, str]:
    """Return a copy of *mapping* with secret values replaced by ``***``.

    A value is masked when its key (lowercased) starts with, or contains, any
    known secret key fragment (``password``, ``secret``, ``token``, ``key``,
    ``pass``, ``credential``, ``cert``, ``private``).
    """
    redacted: Dict[str, str] = {}
    for key, value in mapping.items():
        lower_key = key.lower()
        if any(lower_key.startswith(frag) or frag in lower_key for frag in _SECRET_KEY_FRAGMENTS):
            redacted[key] = _MASK
        else:
            redacted[key] = value
    return redacted


__all__ = ["redact_text", "redact_mapping"]
