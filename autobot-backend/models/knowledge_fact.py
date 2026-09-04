# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The durable home of a knowledge fact (#15663, closing #12733's loss path).

A fact used to exist only as a Redis hash. Redis with RDB snapshots is a cache
that survives most restarts, which is not the same thing as a system of record:
#12733 watched 43 facts go to 0 while their 22 ChromaDB vectors survived,
because nothing else had ever written them down.

This row is now the fact. The ``fact:<id>`` hash is a read projection of it and
the ChromaDB vector is a search index over it, both rebuildable from here --
see ``autobot_shared/store_authority.py`` for the declaration and
``FactsMixin.rebuild_fact_projections`` for the rebuild.

``content`` and ``metadata_json`` carry the fact verbatim. ChromaDB deliberately
does not: ``sanitize_metadata_for_chromadb`` flattens what its metadata columns
cannot hold, so the vector store is lossy by design and could never have served
as the durable copy.
"""

import uuid

from sqlalchemy import Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from user_management.models.base import Base


class KnowledgeFact(Base):
    """One user-owned knowledge fact, durable independently of Redis."""

    __tablename__ = "knowledge_facts"

    #: The fact id every other store keys on: the Redis ``fact:<id>`` hash and
    #: the ChromaDB document id are both this value, so the three stores can be
    #: compared without a mapping table.
    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    content = Column(Text(), nullable=False)
    metadata_json = Column(JSONB(), nullable=False, server_default="{}")

    #: Truncated SHA-256 of the content, mirroring the ``content_hash:<hash>``
    #: Redis key that carries deduplication today. Kept here so the dedup index
    #: is rebuildable rather than being a second original.
    content_hash = Column(String(64), nullable=True, index=True)
    #: ``metadata["unique_key"]`` when present -- the man-page ingest path's
    #: idempotency key, likewise a projection source rather than Redis-only state.
    unique_key = Column(String(255), nullable=True, index=True)

    owner_id = Column(String(255), nullable=True, index=True)
    source_session_id = Column(String(255), nullable=True, index=True)

    #: When ChromaDB last confirmed a vector for this row. Written by the
    #: reconciler as a **record of an observation**, never read as the authority
    #: for whether a vector exists -- rule 3, and the exact drift #12733 hit.
    vector_seen_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_knowledge_facts_owner_session", "owner_id", "source_session_id"),)

    def __repr__(self) -> str:
        return f"<KnowledgeFact id={self.id!r} owner_id={self.owner_id!r}>"
