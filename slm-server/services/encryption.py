# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Server Encryption Service

Provides secure encryption and decryption of sensitive data
using AES-GCM authenticated encryption with PBKDF2 key derivation.
"""

import base64
import hashlib
import logging
import os
import secrets
import threading
from typing import Optional, Union

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class EncryptionService:
    """Secure encryption service for data-at-rest protection."""

    # Key derivation iterations (NIST recommended minimum)
    PBKDF2_ITERATIONS = 100000
    SALT_LENGTH = 16
    NONCE_LENGTH = 12
    KEY_LENGTH = 32  # AES-256

    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize the encryption service.

        Args:
            master_key: Optional master key. If not provided, loads from env.
        """
        self.master_key = master_key or self._load_master_key()
        if not self.master_key:
            raise ValueError(
                "No encryption key provided. Set SLM_ENCRYPTION_KEY "
                "environment variable."
            )

        if len(self.master_key) < 32:
            logger.warning(
                "Encryption key shorter than recommended 32 characters. "
                "Consider using a stronger key."
            )

    def _load_master_key(self) -> Optional[str]:
        """Load master key from environment variables."""
        # Try SLM-specific key first, then fall back to secret_key
        key = os.getenv("SLM_ENCRYPTION_KEY")
        if not key:
            key = os.getenv("SLM_SECRET_KEY")

        if not key:
            logger.error(
                "No encryption key found. Set SLM_ENCRYPTION_KEY environment variable."
            )
            return None

        return key

    def _derive_key(self, salt: bytes) -> bytes:
        """Derive encryption key from master key using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_LENGTH,
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
        )
        return kdf.derive(self.master_key.encode("utf-8"))

    def encrypt(self, plaintext: Union[str, bytes]) -> str:
        """
        Encrypt data using AES-GCM authenticated encryption.

        Args:
            plaintext: Data to encrypt (string or bytes)

        Returns:
            Base64-encoded encrypted data with metadata
        """
        try:
            if isinstance(plaintext, str):
                plaintext_bytes = plaintext.encode("utf-8")
            else:
                plaintext_bytes = plaintext

            salt = secrets.token_bytes(self.SALT_LENGTH)
            nonce = secrets.token_bytes(self.NONCE_LENGTH)

            key = self._derive_key(salt)
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)

            encrypted_data = salt + nonce + ciphertext
            return base64.b64encode(encrypted_data).decode("ascii")

        except Exception as e:
            logger.error("Encryption failed: %s", e)
            raise ValueError(f"Encryption failed: {e}") from e

    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt data using AES-GCM authenticated decryption.

        Args:
            encrypted_data: Base64-encoded encrypted data

        Returns:
            Decrypted plaintext as string
        """
        try:
            data = base64.b64decode(encrypted_data.encode("ascii"))

            min_length = self.SALT_LENGTH + self.NONCE_LENGTH
            if len(data) < min_length:
                raise ValueError("Invalid encrypted data: too short")

            salt = data[: self.SALT_LENGTH]
            nonce = data[self.SALT_LENGTH : self.SALT_LENGTH + self.NONCE_LENGTH]
            ciphertext = data[self.SALT_LENGTH + self.NONCE_LENGTH :]

            key = self._derive_key(salt)
            aesgcm = AESGCM(key)
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)

            return plaintext_bytes.decode("utf-8")

        except Exception as e:
            logger.error("Decryption failed: %s", e)
            raise ValueError(f"Decryption failed: {e}") from e

    def encrypt_json(self, data: dict) -> str:
        """Encrypt dictionary as JSON."""
        import json

        json_str = json.dumps(data, separators=(",", ":"))
        return self.encrypt(json_str)

    def decrypt_json(self, encrypted_data: str) -> dict:
        """Decrypt JSON data to dictionary."""
        import json

        json_str = self.decrypt(encrypted_data)
        return json.loads(json_str)

    def is_encrypted(self, data: str) -> bool:
        """Check if data appears to be encrypted by this service."""
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
        """Get information about current encryption configuration."""
        key_hash = hashlib.sha256(self.master_key.encode()).hexdigest()[:16]
        return {
            "algorithm": "AES-256-GCM",
            "key_derivation": "PBKDF2-SHA256",
            "iterations": self.PBKDF2_ITERATIONS,
            "key_length": len(self.master_key),
            "key_hash_prefix": key_hash,
        }


# Thread-safe singleton
_encryption_service: Optional[EncryptionService] = None
_encryption_service_lock = threading.Lock()


def get_encryption_service() -> EncryptionService:
    """Get the global encryption service instance (thread-safe)."""
    global _encryption_service
    if _encryption_service is None:
        with _encryption_service_lock:
            if _encryption_service is None:
                _encryption_service = EncryptionService()
    return _encryption_service


def encrypt_data(data: Union[str, bytes, dict]) -> str:
    """Encrypt data using the global encryption service."""
    service = get_encryption_service()
    if isinstance(data, dict):
        return service.encrypt_json(data)
    return service.encrypt(data)


def decrypt_data(encrypted_data: str, as_json: bool = False) -> Union[str, dict]:
    """Decrypt data using the global encryption service."""
    service = get_encryption_service()
    if as_json:
        return service.decrypt_json(encrypted_data)
    return service.decrypt(encrypted_data)
