# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The connected self-model: one entity table plus its append-only history (#22277).

SQLAlchemy Core, for the reasons ``models/node_capability.py`` states (``models/database.py`` is at its
size ceiling; the SLM test suite stubs it). Nothing here is ever deleted: a removed entity becomes
``absent`` with ``removed_at``, and every status or version change appends a ``self_model_history`` row.
The keys are computed in code by ``services/self_model_reconcile.entity_key``.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

self_model_entities = Table(
    "self_model_entities",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("entity_key", String(512), nullable=False, unique=True),
    Column("kind", String(16), nullable=False),
    Column("name", String(255), nullable=False),
    Column("parent_key", String(512), nullable=True),
    # SET NULL, not CASCADE: removing a node row must not delete the model's record of it.
    Column("node_id", String(64), ForeignKey("nodes.node_id", ondelete="SET NULL"), nullable=True),
    Column("status", String(16), nullable=False),
    Column("version", String(128), nullable=True),
    Column("first_seen", DateTime(timezone=True), nullable=False),
    Column("last_seen", DateTime(timezone=True), nullable=False),
    Column("removed_at", DateTime(timezone=True), nullable=True),
    Column("attrs", JSONB, nullable=False, server_default="{}"),
    Index("ix_self_model_entities_kind_status", "kind", "status"),
    Index("ix_self_model_entities_node_id", "node_id"),
    Index("ix_self_model_entities_parent_key", "parent_key"),
)

MAX_NAME_LENGTH = self_model_entities.c.name.type.length
MAX_VERSION_LENGTH = self_model_entities.c.version.type.length

self_model_history = Table(
    "self_model_history",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("entity_key", String(512), nullable=False),
    Column("event", String(24), nullable=False),
    Column("old_status", String(16), nullable=True),
    Column("new_status", String(16), nullable=True),
    Column("old_version", String(128), nullable=True),
    Column("new_version", String(128), nullable=True),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Index("ix_self_model_history_entity_key", "entity_key", "id"),
)
