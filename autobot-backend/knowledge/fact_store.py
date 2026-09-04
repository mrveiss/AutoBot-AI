# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Durable reads and writes for knowledge facts (#15663, #12733).

Every function here talks to the ``knowledge_facts`` table, which is the fact.
The ``fact:<id>`` Redis hash and the ChromaDB vector are projections of these
rows; ``autobot_shared/store_authority.py`` declares that relationship and
``FactsMixin.rebuild_fact_projections`` is the rebuild it promises.

Writes here are deliberately **not** best-effort. A Redis or ChromaDB failure
degrades a projection and the reconciler repairs it; a failure to write the row
means the fact was never recorded, and reporting success for that is precisely
the shape of #12733. The caller's existing error handling turns a raised
exception into an error response, so the user is told the fact was not stored
rather than discovering it missing days later.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List

from sqlalchemy import delete as sql_delete
from sqlalchemy import select, update

from autobot_shared.logging_manager import get_logger
from autobot_shared.store_authority import Store, system_of_record
from models.knowledge_fact import KnowledgeFact
from user_management.database import get_async_session_factory

logger = get_logger(__name__)

#: Declared beside the code that writes the copies, so the authority is one jump
#: from any write site rather than a document somebody has to know exists.
SYSTEM_OF_RECORD = system_of_record("knowledge_facts")
assert SYSTEM_OF_RECORD.system_of_record is Store.POSTGRES  # nosec B101

#: Matches the ``content_hash:<hash>`` Redis key width the dedup index uses.
_CONTENT_HASH_WIDTH = 16


def content_hash(content: str) -> str:
    """The deduplication fingerprint, identical to the Redis index's."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:_CONTENT_HASH_WIDTH]


def _row_values(content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """The columns a fact's content and metadata determine."""
    return {
        "content": content,
        "metadata_json": metadata,
        "content_hash": content_hash(content),
        "unique_key": metadata.get("unique_key"),
        "owner_id": metadata.get("owner_id") or metadata.get("user_id"),
        "source_session_id": metadata.get("source_session_id"),
    }


async def persist_fact(fact_id: str, content: str, metadata: Dict[str, Any]) -> None:
    """Write the durable row. Raises when the fact could not be recorded."""
    factory = get_async_session_factory()
    async with factory() as session:
        row = await session.get(KnowledgeFact, fact_id)
        if row is None:
            session.add(KnowledgeFact(id=fact_id, **_row_values(content, metadata)))
        else:
            for column, value in _row_values(content, metadata).items():
                setattr(row, column, value)
        await session.commit()


async def update_fact(fact_id: str, content: str, metadata: Dict[str, Any]) -> bool:
    """Update an existing row. ``False`` when no such fact is recorded."""
    factory = get_async_session_factory()
    async with factory() as session:
        row = await session.get(KnowledgeFact, fact_id)
        if row is None:
            return False
        for column, value in _row_values(content, metadata).items():
            setattr(row, column, value)
        await session.commit()
        return True


async def delete_fact(fact_id: str) -> bool:
    """Remove the durable row. ``False`` when there was nothing to remove."""
    factory = get_async_session_factory()
    async with factory() as session:
        result = await session.execute(sql_delete(KnowledgeFact).where(KnowledgeFact.id == fact_id))
        await session.commit()
        return bool(result.rowcount)


async def load_fact(fact_id: str) -> Dict[str, Any] | None:
    """The fact as recorded, or ``None``. Never consults Redis."""
    factory = get_async_session_factory()
    async with factory() as session:
        row = await session.get(KnowledgeFact, fact_id)
        return None if row is None else {"content": row.content, "metadata": dict(row.metadata_json or {})}


async def fact_id_for_content_hash(digest: str) -> str | None:
    """The recorded fact carrying *digest*, for deduplication on create."""
    factory = get_async_session_factory()
    async with factory() as session:
        found = await session.execute(select(KnowledgeFact.id).where(KnowledgeFact.content_hash == digest).limit(1))
        return found.scalar_one_or_none()


async def fact_id_for_unique_key(unique_key: str) -> str | None:
    """The recorded fact carrying *unique_key*, for idempotent ingest."""
    factory = get_async_session_factory()
    async with factory() as session:
        found = await session.execute(select(KnowledgeFact.id).where(KnowledgeFact.unique_key == unique_key).limit(1))
        return found.scalar_one_or_none()


async def iter_facts(batch_size: int = 500) -> AsyncIterator[List[Dict[str, Any]]]:
    """Every recorded fact, in id order, a batch at a time.

    Ordered and keyset-paged rather than offset-paged so a rebuild that runs
    while facts are being created cannot skip or repeat a row.
    """
    factory = get_async_session_factory()
    after = ""
    while True:
        async with factory() as session:
            rows = await session.execute(
                select(KnowledgeFact).where(KnowledgeFact.id > after).order_by(KnowledgeFact.id).limit(batch_size)
            )
            batch = list(rows.scalars())
        if not batch:
            return
        after = batch[-1].id
        yield [{"fact_id": r.id, "content": r.content, "metadata": dict(r.metadata_json or {})} for r in batch]


async def record_vector_seen(fact_id: str) -> None:
    """Stamp when ChromaDB last confirmed a vector. An observation, not a flag.

    Nothing reads this to decide whether a fact is vectorised -- that question is
    answered by asking ChromaDB (#15663 rule 3, and the drift #12733 hit). It
    exists so a reconciler can report *when* it last agreed with the vector store.
    """
    factory = get_async_session_factory()
    async with factory() as session:
        await session.execute(
            update(KnowledgeFact)
            .where(KnowledgeFact.id == fact_id)
            .values(vector_seen_at=datetime.now(tz=timezone.utc))
        )
        await session.commit()
