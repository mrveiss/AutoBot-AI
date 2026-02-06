# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat History Security Mixin - Encryption and decryption operations.

Provides secure data handling for chat history with:
- Data encryption before storage
- Data decryption on retrieval
- Fallback handling for legacy unencrypted data
"""

import json
import logging
from typing import Any, Dict

from src.encryption_service import decrypt_data, encrypt_data, get_encryption_service

logger = logging.getLogger(__name__)


class SecurityMixin:
    """
    Mixin providing encryption/decryption for chat data.

    Requires base class to have:
    - self.encryption_enabled: bool
    """

    def _encrypt_data(self, data: Dict[str, Any]) -> str:
        """
        Encrypt chat data if encryption is enabled.

        Args:
            data: Dictionary to encrypt

        Returns:
            Encrypted string or JSON string if encryption disabled/failed
        """
        if not self.encryption_enabled:
            return json.dumps(data, indent=2, ensure_ascii=False)

        try:
            return encrypt_data(data)
        except Exception as e:
            logger.error("Failed to encrypt chat data: %s", e)
            logger.warning(
                "Falling back to unencrypted storage due to encryption failure"
            )
            return json.dumps(data, indent=2, ensure_ascii=False)

    def _decrypt_data(self, data_str: str) -> Dict[str, Any]:
        """
        Decrypt chat data if it's encrypted.

        Args:
            data_str: Encrypted or JSON string

        Returns:
            Decrypted dictionary

        Raises:
            ValueError: If data cannot be decoded
        """
        if not self.encryption_enabled:
            return json.loads(data_str)

        try:
            # Check if data is encrypted (base64-like format)
            encryption_service = get_encryption_service()
            if encryption_service.is_encrypted(data_str):
                return decrypt_data(data_str, as_json=True)
            else:
                # Legacy unencrypted data
                logger.debug("Loading legacy unencrypted chat data")
                return json.loads(data_str)
        except Exception as e:
            logger.error("Failed to decrypt chat data: %s", e)
            # Try as unencrypted JSON as fallback
            try:
                return json.loads(data_str)
            except json.JSONDecodeError:
                logger.error("Data is neither valid encrypted nor JSON format")
                raise ValueError(
                    "Cannot decode chat data - corrupted or invalid format"
                )
