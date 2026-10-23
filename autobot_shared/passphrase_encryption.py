# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One passphrase-based AES-GCM data-at-rest codec for both services (#18449).

The main backend and the SLM backend each carried a byte-for-byte equivalent
``EncryptionService`` (PBKDF2-SHA256, 100k iterations, ``salt(16) + nonce(12) +
ciphertext``, base64) plus the same ``encrypt_data`` / ``decrypt_data`` helpers.
They differed in exactly one thing: WHERE the master key comes from. That is
now the single abstract hook :meth:`PassphraseEncryptionService._load_master_key`
and the human-readable :attr:`KEY_ENV_HINT`; the wire format has one definition,
so a blob sealed by one service is readable by the other given the same key.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from typing import Callable

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Plain stdlib logging, deliberately -- NOT autobot_shared.logging_manager. The SLM
# backend loads its encryption module in test harnesses that stub `config` as a
# MagicMock, and get_logger() builds a RotatingFileHandler that fails against it at
# logger-CREATION time. Same precedent as autobot_shared/user_management/password_epoch.py.
logger = logging.getLogger(__name__)

_MIN_RECOMMENDED_KEY_CHARS = 32


class PassphraseEncryptionService:
    """AES-256-GCM with a PBKDF2-derived key; subclasses supply the master key."""

    PBKDF2_ITERATIONS = 100000  # NIST recommended minimum
    SALT_LENGTH = 16
    NONCE_LENGTH = 12
    KEY_LENGTH = 32  # AES-256

    #: Named in the "no key" error so an operator knows which variable to set.
    KEY_ENV_HINT = "an encryption key"

    def __init__(self, master_key: str | None = None):
        key = master_key or self._load_master_key()
        if not key:
            raise ValueError(f"No encryption key provided. Set {self.KEY_ENV_HINT} environment variable.")
        self.master_key: str = key
        if len(key) < _MIN_RECOMMENDED_KEY_CHARS:
            logger.warning(
                "Encryption key is shorter than recommended %d characters. "
                "Consider using a stronger key for better security.",
                _MIN_RECOMMENDED_KEY_CHARS,
            )

    def _load_master_key(self) -> str | None:
        """Return the master key from this service's configuration source, or None."""
        raise NotImplementedError

    def _derive_key(self, salt: bytes) -> bytes:
        """Derive the AES key from the master key and *salt* with PBKDF2-SHA256."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_LENGTH,
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
        )
        return kdf.derive(self.master_key.encode("utf-8"))

    def encrypt(self, plaintext: str | bytes) -> str:
        """Encrypt *plaintext*; returns base64 of ``salt + nonce + ciphertext``."""
        try:
            plaintext_bytes = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
            salt = secrets.token_bytes(self.SALT_LENGTH)
            nonce = secrets.token_bytes(self.NONCE_LENGTH)
            ciphertext = AESGCM(self._derive_key(salt)).encrypt(nonce, plaintext_bytes, None)
            return base64.b64encode(salt + nonce + ciphertext).decode("ascii")
        except Exception as e:
            logger.error("Encryption failed: %s", e)
            raise ValueError(f"Encryption failed: {e}") from e

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt a value produced by :meth:`encrypt`; raises ValueError on any failure."""
        try:
            data = base64.b64decode(encrypted_data.encode("ascii"))
            header = self.SALT_LENGTH + self.NONCE_LENGTH
            if len(data) < header:
                raise ValueError("Invalid encrypted data: too short")
            salt = data[: self.SALT_LENGTH]
            nonce = data[self.SALT_LENGTH : header]
            plaintext_bytes = AESGCM(self._derive_key(salt)).decrypt(nonce, data[header:], None)
            return plaintext_bytes.decode("utf-8")
        except Exception as e:
            logger.error("Decryption failed: %s", e)
            raise ValueError(f"Decryption failed: {e}") from e

    def encrypt_json(self, data: dict) -> str:
        """Encrypt a dictionary as compact JSON."""
        return self.encrypt(json.dumps(data, separators=(",", ":")))

    def decrypt_json(self, encrypted_data: str) -> dict:
        """Decrypt a value produced by :meth:`encrypt_json`."""
        return json.loads(self.decrypt(encrypted_data))

    def is_encrypted(self, data: str) -> bool:
        """True if *data* is base64 long enough to hold a salt and nonce."""
        try:
            decoded = base64.b64decode(data.encode("ascii"))
            return len(decoded) >= (self.SALT_LENGTH + self.NONCE_LENGTH)
        except Exception:
            return False

    @staticmethod
    def generate_key(length: int = 64) -> str:
        """Generate a secure random key for use as master key."""
        return secrets.token_urlsafe(length)

    def get_key_info(self) -> dict:
        """Describe the active configuration; contains no key material."""
        key_hash = hashlib.sha256(self.master_key.encode()).hexdigest()[:16]
        return {
            "algorithm": "AES-256-GCM",
            "key_derivation": "PBKDF2-SHA256",
            "iterations": self.PBKDF2_ITERATIONS,
            "key_length": len(self.master_key),
            "key_hash_prefix": key_hash,
        }


def make_data_codec(
    get_service: Callable[[], PassphraseEncryptionService],
) -> tuple[Callable[..., str], Callable[..., str | dict]]:
    """Build the module-level ``(encrypt_data, decrypt_data)`` pair for one service.

    *get_service* is called on every use, never captured, so a test that swaps
    the owning module's ``get_encryption_service`` is honoured.
    """

    def encrypt_data(data: str | bytes | dict) -> str:
        """Encrypt *data* with the global service; a dict goes through the JSON path."""
        service = get_service()
        return service.encrypt_json(data) if isinstance(data, dict) else service.encrypt(data)

    def decrypt_data(encrypted_data: str, as_json: bool = False) -> str | dict:
        """Decrypt *encrypted_data* with the global service, optionally parsing JSON."""
        service = get_service()
        return service.decrypt_json(encrypted_data) if as_json else service.decrypt(encrypted_data)

    return encrypt_data, decrypt_data
