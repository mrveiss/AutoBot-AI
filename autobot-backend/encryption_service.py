#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

from autobot_shared.logging_manager import get_logger
from autobot_shared.passphrase_encryption import PassphraseEncryptionService, make_data_codec
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import config

logger = get_logger(__name__)


class EncryptionService(PassphraseEncryptionService):
    """Data-at-rest encryption keyed from the AutoBot SSOT configuration (#18449)."""

    KEY_ENV_HINT = "AUTOBOT_ENCRYPTION_KEY"

    def _load_master_key(self) -> str | None:
        """Load master key from the SSOT config (AUTOBOT_ENCRYPTION_KEY, then MASTER_KEY)."""
        # (#13162: the old two-step form re-tested config.encryption_key
        # inside its own `if not key` branch — same result, twice the read.)
        key = config.encryption_key or config.master_key

        if not key:
            logger.error("No encryption key found in environment variables. " "Please set AUTOBOT_ENCRYPTION_KEY.")
            return None

        return key


get_encryption_service = lazy_singleton(EncryptionService)


def is_encryption_enabled() -> bool:
    """
    Check if encryption is enabled via configuration.

    Returns:
        True if encryption should be used
    """
    return bool(config.misc.encryption_key)


# Convenience functions, bound to this service's singleton.
encrypt_data, decrypt_data = make_data_codec(lambda: get_encryption_service())
