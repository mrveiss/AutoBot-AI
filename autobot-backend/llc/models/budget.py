# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC per-agent budget model (GH#8215)."""

import uuid
from decimal import Decimal

from sqlalchemy import Float, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCAgentBudget(Base):
    """Per-agent spend tracking with hard-stop and alert threshold.

    budget_limit and budget_spent use Numeric(15,6) — not Float — so that
    decimal arithmetic is exact (Float loses precision at ~7 sig figs).
    """

    __tablename__ = "llc_agent_budgets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    budget_limit: Mapped[Decimal] = mapped_column(Numeric(15, 6), nullable=False)
    budget_spent: Mapped[Decimal] = mapped_column(Numeric(15, 6), nullable=False, default=Decimal("0"))
    alert_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
