# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Session Service

Manages user sessions and JWT token invalidation via Redis blacklist.
Issue #635.
"""

import hashlib
import logging

logger = logging.getLogger(__name__)


class SessionService:
    """Manages user sessions and JWT token invalidation."""

    @staticmethod
    def hash_token(token: str) -> str:
        """
        Hash JWT token using SHA256.

        Args:
            token: JWT token string

        Returns:
            Hex string of SHA256 hash
        """
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
