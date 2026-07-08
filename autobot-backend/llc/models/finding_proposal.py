# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLCFindingProposal model — analytics finding proposals awaiting promotion (#11271)."""

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base

from .enums import FindingProposalStatus, pg_enum_values


class LLCFindingProposal(Base):
    """A codebase-analytics finding staged for human/agent promotion (#11271).

    Dedup key: (project_id, finding_key).  Status transitions:
      pending → promoted (creates LLCWorkItem)
      pending → dismissed (with dismiss_reason)
    """

    __tablename__ = "llc_finding_proposals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    finding_key: Mapped[str] = mapped_column(String(512), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    line_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verdict_is_real: Mapped[Optional[bool]] = mapped_column(sa.Boolean, nullable=True)
    verdict_confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    verdict_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.Enum(
            FindingProposalStatus,
            name="findingproposalstatus",
            create_type=True,
            values_callable=pg_enum_values,
        ),
        nullable=False,
        server_default=FindingProposalStatus.PENDING.value,
        index=True,
    )
    work_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    dismiss_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    __table_args__ = (UniqueConstraint("project_id", "finding_key", name="uq_finding_proposal_project_key"),)

    def __repr__(self) -> str:
        return f"<LLCFindingProposal id={self.id!r} status={self.status!r} key={self.finding_key!r}>"


__all__ = ["LLCFindingProposal"]
