# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC company-scoped secret SQLAlchemy model (GH#8217)."""

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCSecret(Base):
    """Versioned, encrypted, company-scoped secret.

    Invariants enforced at the service layer:
    - value is always AES-256 Fernet ciphertext; plaintext never persists.
    - version auto-increments on every set() call that overwrites an existing name.
    - revoked_at is a soft-delete; revoked rows stay but are inaccessible via get().
    - (company_id, name) is unique to prevent duplicate names per tenant.
    """

    __tablename__ = "llc_secrets"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    value: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    created_by_agent_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True, default=None)

    # company_id already declares index=True above (auto-creates
    # ix_llc_secrets_company_id); a second explicit Index of the same name made
    # create_all emit it twice → DuplicateTableError (#10075).
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_llc_secrets_company_name"),)

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


__all__ = ["LLCSecret"]
