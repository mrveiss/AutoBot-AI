# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
MFA (Multi-Factor Authentication) Model

Supports TOTP-based 2FA with backup codes.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user_management.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from user_management.models.user import User


class MFAMethod(str, Enum):
    """MFA methods."""

    TOTP = "totp"
    EMAIL = "email"
    SMS = "sms"  # Future support


class UserMFA(Base, TimestampMixin):
    """
    User MFA configuration.

    Stores encrypted TOTP secret and backup codes.
    One MFA record per user.
    """

    __tablename__ = "user_mfa"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # MFA method
    method: Mapped[str] = mapped_column(
        String(50),
        default=MFAMethod.TOTP.value,
        nullable=False,
    )

    # Encrypted TOTP secret (Fernet encrypted)
    secret_encrypted: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # Encrypted backup codes (JSON array of bcrypt hashes, Fernet encrypted)
    backup_codes_encrypted: Mapped[Optional[str]] = mapped_column(
        String(2000),
        nullable=True,
    )

    # Number of remaining backup codes
    backup_codes_remaining: Mapped[int] = mapped_column(
        default=10,
        nullable=False,
    )

    # Whether MFA setup is complete (verified)
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Last verification timestamp
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Recovery email (for email-based recovery)
    recovery_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="mfa",
    )

    def __repr__(self) -> str:
        return (
            f"<UserMFA(user_id={self.user_id}, "
            f"method={self.method}, verified={self.is_verified})>"
        )

    def record_verification(self) -> None:
        """Record a successful MFA verification."""
        self.last_verified_at = datetime.utcnow()

    def use_backup_code(self) -> None:
        """Record usage of a backup code."""
        self.backup_codes_remaining = max(0, self.backup_codes_remaining - 1)
        self.last_verified_at = datetime.utcnow()
