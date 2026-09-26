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

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text
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

    #: Set by migration 20260914_092 on every fact that had no owner and no visibility
    #: at deploy: the #16693 backfill's frozen candidate set. Cleared once the backfill
    #: has decided the fact. No write path sets it, so a fact stored later never is one.
    visibility_backfill_candidate = Column(Boolean, nullable=True)

    # ---- Source liveness (#17545) -------------------------------------------
    # Whether the document a fact was extracted from still resolves. Two kinds
    # of knowledge live here and must not be merged: four of these columns are
    # **observations** a probe wrote, and `source_gone_at` is an **event** that
    # was witnessed. "The source is gone" and "we could not reach the source"
    # are different facts, and only the first is a reason to act.

    #: When the locator was last probed, whatever the outcome. NULL means
    #: *never looked*, which is not *looked and could not reach* -- nothing may
    #: default this to a timestamp, or the state becomes unrepresentable and no
    #: query can ask for it.
    source_checked_at = Column(DateTime(timezone=True), nullable=True)

    #: When the locator last resolved. Frozen by definition once probing starts
    #: failing, which is exactly why `source_checked_at` is separate: without it
    #: a failure ten seconds old reads identically to one a week old.
    source_seen_at = Column(DateTime(timezone=True), nullable=True)

    #: The last probe's outcome -- `resolved`, `absent`, `unreadable` or
    #: `parent_unresolvable`. A bare counter records how many probes failed and
    #: never why, so it cannot separate repeated "the file is not there"
    #: (evidence) from repeated "the share is unreachable" (not evidence).
    source_last_probe = Column(String(32), nullable=True)

    #: Consecutive non-resolving probes, reset to 0 on a resolve. A run length,
    #: never a verdict: how much evidence is enough belongs to the consumer's
    #: retention policy (#17538), not to the detector.
    source_check_failures = Column(Integer, nullable=False, server_default="0")

    #: A deletion that was **witnessed** -- #17546's watchdog events -- never
    #: inferred from a probe. An event set by inference launders a judgement
    #: into a fact: everything downstream then treats it as observed while the
    #: threshold that produced it is no longer visible or re-evaluable, and an
    #: unmounted share becomes a deleted document. Decision on #17545.
    source_gone_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_knowledge_facts_owner_session", "owner_id", "source_session_id"),)

    def __repr__(self) -> str:
        return f"<KnowledgeFact id={self.id!r} owner_id={self.owner_id!r}>"
