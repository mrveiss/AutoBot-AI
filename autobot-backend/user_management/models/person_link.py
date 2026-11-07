# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One SLM person to one main-app user (#10200, decision on #10193).

Both stores keep their own ids, so memberships and reviewers are not rewritten. The SLM's user
lives in another database, so ``slm_user_id`` cannot be a foreign key.
"""

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base, TimestampMixin


class PersonLink(Base, TimestampMixin):
    __tablename__ = "person_links"
    __table_args__ = (
        UniqueConstraint("slm_user_id", name="uq_person_links_slm_user"),
        UniqueConstraint("user_id", name="uq_person_links_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slm_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Kept when the user is deleted, with no user: otherwise the next start links this person again,
    # bringing back an admin someone removed.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
