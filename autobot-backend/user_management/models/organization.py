# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Organization Model

Represents a tenant/organization in the system.
In multi_company and provider modes, each organization is isolated.

Everything this model shares with SLM now lives in
``autobot_shared.user_management.models.organization.OrganizationCore``
(#12647). What stays here is genuinely backend-only: the LLC extension
columns (#8211), external PM sync config (#8257), KB inheritance weight
(#8241) and the per-org LLM/embedding model config helpers (#4451). Folding
those into the shared core would migrate ~12 unused columns into SLM's
``organizations`` table for a feature SLM does not have.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from autobot_shared.user_management.models.organization import OrganizationCore


class Organization(OrganizationCore):
    """Backend's concrete ``organizations`` mapping.

    All shared columns, relationships and helpers come from
    ``OrganizationCore`` — see
    ``autobot_shared/user_management/models/organization.py`` for their
    documentation.
    """

    __tablename__ = "organizations"

    # ------------------------------------------------------------------ #
    # LLC extension columns (GH#8211)                                     #
    # ------------------------------------------------------------------ #

    # Sub-company hierarchy: nullable for root companies
    parent_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Per-company issue numbering (e.g. "ABO", "MVA")
    issue_prefix: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        unique=True,
        index=True,
    )
    issue_counter: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Budget tracking in cents to avoid floating-point precision issues
    budget_monthly_cents: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    spent_monthly_cents: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Branding
    brand_color: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Governance
    require_approval_for_hires: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # LLC lifecycle status — stored as string, validated by LLCCompanyStatus enum
    llc_status: Mapped[str] = mapped_column(
        String(32),
        default="onboarding",
        nullable=False,
    )
    pause_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    paused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ------------------------------------------------------------------ #
    # External PM sync config (GH#8257)                                   #
    # ------------------------------------------------------------------ #

    external_pm_type: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    # AES-256-encrypted JSON blob — never store plaintext credentials
    external_pm_config: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # KB inheritance weight multiplier (GH#8241)
    kb_inheritance_weight: Mapped[float] = mapped_column(
        Float,
        default=0.6,
        nullable=False,
    )

    # Self-referential relationships for sub-company tree
    children: Mapped[list["Organization"]] = relationship(
        "Organization",
        back_populates="parent",
        foreign_keys="Organization.parent_org_id",
        lazy="select",
    )
    parent: Mapped["Organization | None"] = relationship(
        "Organization",
        back_populates="children",
        foreign_keys="Organization.parent_org_id",
        remote_side="Organization.id",
    )

    # ------------------------------------------------------------------
    # Per-org LLM + embedding model config (Issue #4451)
    # ------------------------------------------------------------------

    def get_model_config(self) -> dict:
        """Return the org's persisted LLM/embedding model config.

        Known keys: ``llm_provider``, ``llm_model``, ``embedding_model``,
        ``embedding_dimension``.  Missing keys indicate "use SSOT default".
        """
        return {
            "llm_provider": self.get_setting("llm_provider"),
            "llm_model": self.get_setting("llm_model"),
            "embedding_model": self.get_setting("embedding_model"),
            "embedding_dimension": self.get_setting("embedding_dimension"),
        }

    def set_model_config(self, config: dict) -> None:
        """Persist the org's LLM/embedding model config.

        Only the four well-known keys are accepted.  Passing ``None`` for a
        key clears that field; omitting the key leaves the existing value
        untouched.
        """
        known = {"llm_provider", "llm_model", "embedding_model", "embedding_dimension"}
        for key in known & set(config.keys()):
            self.set_setting(key, config[key])
