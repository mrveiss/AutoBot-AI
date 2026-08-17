# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which companies can see a shared contact (#13998).

Owner decision:

    contacts can be shared across companies and projects, we should avoid
    duplication and merge into a single [record]

So an ``LLCContact`` is **one row per human**, and visibility is granted per
company through this link table rather than by copying the person once per
company.

Two properties follow, and both are load-bearing:

* **A company sees only the contacts linked to it.** Shared does not mean
  public: company A must not see a supplier merely because company B uses one.
  That is what reconciles sharing with the access decision on #13992 — "minimal
  necessary access… only when a specific role is required". Sharing removes
  duplication, not the boundary.
* **Unlinking is not deleting.** Removing a contact from one company's view
  deletes that company's link. The contact row — the PII — is removed only when
  no links remain, which keeps #13969's "deletion removes PII" criterion true
  without letting one company's tidying destroy another company's data.

``LLCContact.company_id`` is deliberately left in place for now. Readers are
migrated to the link table first; dropping the column is a follow-up, so no
window exists where a reader depends on a column that has already gone.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCContactCompanyLink(Base):
    """One company's visibility of one shared contact."""

    __tablename__ = "llc_contact_company_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    __table_args__ = (
        # Linking the same contact to the same company twice is a no-op the
        # caller should hear about, not a second row that makes the contact
        # appear duplicated in the very list this table exists to de-duplicate.
        sa.UniqueConstraint("contact_id", "company_id", name="uq_llc_contact_company_links_contact_company"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<LLCContactCompanyLink contact={self.contact_id} company={self.company_id}>"
