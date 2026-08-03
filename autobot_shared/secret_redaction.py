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
* Location-shaped fields (``*_path``, ``*_file``, ``*_dir``, ``*_url``) are
  never masked — a filename is not a credential and is needed for diagnosis.
* Empty / unset values are shown verbatim.  ``jwt_secret=''`` leaks nothing and
  answers the most common diagnostic question directly.

Issue: #13325
"""

from __future__ import annotations

from typing import Any, ClassVar, FrozenSet, Iterable, Tuple

# Masked stand-in for a populated credential value.  Fixed width so the mask
# never discloses the length of the real secret.
REDACTED_PLACEHOLDER = "**********"

# A field is credential-shaped when its name equals one of these nouns or ends
# with ``_<noun>``.  Suffix matching avoids false positives on names that merely
# contain the noun (``tokenizers_parallelism``, ``llm_key_rotation_grace_secs``).
CREDENTIAL_SUFFIXES: Tuple[str, ...] = (
    "secret",
    "key",
    "token",
    "password",
    "passwd",
    "pass",
    "passphrase",
    "credential",
    "credentials",
    "salt",
    "dsn",
    "signature",
)

# Names ending in these are locations or identifiers pointing *at* a credential,
# not the credential itself.  ``tls_key_path`` and ``service_key_file`` must stay
# visible so an operator can tell which file was loaded.
LOCATION_SUFFIXES: Tuple[str, ...] = ("_path", "_file", "_dir", "_url", "_id")


def is_credential_field(name: str) -> bool:
    """Return True when a field name denotes a credential *value*."""
    if not name:
        return False
    lowered = name.lower()
    if lowered.endswith(LOCATION_SUFFIXES):
        return False
    return any(lowered == suffix or lowered.endswith(f"_{suffix}") for suffix in CREDENTIAL_SUFFIXES)


def redact_value(name: str, value: Any) -> Any:
    """Mask ``value`` when ``name`` is credential-shaped and the value is set."""
    if not is_credential_field(name):
        return value
    if value is None or value == "":
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
        exempt = getattr(self, "NON_CREDENTIAL_FIELDS", frozenset())
        for name, value in super().__repr_args__():  # type: ignore[misc]
            if not name or name in exempt:
                yield name, value
            else:
                yield name, redact_value(name, value)
