# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Mobile Device Model (GH#4463)

SQLAlchemy model for paired mobile devices used in push notification
delivery and offline conversation sync.
"""

import uuid
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.types import Uuid

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from user_management.models.base import Base

logger = get_logger(__name__)


class DevicePlatform(str, Enum):
    IOS = "ios"
    ANDROID = "android"
    PWA = "pwa"


class MobileDevice(Base):
    """Paired mobile device registered via QR-code pairing flow (GH#4463).

    Device tokens are encrypted at rest using AES-256-GCM.
    """

    __tablename__ = "desktop_mobile_devices"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(64), nullable=False, index=True)
    device_name = Column(String(255), nullable=False)
    # Encrypted push token from APNs / FCM / web-push (base64-encoded ciphertext)
    _device_token_encrypted = Column("device_token", Text, nullable=False)
    platform = Column(String(16), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)

    def __repr__(self) -> str:
        return (
            f"<MobileDevice id={self.id} user={self.user_id} platform={self.platform}>"
        )

    @property
    def device_token(self) -> str:
        """Get decrypted device token."""
        try:
            from encryption_service import decrypt_data

            return decrypt_data(self._device_token_encrypted)
        except Exception:
            logger.exception("Failed to decrypt device token for device %s", self.id)
            raise

    @device_token.setter
    def device_token(self, plaintext_token: str) -> None:
        """Set device token (will be encrypted before storage)."""
        try:
            from encryption_service import encrypt_data

            self._device_token_encrypted = encrypt_data(plaintext_token)
        except Exception:
            logger.exception("Failed to encrypt device token for device %s", self.id)
            raise
