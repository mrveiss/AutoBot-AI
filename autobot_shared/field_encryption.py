# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Field-level encryption for single stored credentials: a facade over ``secrets_envelope`` (#17981).

Every value is sealed with the vault's AEAD core under a key derived from
``AUTOBOT_SECRETS_ROOT_KEY``, and bound to *context*: a stable name for where
the value is stored, such as ``organization:<id>:pm_config``. A sealed value
copied to another record or field does not open.

Values written before #17981 carry no binding and were sealed with
``AUTOBOT_FIELD_ENCRYPTION_KEY``. They stay readable while that key is set, and
are sealed in the new format the next time the product itself saves them. No
code re-seals stored credentials on its own (#17038).

Any read failure raises :class:`FieldDecryptionError` naming the context. It
never returns an empty value that a caller could save back over the credential.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os

from autobot_shared.secrets_envelope import (
    FIELD_FORMAT_PREFIX,
    DecryptionError,
    UnsupportedFormatError,
    open_field,
    open_unbound_legacy,
    seal_field,
)

logger = logging.getLogger(__name__)

_LEGACY_KEY_ENV = "AUTOBOT_FIELD_ENCRYPTION_KEY"


class FieldDecryptionError(Exception):
    """A stored credential could not be read; the message names its context, never its value."""


def _legacy_key(context: str) -> bytes:
    raw = os.environ.get(_LEGACY_KEY_ENV, "")
    if not raw:
        raise FieldDecryptionError(f"{context}: stored in the pre-#17981 format, and {_LEGACY_KEY_ENV} is not set")
    key = base64.urlsafe_b64decode(raw + "==")
    if len(key) != 32:
        raise FieldDecryptionError(f"{context}: {_LEGACY_KEY_ENV} must be 32 bytes (got {len(key)})")
    return key


def encrypt_field(plaintext: str, *, context: str) -> str:
    """Seal *plaintext*, bound to *context*. Raises if the root key is unusable."""
    return seal_field(plaintext.encode("utf-8"), context=context)


def decrypt_field(ciphertext: str, *, context: str) -> str:
    """Open a value sealed for *context*, in either format. Fails closed with :class:`FieldDecryptionError`."""
    try:
        if ciphertext.startswith(FIELD_FORMAT_PREFIX):
            return open_field(ciphertext, context=context).decode("utf-8")
        raw = base64.urlsafe_b64decode(ciphertext + "==")
        return open_unbound_legacy(_legacy_key(context), raw).decode("utf-8")
    except FieldDecryptionError:
        raise
    except (DecryptionError, UnsupportedFormatError, binascii.Error, ValueError, RuntimeError) as exc:
        raise FieldDecryptionError(f"{context}: stored value cannot be decrypted ({type(exc).__name__})") from exc


def is_legacy_ciphertext(ciphertext: str) -> bool:
    """True for a value sealed before #17981 (no binding); the next save writes the new format."""
    return not ciphertext.startswith(FIELD_FORMAT_PREFIX)


# Sentinel prefix that distinguishes an encrypted value from a plaintext one.
# Allows backward-compatible reads: if a stored value lacks the prefix it was
# written before encryption was enabled and is returned as-is.
_ENCRYPTED_PREFIX = "enc:"


def seal_tagged(plaintext: str, *, context: str) -> str:
    """Seal for a store that also holds plaintext: the result carries the ``enc:`` tag."""
    return _ENCRYPTED_PREFIX + encrypt_field(plaintext, context=context)


def is_plaintext(stored: str) -> bool:
    """True for a value in a tagged store that was written before encryption (no ``enc:`` tag)."""
    return not stored.startswith(_ENCRYPTED_PREFIX)


def open_tagged(stored: str, *, context: str) -> str:
    """Read a value written by :func:`seal_tagged`. An untagged (pre-encryption) value is returned as-is.

    A tagged value that cannot be decrypted raises :class:`FieldDecryptionError`.
    """
    if is_plaintext(stored):
        return stored
    return decrypt_field(stored[len(_ENCRYPTED_PREFIX) :], context=context)


# Fields within sso_providers.config that hold credentials and must be
# encrypted at rest.
SSO_SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {
        "client_secret",
        "private_key",
        "private_key_pem",
        "bind_password",
        "service_account_key",
    }
)


def _sso_context(provider_id: str, field: str) -> str:
    return f"sso_provider:{provider_id}:{field}"


def encrypt_sso_config(config: dict, *, provider_id: str) -> dict:
    """Return a copy of *config* with all sensitive fields encrypted.

    Non-sensitive fields are copied verbatim. Already-encrypted values
    (prefixed with ``enc:``) are left unchanged so the function is idempotent.
    """
    out = dict(config)
    for field in SSO_SENSITIVE_FIELDS:
        value = out.get(field)
        if value and isinstance(value, str) and not value.startswith(_ENCRYPTED_PREFIX):
            out[field] = seal_tagged(value, context=_sso_context(provider_id, field))
    return out


def decrypt_sso_config(config: dict, *, provider_id: str) -> dict:
    """Return a copy of *config* with all encrypted sensitive fields decrypted.

    Values that do not carry the ``enc:`` prefix are assumed plaintext (written
    before encryption was rolled out) and are returned unchanged.
    """
    out = dict(config)
    for field in SSO_SENSITIVE_FIELDS:
        value = out.get(field)
        if value and isinstance(value, str):
            out[field] = open_tagged(value, context=_sso_context(provider_id, field))
    return out


def is_sso_config_encrypted(config: dict) -> bool:
    """Return True if at least one sensitive field in *config* is encrypted."""
    for field in SSO_SENSITIVE_FIELDS:
        value = config.get(field)
        if value and isinstance(value, str) and value.startswith(_ENCRYPTED_PREFIX):
            return True
    return False
