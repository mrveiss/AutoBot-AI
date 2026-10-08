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


Boundary: this module is one of seven that own a secret detector — see
``docs/developer/REDACTION_BOUNDARY.md`` for which redactor owns which shape of
the problem, and add a new detector there rather than starting an eighth (#16688).
"""

import re
from typing import Dict, Mapping

from autobot_shared.env_utils import env_int

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

# ---------------------------------------------------------------------------
# Cloud-provider identifiers (#15324)
# ---------------------------------------------------------------------------

# A boto3 ``ClientError``'s message embeds the caller's identity, e.g.
#
#   An error occurred (AccessDeniedException) when calling the InvokeModel
#   operation: User: arn:aws:iam::123456789012:user/svc-bedrock is not
#   authorized to perform: bedrock:InvokeModel on resource:
#   arn:aws:bedrock:eu-west-1:123456789012:model/anthropic...
#
# The account number identifies the AWS account; the trailing resource segment
# names a principal or resource. Both are disclosure when a provider error is
# logged or returned to a caller.
#
# WHY THIS LIVES HERE rather than in a new module: this file's own header says a
# redactor is a security control with exactly ONE implementation, because two
# divergent one-off copies are what #12242 consolidated. A stashed draft of this
# fix (#15324) added a separate ``autobot_shared/aws_error_sanitizer`` instead,
# which would have reintroduced precisely that split — and it imported a module
# that was never written, so it could not have run at all.
#
# DELIBERATELY NARROW: only the account field and the resource tail inside a
# well-formed ARN are masked. The partition, service and region are kept, because
# "which service refused me, in which region" is the whole diagnostic value of
# the error, and a redactor that removes it will be worked around. A bare
# 12-digit number elsewhere in a message is NOT masked — matching every such
# number would hit ports, sizes and timestamps, and a redactor with false
# positives is one people route around.
_ARN_RE = re.compile(
    r"\barn:(?P<partition>aws[a-z-]*):(?P<service>[a-z0-9-]*):(?P<region>[a-z0-9-]*):"
    r"(?P<account>\d{12}):(?P<tail>[^\s\"',;)]*)"
)


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


def redact_cloud_identifiers(text: str) -> str:
    """Mask AWS account numbers and resource tails inside ARNs in *text* (#15324).

    ``arn:aws:iam::123456789012:user/svc`` -> ``arn:aws:iam::***:***``.
    Partition, service and region survive, so an error still says which service
    refused the call and where. Text containing no ARN is returned unchanged.
    """

    def _mask(match: "re.Match[str]") -> str:
        return f"arn:{match.group('partition')}:{match.group('service')}:" f"{match.group('region')}:{_MASK}:{_MASK}"

    return _ARN_RE.sub(_mask, text)


def redact_provider_error(exc: BaseException) -> str:
    """A provider exception rendered safe to log or return to a caller (#15324).

    Applies both the secret patterns and the cloud-identifier patterns. Returns
    the class name alone when the message is empty, so a caller never logs a
    bare ``''`` that reads as "no error".
    """
    message = str(exc).strip()
    if not message:
        return type(exc).__name__
    return redact_cloud_identifiers(redact_text(message))


# ---------------------------------------------------------------------------
# Untrusted-value neutralisation for log lines (#13602)
# ---------------------------------------------------------------------------

#: Longest untrusted value interpolated into a single log line. A rejected path
#: can be megabytes long and a log store is not the place to replay it.
LOG_VALUE_MAX_CHARS = env_int("AUTOBOT_LOG_VALUE_MAX_CHARS", 256)

#: Everything that lets the author of a value author *log records* rather than
#: appear inside one: the C0 controls (CR/LF start a new line, so a forged
#: ``2026-01-01 ERROR ...`` entry is one ``\r\n`` away), DEL and the C1 range,
#: ESC-driven ANSI sequences that rewrite a terminal reading the log, the
#: Unicode line/paragraph separators many viewers break on, and the bidi
#: overrides that reorder a rendered line without changing its bytes.
_UNSAFE_LOG_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]")


def sanitize_log_value(value: object, *, max_chars: int | None = None) -> str:
    r"""Render *value* safe to interpolate into a log line (#13602).

    This is **not** a secret detector and declares no secret vocabulary of its
    own — it neutralises *structure*, not content, so it is not an eighth
    implementation under ``docs/developer/REDACTION_BOUNDARY.md``. Pair it with
    :func:`redact_text` when the value may also carry a credential.

    Control characters become a visible ``\xNN``/``\uNNNN`` escape rather than
    being dropped, so the rejected input stays diagnosable; the result is
    truncated to *max_chars* (default :data:`LOG_VALUE_MAX_CHARS`) with an
    explicit marker, so a log line can never be padded out by its subject.
    """
    text = value if isinstance(value, str) else repr(value)
    escaped = _UNSAFE_LOG_CHARS.sub(lambda m: _escape_char(m.group(0)), text)
    limit = LOG_VALUE_MAX_CHARS if max_chars is None else max_chars
    if limit < 0:
        # #13602 review: a negative bound skipped truncation entirely, so
        # AUTOBOT_LOG_VALUE_MAX_CHARS=-1 (or an explicit negative argument) let a rejected
        # request put its whole path in the log -- the opposite of what this function is
        # for. A guard has no "unlimited" reading, so a negative bound is refused rather
        # than honoured: fall back to the module default, and to 0 if that is misconfigured
        # negative too, so the bound can never be switched off from configuration.
        limit = LOG_VALUE_MAX_CHARS if LOG_VALUE_MAX_CHARS >= 0 else 0
    if len(escaped) > limit:
        return f"{escaped[:limit]}...[truncated {len(escaped) - limit} chars]"
    return escaped


def _escape_char(char: str) -> str:
    """One unsafe character as a readable escape."""
    code = ord(char)
    return f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}"


__all__ = [
    "LOG_VALUE_MAX_CHARS",
    "redact_text",
    "redact_mapping",
    "redact_cloud_identifiers",
    "redact_provider_error",
    "sanitize_log_value",
]
