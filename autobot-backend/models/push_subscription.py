# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""PushSubscription SQLAlchemy model for web push delivery (GH#4459)."""

import uuid

from sqlalchemy import Column, String, Text

from user_management.models.base import Base


class PushSubscription(Base):
    """One browser push subscription endpoint per (user_id, endpoint) pair."""

    __tablename__ = "push_subscriptions"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    endpoint = Column(Text(), nullable=False, unique=True)
    p256dh = Column(Text(), nullable=False)
    auth = Column(Text(), nullable=False)
    # created_at / updated_at are injected by Base via mapped_column — do not redeclare

    def __repr__(self) -> str:
        return f"<PushSubscription user_id={self.user_id!r} endpoint={self.endpoint[:40]!r}...>"
