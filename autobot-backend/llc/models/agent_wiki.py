# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC AgentWikiEntry model — per-agent knowledge vault (GH#9021).

Each LLC agent has a dedicated knowledge wiki scoped to their role.
Entries are organised by *namespace* (e.g. "procedures", "domain", "glossary")
and identified by a short *key* slug unique within (agent_id, namespace).
The ``body`` column stores freeform Markdown content that is injected as
system context in every heartbeat prompt.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .activity import LLCBase


class LLCAgentWikiEntry(LLCBase):
    """A single wiki page scoped to one LLC agent and one namespace."""

    __tablename__ = "llc_agent_wiki_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    agent_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=sa.text("'general'"),
        index=True,
    )
    key: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa.text("''"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
        onupdate=datetime.utcnow,
    )

    __table_args__ = (sa.UniqueConstraint("agent_id", "namespace", "key", name="uq_agent_wiki_agent_ns_key"),)
