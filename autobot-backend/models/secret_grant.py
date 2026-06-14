# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-grantee wrapped-DEK grants for the unified envelope secrets store.

Task 2.1 of umbrella #10088. A secret's value is sealed once under a per-secret
DEK (stored on ``secrets.sealed_value``); the DEK is then **wrapped** for each
grantee vault and each wrap is one row here. Sharing a secret = adding a row;
revoking a share = deleting one; the owner's own access is just the row whose
``grantee == secrets.owner_vault`` (so the read path is uniform).

``grantee`` is a :func:`autobot_shared.secrets_vault.VaultRef.to_str` string and
matches ``WrappedDek.grantee``; ``wrapped_dek`` is ``WrappedDek.to_dict()``.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from user_management.models.base import Base


class SecretGrant(Base):
    """One wrapped DEK granting a vault access to a secret (1:N with ``secrets``)."""

    __tablename__ = "secret_grants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    secret_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("secrets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    grantee: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        index=True,
        comment="VaultRef.to_str() of the grantee vault; matches WrappedDek.grantee",
    )

    wrapped_dek: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="WrappedDek.to_dict() — the secret's DEK wrapped under this grantee's vault KEK",
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        comment="Acting principal (user_id) who created this grant",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # One wrapped DEK per (secret, grantee vault); re-share rewraps in place.
        UniqueConstraint("secret_id", "grantee", name="uq_secret_grants_secret_grantee"),
    )

    def __repr__(self) -> str:
        return f"<SecretGrant(secret_id={self.secret_id}, grantee={self.grantee!r})>"
