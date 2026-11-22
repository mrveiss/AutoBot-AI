# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``audit_chain_anchors``: where the audit hash chain starts (#17219).

One ``genesis`` row, written by the first chained insert (never by the migration, so rows
that old code wrote between the migration and the restart are counted too). It records how
many ``audit_logs`` rows predate the chain: those rows are *pre-chain*, identified by
``chain_seq IS NULL``, never rewritten and never reported as faults. A ``reanchor`` row is
the shape a future approved purge would write (#17038); none is written today.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from autobot_shared.user_management.models.base import Base

GENESIS_KIND = "genesis"
REANCHOR_KIND = "reanchor"


class AuditChainAnchor(Base):
    """A point the chain is verified from: the genesis, or a later re-anchor.

    ``created_at`` / ``updated_at`` come from ``Base``.
    """

    __tablename__ = "audit_chain_anchors"

    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mac: Mapped[str] = mapped_column(String(64), nullable=False)
    key_id: Mapped[str] = mapped_column(String(32), nullable=False)
    pre_chain_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pre_chain_max_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
