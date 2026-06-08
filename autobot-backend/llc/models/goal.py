# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC goal model — 4-level hierarchy (GH#8212).

Table: llc_goals
Self-referential FK: parent_goal_id → llc_goals.id
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from user_management.models.base import Base


class GoalLevel(str, Enum):
    """4-level goal hierarchy."""

    VISION = "vision"
    MISSION = "mission"
    OBJECTIVE = "objective"
    KEY_RESULT = "key_result"


class GoalStatus(str, Enum):
    """Lifecycle status of a goal."""

    DRAFT = "draft"
    ACTIVE = "active"
    ACHIEVED = "achieved"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"


class LLCGoal(Base):
    """4-level goal hierarchy node (GH#8212).

    The root of each tree has parent_goal_id = NULL. Level enforces the
    vision → mission → objective → key_result order; the service validates
    that a child's level is one step below the parent's level.
    """

    __tablename__ = "llc_goals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    parent_goal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("llc_goals.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    level: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=GoalStatus.DRAFT.value, index=True)
    owner_agent_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    children: Mapped[list["LLCGoal"]] = relationship(
        "LLCGoal",
        back_populates="parent",
        foreign_keys=[parent_goal_id],
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    parent: Mapped[Optional["LLCGoal"]] = relationship(
        "LLCGoal",
        back_populates="children",
        foreign_keys=[parent_goal_id],
        remote_side="LLCGoal.id",
    )

    def __repr__(self) -> str:
        return f"<LLCGoal id={self.id!r} level={self.level!r} title={self.title!r}>"
