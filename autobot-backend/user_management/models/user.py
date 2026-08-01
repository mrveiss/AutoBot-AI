# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
User Model

Core user model with authentication, profile, and tenant association.

Everything this model shares with SLM now lives in
``autobot_shared.user_management.models.user.UserCore`` (#12647) — one
declaration, one place to fix a bug. What stays here is what is genuinely
backend-only: the activity-tracking relationships (#871), whose target models
(``models.activities``) exist in ``autobot-backend`` alone. Declaring them on
the shared core would break ``configure_mappers()`` on the SLM side, where
those classes are not in the registry.

The concrete class stays in this module (rather than being re-exported from
``autobot_shared``) because the two backends need *different* concrete
mappings of the same table, and because every existing
``from user_management.models.user import User`` importer keeps working
unchanged.
"""

from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, relationship

from autobot_shared.user_management.models.user import UserCore

if TYPE_CHECKING:
    from models.activities import (
        BrowserActivityModel,
        DesktopActivityModel,
        FileActivityModel,
        SecretUsageModel,
        TerminalActivityModel,
    )

# Runtime imports for SQLAlchemy relationships (avoid circular imports)
try:
    from models.activities import (  # noqa: F401, F811
        BrowserActivityModel,
        DesktopActivityModel,
        FileActivityModel,
        SecretUsageModel,
        TerminalActivityModel,
    )
except ImportError:
    pass


class User(UserCore):
    """Backend's concrete ``users`` mapping.

    All shared columns, relationships and helpers come from ``UserCore`` — see
    ``autobot_shared/user_management/models/user.py`` for their documentation.
    """

    __tablename__ = "users"

    # Activity tracking relationships (Issue #871) — backend-only
    terminal_activities: Mapped[list["TerminalActivityModel"]] = relationship(
        "TerminalActivityModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    file_activities: Mapped[list["FileActivityModel"]] = relationship(
        "FileActivityModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    browser_activities: Mapped[list["BrowserActivityModel"]] = relationship(
        "BrowserActivityModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    desktop_activities: Mapped[list["DesktopActivityModel"]] = relationship(
        "DesktopActivityModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    secret_usage: Mapped[list["SecretUsageModel"]] = relationship(
        "SecretUsageModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )
