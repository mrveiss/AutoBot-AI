# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AES-256-GCM field-level encryption for sensitive config blobs (GH#8257).

Environment variable:
    AUTOBOT_FIELD_ENCRYPTION_KEY — 32-byte key as URL-safe base64 (required for
    encrypt/decrypt).  Generate with:
        python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"

Encrypted format (base64url of: 12-byte nonce || ciphertext || 16-byte tag).
"""

from __future__ import annotations

import base64
import logging
import os

logger = logging.getLogger(__name__)

_KEY_ENV = "AUTOBOT_FIELD_ENCRYPTION_KEY"
_NONCE_LEN = 12
_TAG_LEN = 16


def _load_key() -> bytes:
    raw = os.environ.get(_KEY_ENV, "")
    if not raw:
        raise RuntimeError(f"{_KEY_ENV} is not set — cannot encrypt/decrypt sensitive fields")
    key = base64.urlsafe_b64decode(raw + "==")
    if len(key) != 32:
        raise RuntimeError(f"{_KEY_ENV} must be 32 bytes (got {len(key)})")
    return key


def encrypt_field(plaintext: str) -> str:
    """Return a base64url-encoded AES-256-GCM ciphertext for *plaintext*."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _load_key()
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    blob = nonce + ct
    return base64.urlsafe_b64encode(blob).decode("ascii")


def decrypt_field(ciphertext: str) -> str:
    """Decrypt a base64url-encoded AES-256-GCM blob and return the plaintext."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _load_key()
    blob = base64.urlsafe_b64decode(ciphertext + "==")
    if len(blob) < _NONCE_LEN + _TAG_LEN:
        raise ValueError("Encrypted blob is too short")
    nonce = blob[:_NONCE_LEN]
    ct = blob[_NONCE_LEN:]
    plaintext_bytes = AESGCM(key).decrypt(nonce, ct, None)
    return plaintext_bytes.decode("utf-8")


# Sentinel prefix that distinguishes an encrypted value from a plaintext one.
# Allows backward-compatible reads: if a stored value lacks the prefix it was
# written before encryption was enabled and is returned as-is.
_ENCRYPTED_PREFIX = "enc:"

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


def encrypt_sso_config(config: dict) -> dict:
    """Return a copy of *config* with all sensitive fields encrypted.

    Non-sensitive fields are copied verbatim. Already-encrypted values
    (prefixed with ``enc:``) are left unchanged so the function is idempotent.
    """
    out = dict(config)
    for field in SSO_SENSITIVE_FIELDS:
        value = out.get(field)
        if value and isinstance(value, str) and not value.startswith(_ENCRYPTED_PREFIX):
            out[field] = _ENCRYPTED_PREFIX + encrypt_field(value)
    return out


def decrypt_sso_config(config: dict) -> dict:
    """Return a copy of *config* with all encrypted sensitive fields decrypted.

    Values that do not carry the ``enc:`` prefix are assumed plaintext (written
    before encryption was rolled out) and are returned unchanged.
    """
    out = dict(config)
    for field in SSO_SENSITIVE_FIELDS:
        value = out.get(field)
        if value and isinstance(value, str) and value.startswith(_ENCRYPTED_PREFIX):
            out[field] = decrypt_field(value[len(_ENCRYPTED_PREFIX) :])
    return out


def is_sso_config_encrypted(config: dict) -> bool:
    """Return True if at least one sensitive field in *config* is encrypted."""
    for field in SSO_SENSITIVE_FIELDS:
        value = config.get(field)
        if value and isinstance(value, str) and value.startswith(_ENCRYPTED_PREFIX):
            return True
    return False
