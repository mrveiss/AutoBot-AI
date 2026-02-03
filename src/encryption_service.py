#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Data-at-Rest Encryption Service for AutoBot

This module provides secure encryption and decryption of sensitive data
including chat history, knowledge base content, and user-generated content.

Security Features:
- AES-GCM authenticated encryption
- Secure key derivation using PBKDF2
- Salt-based key generation for each encryption
- Environment variable-based key management
"""

import base64
import hashlib
import logging
import os
import secrets
from typing import Optional, Union

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


logger = logging.getLogger(__name__)


class EncryptionService:
    """
    Secure encryption service for data-at-rest protection.

    Uses AES-GCM authenticated encryption with PBKDF2 key derivation.
    """

    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize the encryption service.

        Args:
            master_key: Optional master key. If not provided, will load from
                environment.
        """
        self.master_key = master_key or self._load_master_key()
        if not self.master_key:
            raise ValueError(
                "No encryption key provided. Set AUTOBOT_ENCRYPTION_KEY "
                "environment variable."
            )

        # Validate key strength
        if len(self.master_key) < 32:
            logger.warning(
                "Encryption key is shorter than recommended 32 characters. "
                "Consider using a stronger key for better security."
            )

    def _load_master_key(self) -> Optional[str]:
        """Load master key from environment variables."""
        key = os.getenv("AUTOBOT_ENCRYPTION_KEY")
        if not key:
            # Try alternative environment variable names
            key = os.getenv("ENCRYPTION_KEY") or os.getenv("MASTER_KEY")

        if not key:
            logger.error(
                "No encryption key found in environment variables. "
                "Please set AUTOBOT_ENCRYPTION_KEY."
            )
            return None

        return key

    def _derive_key(self, salt: bytes) -> bytes:
        """
        Derive encryption key from master key using PBKDF2.

        Args:
            salt: Salt bytes for key derivation

        Returns:
            32-byte derived key
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # AES-256 key length
            salt=salt,
            iterations=100000,  # NIST recommended minimum
        )
        return kdf.derive(self.master_key.encode("utf-8"))

    def encrypt(self, plaintext: Union[str, bytes]) -> str:
        """
        Encrypt data using AES-GCM authenticated encryption.

        Args:
            plaintext: Data to encrypt (string or bytes)

        Returns:
            Base64-encoded encrypted data with metadata

        Raises:
            ValueError: If encryption fails
        """
        try:
            # Convert string to bytes if needed
            if isinstance(plaintext, str):
                plaintext_bytes = plaintext.encode("utf-8")
            else:
                plaintext_bytes = plaintext

            # Generate random salt and nonce
            salt = secrets.token_bytes(16)  # 128-bit salt
            nonce = secrets.token_bytes(12)  # 96-bit nonce for GCM

            # Derive encryption key
            key = self._derive_key(salt)

            # Encrypt with AES-GCM
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)

            # Combine salt + nonce + ciphertext
            encrypted_data = salt + nonce + ciphertext

            # Return base64-encoded result
            return base64.b64encode(encrypted_data).decode("ascii")

        except Exception as e:
            logger.error("Encryption failed: %s", e)
            raise ValueError(f"Encryption failed: {e}")

    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt data using AES-GCM authenticated decryption.

        Args:
            encrypted_data: Base64-encoded encrypted data

        Returns:
            Decrypted plaintext as string

        Raises:
            ValueError: If decryption fails or data is invalid
        """
        try:
            # Decode from base64
            data = base64.b64decode(encrypted_data.encode("ascii"))

            # Extract components (salt: 16 bytes, nonce: 12 bytes, rest: ciphertext)
            if len(data) < 28:  # Minimum: 16 (salt) + 12 (nonce)
                raise ValueError("Invalid encrypted data: too short")

            salt = data[:16]
            nonce = data[16:28]
            ciphertext = data[28:]

            # Derive decryption key
            key = self._derive_key(salt)

            # Decrypt with AES-GCM
            aesgcm = AESGCM(key)
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)

            # Return as string
            return plaintext_bytes.decode("utf-8")

        except Exception as e:
            logger.error("Decryption failed: %s", e)
            raise ValueError(f"Decryption failed: {e}")

    def encrypt_json(self, data: dict) -> str:
        """
        Encrypt JSON data.

        Args:
            data: Dictionary to encrypt

        Returns:
            Base64-encoded encrypted JSON
        """
        import json

        json_str = json.dumps(data, separators=(",", ":"))  # Compact JSON
        return self.encrypt(json_str)

    def decrypt_json(self, encrypted_data: str) -> dict:
        """
        Decrypt JSON data.

        Args:
            encrypted_data: Base64-encoded encrypted JSON

        Returns:
            Decrypted dictionary
        """
        import json

        json_str = self.decrypt(encrypted_data)
        return json.loads(json_str)

    def is_encrypted(self, data: str) -> bool:
        """
        Check if data appears to be encrypted by this service.

        Args:
            data: Data to check

        Returns:
            True if data looks like encrypted content
        """
        try:
            # Try to decode as base64
            decoded = base64.b64decode(data.encode("ascii"))
            # Check minimum length for salt + nonce
            return len(decoded) >= 28
        except Exception:
            return False

    def generate_key(self, length: int = 64) -> str:
        """
        Generate a secure random key for use as master key.

        Args:
            length: Key length in characters (default: 64)

        Returns:
            Cryptographically secure random key
        """
        return secrets.token_urlsafe(length)

    def get_key_info(self) -> dict:
        """
        Get information about the current encryption configuration.

        Returns:
            Dictionary with key information (no sensitive data)
        """
        key_hash = hashlib.sha256(self.master_key.encode()).hexdigest()[:16]
        return {
            "algorithm": "AES-256-GCM",
            "key_derivation": "PBKDF2-SHA256",
            "iterations": 100000,
            "key_length": len(self.master_key),
            "key_hash_prefix": key_hash,  # First 16 chars for identification
        }


# Global encryption service instance (thread-safe)
import threading

_encryption_service: Optional[EncryptionService] = None
_encryption_service_lock = threading.Lock()


def get_encryption_service() -> EncryptionService:
    """
    Get the global encryption service instance (thread-safe).

    Returns:
        EncryptionService instance

    Raises:
        ValueError: If encryption service cannot be initialized
    """
    global _encryption_service
    if _encryption_service is None:
        with _encryption_service_lock:
            # Double-check after acquiring lock
            if _encryption_service is None:
                _encryption_service = EncryptionService()
    return _encryption_service


def is_encryption_enabled() -> bool:
    """
    Check if encryption is enabled via configuration.

    Returns:
        True if encryption should be used
    """
    from src.config import config as global_config_manager

    return global_config_manager.get_nested("security.enable_encryption", False)


# Convenience functions
def encrypt_data(data: Union[str, bytes, dict]) -> str:
    """Encrypt data using the global encryption service."""
    service = get_encryption_service()
    if isinstance(data, dict):
        return service.encrypt_json(data)
    else:
        return service.encrypt(data)


def decrypt_data(encrypted_data: str, as_json: bool = False) -> Union[str, dict]:
    """Decrypt data using the global encryption service."""
    service = get_encryption_service()
    if as_json:
        return service.decrypt_json(encrypted_data)
    else:
        return service.decrypt(encrypted_data)
