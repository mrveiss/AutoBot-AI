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

from sqlalchemy import Column, DateTime, String
from sqlalchemy.types import Uuid

from autobot_shared.time_utils import now_utc
from user_management.models.base import Base


class DevicePlatform(str, Enum):
    IOS = "ios"
    ANDROID = "android"
    PWA = "pwa"


class MobileDevice(Base):
    """Paired mobile device registered via QR-code pairing flow (GH#4463)."""

    __tablename__ = "desktop_mobile_devices"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(64), nullable=False, index=True)
    device_name = Column(String(255), nullable=False)
    # Opaque push token from APNs / FCM / web-push
    device_token = Column(String(512), nullable=False)
    platform = Column(String(16), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)

    def __repr__(self) -> str:
        return f"<MobileDevice id={self.id} user={self.user_id} platform={self.platform}>"
