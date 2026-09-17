#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Credential-aware repr redaction for Pydantic settings models.

Why this exists
---------------
``repr()`` of a Pydantic model prints every field value.  Any code path that
formats a settings object — most commonly ``unittest.mock.patch.object`` on a
misspelled attribute, which raises
``AttributeError("<repr of obj> does not have the attribute 'x'")`` — therefore
dumps the whole configuration, secrets included, into pytest output and from
there into CI logs.

Redaction rules
---------------
* Field **names are always preserved**.  Only *values* are masked, so a
  configuration dump stays diagnosable ("which fields exist, which are set").
* Only fields whose name *ends with* a credential noun are masked.  Suffix
  matching (not substring) keeps ``tokenizers_parallelism`` and
  ``speculation_num_tokens`` readable while catching ``jwt_secret``.
* URL-shaped fields keep scheme/host/port/path and lose only the **userinfo**
  password.  ``database_url`` and ``redis_url`` routinely embed credentials
  (``postgresql://user:pw@host/db``), so exempting them wholesale would leak
  through the very vector this module closes — but host and database name are
  exactly what an operator needs to diagnose a connection problem.
* Location-shaped fields (``*_path``, ``*_file``, ``*_dir``) are never masked —
  a filename is not a credential and is needed for diagnosis.
* Empty / unset values are shown verbatim.  ``jwt_secret=''`` leaks nothing and
  answers the most common diagnostic question directly.

Issue: #13325

Content-scanning companion (#13708)
------------------------------------
Everything above is *name-keyed*: it only masks a value when the field name
already says it holds a credential. ``scan_content_for_credentials`` and
``redact_content`` are the opposite -- they look at the *content* of free
text (a message body, a document, a log line) with no field name to go on,
for exactly the case a config-model redactor cannot reach: a credential
sitting in prose ("your temporary password is X"), not behind a named field.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, ClassVar, FrozenSet, Iterable, Tuple
from urllib.parse import urlsplit, urlunsplit

# Masked stand-in for a populated credential value.  Fixed width so the mask
# never discloses the length of the real secret.
REDACTED_PLACEHOLDER = "**********"

# A field is credential-shaped when its name equals one of these nouns or ends
# with ``_<noun>``.  Suffix matching avoids false positives on names that merely
# contain the noun (``tokenizers_parallelism``, ``llm_key_rotation_grace_secs``).
# Plurals are listed explicitly: a future ``api_keys: dict`` must not fail open.
CREDENTIAL_SUFFIXES: Tuple[str, ...] = (
    "secret",
    "secrets",
    "key",
    "keys",
    "token",
    "tokens",
    "password",
    "passwords",
    "passwd",
    "pass",
    "passphrase",
    "credential",
    "credentials",
    "salt",
    "dsn",
    "signature",
    "pem",
    "cert",
    "seed",
)

# Names ending in these are locations pointing *at* a credential, not the
# credential itself.  ``tls_key_path`` and ``service_key_file`` must stay visible
# so an operator can tell which file was loaded.  ``_url`` is deliberately NOT
# here — see URL_SUFFIXES.
LOCATION_SUFFIXES: Tuple[str, ...] = ("_path", "_file", "_dir", "_id")

# Names ending in these hold a connection string.  They are redacted in-place
# (userinfo only) rather than exempted or fully masked.
URL_SUFFIXES: Tuple[str, ...] = ("_url", "_uri", "_dsn")


def is_credential_field(name: str) -> bool:
    """Return True when a field name denotes a credential *value*."""
    if not name:
        return False
    lowered = name.lower()
    if lowered.endswith(LOCATION_SUFFIXES):
        return False
    return any(lowered == suffix or lowered.endswith(f"_{suffix}") for suffix in CREDENTIAL_SUFFIXES)


def is_url_field(name: str) -> bool:
    """Return True when a field name denotes a connection string."""
    lowered = (name or "").lower()
    return lowered.endswith(URL_SUFFIXES) or lowered in ("url", "uri", "dsn")


def redact_url_userinfo(value: str, mask_username: bool = False) -> str:
    """Strip the password from a URL, preserving scheme/host/port/path.

    ``mask_username`` additionally hides the user component, for schemes that
    carry the credential there instead (a Sentry-style ``https://<key>@host/1``).
    """
    try:
        parsed = urlsplit(value)
    except ValueError:
        # Unparseable: fail closed rather than emit an unredacted string.
        return REDACTED_PLACEHOLDER
    if not parsed.password and not (mask_username and parsed.username):
        return value
    user = REDACTED_PLACEHOLDER if (mask_username and parsed.username) else (parsed.username or "")
    netloc = f"{user}:{REDACTED_PLACEHOLDER}@" if parsed.password else f"{user}@"
    netloc += parsed.hostname or ""
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunsplit(parsed._replace(netloc=netloc))


def redact_value(name: str, value: Any) -> Any:
    """Mask ``value`` when ``name`` is credential-shaped and the value is set."""
    if value is None or value == "":
        return value
    # URL handling runs first: a ``*_dsn`` name matches both rule sets, and
    # in-place userinfo redaction is strictly more diagnosable than a full mask.
    if is_url_field(name) and isinstance(value, str):
        return redact_url_userinfo(value, mask_username=is_credential_field(name))
    if not is_credential_field(name):
        return value
    return REDACTED_PLACEHOLDER


class RedactedReprMixin:
    """Mask credential *values* in ``repr()`` / ``str()`` of a Pydantic model.

    Mix in before the Pydantic base class.  ``model_dump()`` and normal
    attribute access are deliberately untouched — only the human-readable
    rendering is redacted.
    """

    #: Field names that are credential-shaped but hold no secret — typically a
    #: path *to* a key (``ca_key = "certs/ca/ca-key.pem"``).  Listing them keeps
    #: the value visible for diagnosis instead of masking a filename.
    NON_CREDENTIAL_FIELDS: ClassVar[FrozenSet[str]] = frozenset()

    def __repr_args__(self) -> Iterable[Tuple[str | None, Any]]:
        exempt: FrozenSet[str] = getattr(self, "NON_CREDENTIAL_FIELDS", frozenset())
        for name, value in super().__repr_args__():  # type: ignore[misc]
            if not name or name in exempt:
                yield name, value
            else:
                yield name, redact_value(name, value)


# ---------------------------------------------------------------------------
# Content-scanning companion (#13708)
# ---------------------------------------------------------------------------

#: One detected credential-shaped span in free text: which rule matched, where,
#: and how confident the rule is. Structured so a caller can quarantine or log
#: instead of only ever getting back a mangled string with no explanation.
@dataclass(frozen=True)
class ContentMatch:
    pattern: str
    start: int
    end: int
    confidence: str  # "high" | "medium"


_PEM_BLOCK_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----")

# A JWT is three base64url segments joined by dots; the first two decode to
# JSON objects, so both start with the base64url encoding of ``{"`` (``eyJ``).
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")

# Provider-specific prefixes with a fixed, well-documented shape — the same
# patterns every mainstream secret scanner (gitleaks, trufflehog, detect-secrets)
# keys on, so a match here is unambiguous regardless of surrounding context.
_KNOWN_PREFIX_RE = re.compile(
    r"\b(?:"
    r"sk-[A-Za-z0-9]{20,}"  # OpenAI/Anthropic
    r"|gsk_[A-Za-z0-9]{20,}"  # Groq
    r"|gh[pousr]_[A-Za-z0-9]{30,}"  # GitHub (personal/oauth/user-to-server/server-to-server/refresh)
    r"|AKIA[0-9A-Z]{16}"  # AWS access key ID
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"  # Slack
    r")\b"
)

# scheme://user:password@host -- credentials embedded directly in a URL.
_BASIC_AUTH_URL_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/:@]+:[^\s/@]+@[^\s]+")

# "your password is X", "here is your api key: Y" -- a signup/notification
# email's own words pointing at the value that follows.  The value itself
# still has to look credential-shaped (checked in code, not the regex): a
# plain identifier like ``getKey()`` must not qualify just because it follows
# the word "key".
_CREDENTIAL_PHRASE_RE = re.compile(
    r"\b(?:password|passwd|api[ _-]?key|secret|token)\b\s*(?:is|:|=)\s*[\"']?([^\s\"'.,;]{6,})[\"']?",
    re.IGNORECASE,
)

# A data: URI's base64 payload is long, high-entropy, and not a credential --
# excluded up front so the generic scanner below never has to reason about it.
_DATA_URI_RE = re.compile(r"data:[^,\s]+;base64,[A-Za-z0-9+/=]+")

# A bare, contiguous run with no whitespace, long enough to plausibly be a
# token and short enough that a base64 image (typically hundreds+ chars) is
# excluded by length alone even before the data: URI check above catches it.
# Deliberately excludes ``_`` and ``/``: both are legal in some token alphabets,
# but keeping them out of this generic fallback (prefixed formats like ``ghp_``
# are already caught by _KNOWN_PREFIX_RE) is what keeps a snake_case constant
# name or a URL path from reading as one long "random" run -- measured against
# real samples, that was the single biggest source of false positives here.
_HIGH_ENTROPY_RE = re.compile(r"\b[A-Za-z0-9+-]{20,64}\b")
_HIGH_ENTROPY_MIN_BITS_PER_CHAR = 4.0

# Pure-hex runs at exactly these lengths are overwhelmingly a hash/checksum/
# commit SHA (md5/sha1/sha256), not a credential -- and indistinguishable from
# one by entropy alone, since both are effectively random hex to this measure.
_HASH_LIKE_LENGTHS = frozenset({32, 40, 64})
_PURE_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def _looks_like_identifier(value: str) -> bool:
    """A bare name or call (``getKey()``, ``apiKey``) -- not a credential value."""
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\(\))?", value))


