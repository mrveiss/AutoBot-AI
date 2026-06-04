"""LLC activity log SQLAlchemy model (GH#8216).

Immutable audit trail for all LLC mutations. This table is append-only:
no UPDATE or DELETE operations are ever performed on it at the service layer.
"""

import uuid
from datetime import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class LLCBase(DeclarativeBase):
    """Separate declarative base for LLC models.

    Intentionally does NOT include created_at/updated_at from
    user_management.models.base.Base — LLC's activity log uses occurred_at
    and must never have an updated_at column (append-only constraint).
    """

    type_annotation_map = {uuid.UUID: UUID(as_uuid=True)}


class ActorType(str, Enum):
    """Who triggered the action recorded in an activity log row."""

    AGENT = "agent"
    USER = "user"
    SYSTEM = "system"


class LLCActivityLog(LLCBase):
    """Immutable record of every state-changing LLC operation.

    Rules enforced at the service layer (LLCActivityLogService):
    - Rows are only ever inserted, never updated or deleted.
    - after_state is always populated; before_state is nullable.
    - actor_agent_id XOR actor_user_id is set; both null only for system events.
    """

    __tablename__ = "llc_activity_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_type: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
    )
    actor_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    entity_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(sa.Text, nullable=False)
    before_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    log_metadata: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    __table_args__ = (
        sa.Index("ix_llc_activity_log_company_id", "company_id"),
        sa.Index(
            "ix_llc_activity_log_entity",
            "company_id",
            "entity_type",
            "entity_id",
        ),
        sa.Index(
            "ix_llc_activity_log_occurred_at",
            "company_id",
            "occurred_at",
        ),
        sa.Index("ix_llc_activity_log_action", "company_id", "action"),
        sa.Index("ix_llc_activity_log_actor_agent", "actor_agent_id"),
        sa.Index("ix_llc_activity_log_actor_user", "actor_user_id"),
    )


__all__ = ["ActorType", "LLCActivityLog", "LLCBase"]
