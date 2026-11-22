# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chunks the knowledge lint scans, moved out of ``api/knowledge_maintenance.py`` (#19163).

The lint is an owner-approved reader of the research quarantine (ruling 2026-10-22): it reads every
chunk, marks the quarantined ones, and its route audits the run once.
"""

from __future__ import annotations

import asyncio

from knowledge.quarantine import is_quarantined


async def _fetch_all_chunks(kb) -> list[dict]:
    """Fetch all KB chunks as dicts with a 'text' key -- kb.chroma_collection was never real (#16707).

    The lint is an owner-approved opt-out reader of the research quarantine (#19163): chunks that
    are quarantined carry ``quarantined`` and their ``id``; the caller audits the run once.
    """

    def _load():
        results = kb.vector_store._collection.get(include=["documents", "metadatas"])
        docs = results.get("documents") or []
        metas = results.get("metadatas") or [{}] * len(docs)
        ids = results.get("ids") or [None] * len(docs)
        return [_lint_chunk(i, d, m) for i, d, m in zip(ids, docs, metas)]

    return await asyncio.to_thread(_load)


def _lint_chunk(chunk_id, text, metadata) -> dict:
    """One lint chunk; a research-quarantined one is marked and carries its id (#19163)."""
    chunk = {"text": text, "metadata": metadata}
    if is_quarantined({"metadata": metadata or {}}):
        chunk.update(quarantined=True, id=chunk_id)
    return chunk
