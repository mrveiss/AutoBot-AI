# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC per-agent budget model (GH#8215, GH#8997)."""

import uuid
from decimal import Decimal

from sqlalchemy import BigInteger, Float, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from llc.models.enums import BudgetMode
from user_management.models.base import Base


class LLCAgentBudget(Base):
    """Per-agent spend tracking with hard-stop and alert threshold.

    Supports two budget modes (GH#8997):
    - DOLLARS: track spend in USD using budget_limit/budget_spent (Numeric)
    - TOKENS: track spend in token counts using token_limit/tokens_spent (BigInteger)

    budget_limit and budget_spent use Numeric(15,6) — not Float — so that
    decimal arithmetic is exact (Float loses precision at ~7 sig figs).
    """

    __tablename__ = "llc_agent_budgets"
    __table_args__ = (UniqueConstraint("company_id", "agent_id", name="uq_llc_agent_budgets_company_id_agent_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    #: Per-company slug. NOT globally unique (#15812): global uniqueness made
    #: "is this slug taken?" answerable across the tenant boundary, and the slug
    #: is a company-local name in the first place. Every lookup must therefore
    #: carry company_id — see ``llc/services/budget.py::_for_agent``.
    agent_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    # Budget mode (GH#8997)
    budget_mode: Mapped[str] = mapped_column(String(32), nullable=False, default=BudgetMode.DOLLARS.value)

    # Dollar-based budget (original GH#8215)
    budget_limit: Mapped[Decimal] = mapped_column(Numeric(15, 6), nullable=False)
    budget_spent: Mapped[Decimal] = mapped_column(Numeric(15, 6), nullable=False, default=Decimal("0"))

    # Token-based budget (GH#8997)
    token_limit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tokens_spent: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    alert_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
