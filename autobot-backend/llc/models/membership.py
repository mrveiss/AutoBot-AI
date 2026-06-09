# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC company membership SQLAlchemy model (GH#8223).

Tracks human-user membership in an LLC company with a role.
Used to gate human claim/unclaim of work items — only members may claim.
"""

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base

from .enums import MembershipRole


class LLCCompanyMembership(Base):
    """One row per (company, user) — role defines capabilities within the company."""

    __tablename__ = "llc_company_memberships"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    role: Mapped[str] = mapped_column(
        sa.Enum(MembershipRole, name="membershiprole", create_type=False),
        nullable=False,
        server_default=MembershipRole.MEMBER.value,
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    __table_args__ = (sa.UniqueConstraint("company_id", "user_id", name="uq_llc_membership_company_user"),)
