# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Mobile Device Model (GH#4463, #14964)

SQLAlchemy model for paired mobile devices. Originally a push-notification and
offline-sync credential; #14964 extended the same record with the capability
scoping the remote-control surface needs.

Extending this record rather than introducing a second control-credential
table was a deliberate choice (#14964 asked for the decision to be recorded).
The pairing act, the device identity, the encrypted token and the revocation
event are one fact about one physical device: splitting them across two tables
would mean two revocation paths, two ``last_seen_at`` clocks and two rows that
can disagree about whether a device is still trusted. A second table only earns
its place when a device can hold a control credential *without* holding a
pairing, which is not a state this platform has. The columns added here are
additive and default to the denied state, so the record's original consumers
(``push_notifications/mobile_push.py``) are unaffected by them.
"""

import uuid
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.types import Uuid

from autobot_shared.auth.device_capabilities import (
    NO_CAPABILITIES_JSON,
    DeviceCapability,
    capability_granted,
)
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

    # --- #14964 capability scoping -------------------------------------------
    # All three default to the DENIED state, at the model *and* at the database
    # (server_default), so a row inserted by a writer that never heard of these
    # columns is denied rather than granted. The backfill in migration
    # 20260824_084 applies the same values to every pre-existing row.
    #
    # JSON text rather than JSONB: this table is created directly on SQLite by
    # the integration suites (tests/integration/test_mobile_*.py call
    # ``create_all`` on this metadata), and JSONB does not compile there. The
    # grant set is read through ``parse_device_permissions``, which treats any
    # unreadable value as no grants, so text costs nothing in safety.
    permissions = Column(Text, nullable=False, server_default=NO_CAPABILITIES_JSON, default=NO_CAPABILITIES_JSON)
    is_approved = Column(Boolean, nullable=False, server_default="false", default=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    def has_capability(self, capability: "DeviceCapability | str") -> bool:
        """Positive assertion that this device holds ``capability`` (#14964).

        Thin adapter over the canonical predicate so the decision has exactly
        one implementation; see ``autobot_shared.auth.device_capabilities``.
        """
        return capability_granted(
            capability=capability,
            permissions_raw=self.permissions,
            is_approved=self.is_approved,
            revoked_at=self.revoked_at,
        )

    def __repr__(self) -> str:
        return f"<MobileDevice id={self.id} user={self.user_id} platform={self.platform}>"

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