def _is_hash_like(value: str) -> bool:
    return len(value) in _HASH_LIKE_LENGTHS and bool(_PURE_HEX_RE.match(value))


def _shannon_entropy(s: str) -> float:
    """Bits per character. Higher means less like ordinary words, more like a random token."""
    if not s:
        return 0.0
    counts: dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    length = len(s)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


def scan_content_for_credentials(text: str) -> list[ContentMatch]:
    """Find credential-shaped spans in free text with no field name to key on.

    Six rule classes, checked in the order below so an overlapping later match
    (e.g. the generic high-entropy scan) never re-reports a span an earlier,
    more specific rule already explains: PEM private-key blocks, JWTs, known
    provider key prefixes, basic-auth URLs, "password is X"-style phrasing,
    and finally a bounded-length high-entropy token. Returns matches sorted
    by position; overlapping spans keep only the first (most specific) rule.
    """
    if not text:
        return []

    matches: list[ContentMatch] = []
    claimed: list[tuple[int, int]] = []

    def _claim(start: int, end: int) -> bool:
        if any(start < c_end and end > c_start for c_start, c_end in claimed):
            return False
        claimed.append((start, end))
        return True

    for m in _PEM_BLOCK_RE.finditer(text):
        if _claim(m.start(), m.end()):
            matches.append(ContentMatch("pem_private_key", m.start(), m.end(), "high"))
    for m in _JWT_RE.finditer(text):
        if _claim(m.start(), m.end()):
            matches.append(ContentMatch("jwt", m.start(), m.end(), "high"))
    for m in _KNOWN_PREFIX_RE.finditer(text):
        if _claim(m.start(), m.end()):
            matches.append(ContentMatch("known_key_prefix", m.start(), m.end(), "high"))
    for m in _BASIC_AUTH_URL_RE.finditer(text):
        if _claim(m.start(), m.end()):
            matches.append(ContentMatch("basic_auth_url", m.start(), m.end(), "high"))
    for m in _CREDENTIAL_PHRASE_RE.finditer(text):
        value = m.group(1)
        if _looks_like_identifier(value) or not any(c.isdigit() or not c.isalnum() for c in value):
            continue  # a plain word/identifier following "password"/"key" is not itself a value
        if _claim(m.start(1), m.end(1)):
            matches.append(ContentMatch("credential_phrase", m.start(1), m.end(1), "medium"))

    data_uri_spans = [(m.start(), m.end()) for m in _DATA_URI_RE.finditer(text)]
    for m in _HIGH_ENTROPY_RE.finditer(text):
        if any(s <= m.start() < e for s, e in data_uri_spans):
            continue
        candidate = m.group()
        if _is_hash_like(candidate):
            continue
        if _shannon_entropy(candidate) < _HIGH_ENTROPY_MIN_BITS_PER_CHAR:
            continue
        if _claim(m.start(), m.end()):
            matches.append(ContentMatch("high_entropy", m.start(), m.end(), "medium"))

    return sorted(matches, key=lambda mm: mm.start)


def redact_content(text: str) -> str:
    """Mask every credential-shaped span :func:`scan_content_for_credentials` finds.

    Convenience wrapper for callers that only need the redacted text, not the
    structured matches (e.g. logging, or a second redaction pass over content
    a name-keyed pass already ran on).
    """
    matches = scan_content_for_credentials(text)
    if not matches:
        return text
    out = text
    for m in sorted(matches, key=lambda mm: mm.start, reverse=True):
        out = out[: m.start] + REDACTED_PLACEHOLDER + out[m.end :]
    return out
