# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Credential *references* carried by a role (#14221 step 4).

Owner framing:

    people get promoted or leave the company, but the role stays — and so do
    the tools and workflows attached to the role

Before this, a secret was keyed to the agent that created it
(``LLCSecret.created_by_agent_id``), so terminating that agent left the secret
referencing nobody active and the next holder of the same role starting from
nothing. The reference belongs to the **role**, which outlives its occupants.

**A reference, never a value.** This table stores ``secret_id`` only. The
plaintext stays behind ``SecretService``, which owns decryption, revocation and
the audit trail. Copying a secret's value into a second table would create a
parallel credential path with no revocation story — the defect shape recorded in
#10088 and #13643.

Revocation is honoured at **read** time, not just at attach time. A secret
revoked after being attached must stop resolving through the role immediately;
see ``RoleCredentialService.list_active_for_role``. Filtering only at attach
would let a revoked credential stay reachable for as long as the row survived,
which is precisely what revocation is supposed to prevent.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCRoleCredential(Base):
    """One secret made available to the holders of one role."""

    __tablename__ = "llc_role_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Carried on the attachment so every query pins scope without depending on
    # a join — a lost join condition cannot widen the result. UUID here, matching
    # llc_roles/organizations; llc_secrets.company_id is String(255) and the one
    # coercion that bridges them is confined to the service (#14312).
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    secret_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    __table_args__ = (sa.UniqueConstraint("role_id", "secret_id", name="uq_llc_role_credentials_role_secret"),)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<LLCRoleCredential role={self.role_id} secret={self.secret_id}>"
