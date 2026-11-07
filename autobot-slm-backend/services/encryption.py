# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM Server Encryption Service

Provides secure encryption and decryption of sensitive data
using AES-GCM authenticated encryption with PBKDF2 key derivation.
"""

import logging
import os

from autobot_shared.passphrase_encryption import PassphraseEncryptionService, make_data_codec
from autobot_shared.singleton_factory import lazy_singleton

logger = logging.getLogger(__name__)


class SlmEncryptionService(PassphraseEncryptionService):
    """Data-at-rest encryption keyed from the SLM server environment (#18449)."""

    KEY_ENV_HINT = "SLM_ENCRYPTION_KEY"

    def _load_master_key(self) -> str | None:
        """Load master key from SLM_ENCRYPTION_KEY, falling back to SLM_SECRET_KEY."""
        key = os.getenv("SLM_ENCRYPTION_KEY")
        if not key:
            key = os.getenv("SLM_SECRET_KEY")

        if not key:
            logger.error("No encryption key found. Set SLM_ENCRYPTION_KEY environment variable.")
            return None

        return key


get_encryption_service = lazy_singleton(SlmEncryptionService)

# Convenience functions, bound to this service's singleton.
encrypt_data, decrypt_data = make_data_codec(lambda: get_encryption_service())
