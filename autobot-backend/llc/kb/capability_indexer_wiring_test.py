# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14839: capability indexing must actually reach the KB.

`_fetch_agent_row` imported `get_async_session_factory` from `llc.db`, a module
that does not exist. The import is *function-local*, so nothing failed at import
time and `from llc.kb import AgentCapabilityIndexer` succeeded normally — it
raised `ModuleNotFoundError` on every call instead. All four call sites
(`services/agent_org_service.py:265` and `:333`, `llc/services/portability.py`)
wrap the call in `except Exception` and log it as non-fatal, so agent capability
documents were never written, on any path, and the only trace was a log line.

The whole surface existed — an indexer class, a real SQL query, four wired call
sites — and the sink was unreachable.

This test therefore drives the **real** `_fetch_agent_row`. Stubbing it, or
stubbing `index_from_db`, would reproduce exactly the blind spot that let this
survive: every existing caller already tolerates the failure, so a test that
tolerates it too asserts nothing. Only the database and the KB are stubbed, at
their own boundaries.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from llc.kb.capability_indexer import AgentCapabilityIndexer

AGENT_ID = "agent-1"
COMPANY_ID = "co-1"

_ROW = {
    "agent_id": AGENT_ID,
    "name": "Ada",
    "title": "Principal Engineer",
    "org_role": "worker",
    "capabilities": "security audits, cloud devops",
    "reports_to": "mgr-1",
    "manager_name": "Grace",
}


class _FakeSession:
    def __init__(self, row):
        self._row = row

    async def execute(self, *_args, **_kwargs):
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: self._row))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


def _factory_returning(row):
    """Stands in for `get_async_session_factory` at the database boundary.

    Two levels of callable, matching production: `_fetch_agent_row` does
    `factory = get_async_session_factory()` and then `async with factory()`.
    Returning the session directly makes the second call fail with
    "'_FakeSession' object is not callable".
    """
    session_factory = lambda: _FakeSession(row)  # noqa: E731 - a one-line stub reads better inline
    return lambda: session_factory


class _FakeCollection:
    def __init__(self):
        self.upserts = []

    async def upsert(self, ids, documents, metadatas):
        self.upserts.append({"ids": ids, "documents": documents, "metadatas": metadatas})


class _FakeKB:
    def __init__(self, collection):
        self._async_chroma_client = SimpleNamespace(
            get_or_create_collection=self._get_or_create,
        )
        self._collection = collection
        self.collections = []

    async def _get_or_create(self, name, metadata=None):
        self.collections.append(name)
        return self._collection


@pytest.mark.asyncio
async def test_a_document_reaches_the_knowledge_base():
    """The assertion the previous state could not satisfy.

    Not "was index_from_db called" and not "did nothing raise" — the pre-fix
    code satisfies both of those, because every caller swallows the error.
    """
    collection = _FakeCollection()
    kb = _FakeKB(collection)

    with (
        patch("user_management.database.get_async_session_factory", _factory_returning(_ROW)),
        patch("llc.kb.capability_indexer.get_knowledge_base", return_value=kb),
    ):
        doc_id = await AgentCapabilityIndexer().index_from_db(AGENT_ID, COMPANY_ID)

    assert doc_id, "index_from_db returned nothing, so no document was written"
    assert len(collection.upserts) == 1, (
        "no document reached the KB collection. Pre-#14839 this was the state on "
        "every path — the call raised ModuleNotFoundError and every caller "
        "logged it as non-fatal."
    )

    written = collection.upserts[0]
    assert written["ids"] == [doc_id]
    assert "security audits" in written["documents"][0], "the agent's capabilities are not in the document"
    assert written["metadatas"][0]["manager_name"] == "Grace"


@pytest.mark.asyncio
async def test_a_missing_agent_writes_nothing_and_says_so():
    """The 'nothing to index' case must stay distinguishable from a failure."""
    collection = _FakeCollection()

    with (
        patch("user_management.database.get_async_session_factory", _factory_returning(None)),
        patch("llc.kb.capability_indexer.get_knowledge_base", return_value=_FakeKB(collection)),
    ):
        doc_id = await AgentCapabilityIndexer().index_from_db(AGENT_ID, COMPANY_ID)

    assert doc_id is None
    assert collection.upserts == []
