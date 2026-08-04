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
"""

from __future__ import annotations

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
