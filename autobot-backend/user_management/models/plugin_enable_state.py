# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Whether an operator has enabled a plugin to run in this process (#17421).

One row per plugin name. A plugin is imported at startup only when its row says enabled, so a
manifest dropped on disk cannot execute code by itself. The row survives restarts: it is the system
of record for the decision, not the in-memory ``BasePlugin.status``.
"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class PluginEnableState(Base):
    __tablename__ = "plugin_enable_state"

    plugin_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # "grandfathered" (loaded before this gate existed) or "admin" (a deliberate operator action).
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(128), nullable=False)
