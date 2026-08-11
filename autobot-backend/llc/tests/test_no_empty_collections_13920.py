# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reading a KB does not create it, and deleting an entity drops it (#13920).

The ChromaDB Explorer listed **37 collections, 32 of them empty** on one
deployment. They were not orphans of deleted sessions: read and delete paths
were calling ``get_or_create_collection``, so merely *querying* an entity KB
that never had anything ingested materialised a permanent empty collection.

The cost is not only the noise. An entity KB that *should* hold content and
does not becomes indistinguishable from one that was queried once — the
accumulation hides exactly the signal an operator would look for.

Asserted against a hand-written in-memory store, not a MagicMock. The property
under test is *what the store contains afterwards*; a MagicMock would only
confirm which method name was called, which is a restatement of the fix.

The root conftest stubs ``chromadb`` outright (it hangs at import without a
local server), so a real ``EphemeralClient()`` here is a MagicMock whose every
call succeeds — the first draft of this file did exactly that and was asserting
nothing. The fake below implements the one behaviour that matters, and
``test_real_chromadb_raises_notfounderror_for_a_missing_collection`` pins that
behaviour against the real library whenever it is genuinely importable, so the
fake cannot quietly drift from what it stands in for.
"""

from __future__ import annotations

import uuid

import pytest

from utils.async_chromadb_client import AsyncChromaClient


class _FakeChroma:
    """The slice of chromadb's sync client these paths use.

    ``get_collection`` raises ``NotFoundError`` for an absent name — that is
    the contract ``get_collection_or_none`` is built on, and the reason a
    ``create``-on-read was needed before.
    """

    def __init__(self):
        self.collections: dict[str, "_FakeCollection"] = {}

    def list_collections(self):
        return [type("C", (), {"name": n})() for n in self.collections]

    def get_collection(self, name, embedding_function=None):
        from chromadb.errors import NotFoundError

        if name not in self.collections:
            raise NotFoundError(f"Collection {name} does not exist")
        return self.collections[name]

    def get_or_create_collection(self, name, metadata=None, embedding_function=None):
        return self.collections.setdefault(name, _FakeCollection(name))

    def create_collection(self, name, metadata=None, embedding_function=None):
        self.collections[name] = _FakeCollection(name)
        return self.collections[name]

    def delete_collection(self, name):
        self.collections.pop(name, None)


class _FakeCollection:
    def __init__(self, name):
        self.name = name
        self.deleted_ids: list = []

    def delete(self, ids=None, where=None):
        self.deleted_ids.extend(ids or [])

    def query(self, **kwargs):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


@pytest.fixture
async def client():
    c = AsyncChromaClient.__new__(AsyncChromaClient)
    c._client = _FakeChroma()
    c._collection_cache = {}
    return c


def test_real_chromadb_raises_notfounderror_for_a_missing_collection():
    """Pin the contract the fake encodes, against the real library.

    Skipped where the root conftest's stub is in place — under the stub this
    would assert against a MagicMock and pass regardless, which is the failure
    mode the fake exists to avoid rather than reproduce.
    """
    import chromadb

    # __path__, not __file__: the stub is a real ModuleType whose __getattr__
    # hands back a MagicMock for any missing attribute, so a __file__ check
    # returns something truthy and the skip never fires. __path__ is set
    # explicitly on the stub (to []) and is non-empty on the real package.
    if not list(getattr(chromadb, "__path__", []) or []):
        pytest.skip("chromadb is stubbed by the root conftest")

    from chromadb.errors import NotFoundError

    real = chromadb.EphemeralClient()
    with pytest.raises(NotFoundError):
        real.get_collection("definitely_absent")


# --------------------------------------------------------- the helper itself


@pytest.mark.asyncio
async def test_get_collection_or_none_returns_none_without_creating(client):
    """The whole point: asking must not be the same as making."""
    before = await client.list_collections()

    result = await client.get_collection_or_none("never_ingested")

    assert result is None
    assert await client.list_collections() == before, "a lookup created the collection it was only asking about"


@pytest.mark.asyncio
async def test_get_collection_or_none_returns_an_existing_collection(client):
    """It must still find what is there — a helper that always returns None
    would pass the test above and break every read."""
    await client.create_collection("real_one")

    result = await client.get_collection_or_none("real_one")

    assert result is not None


@pytest.mark.asyncio
async def test_a_connection_failure_is_not_reported_as_absence(client):
    """Absence and unreachability must not collapse into the same answer.

    Callers treat ``None`` as "no results". If a broken ChromaDB also returned
    ``None``, an outage would surface as silently empty answers — the same
    class of defect this issue is about, one layer down.
    """

    async def boom(*a, **k):
        raise RuntimeError("chromadb unreachable")

    client.get_collection = boom

    with pytest.raises(RuntimeError):
        await client.get_collection_or_none("anything")


# ------------------------------------------------------- the calling paths


@pytest.mark.asyncio
async def test_querying_an_entity_kb_leaves_the_store_unchanged(client, monkeypatch):
    """The acceptance criterion, against the real read path.

    ``_query_collection`` is the function that was calling
    ``get_or_create_collection`` before returning query results.
    """
    from llc.kb.rag_assembler import LLCRAGAssembler

    before = await client.list_collections()

    assembler = LLCRAGAssembler.__new__(LLCRAGAssembler)
    result = await assembler._query_collection(client, "work_item:" + str(uuid.uuid4()), "anything", 5)

    assert await client.list_collections() == before, "a query created the collection"
    assert result == {"chunks": [], "sources": []}, "a missing collection must read as empty, not raise"


@pytest.mark.asyncio
async def test_deleting_from_a_missing_collection_does_not_create_it(client):
    """Deleting from a collection that does not exist is already a no-op.

    Creating one so the delete has somewhere to go leaves an empty collection
    behind forever — which is how the ``company_*`` entries appeared.
    """
    before = await client.list_collections()

    collection = await client.get_collection_or_none("company:" + str(uuid.uuid4()))
    if collection is not None:  # pragma: no cover
        await collection.delete(ids=["x"])

    assert await client.list_collections() == before


# ------------------------------------------------------------ dropping them


@pytest.mark.asyncio
async def test_drop_collection_removes_an_existing_one(client, monkeypatch):
    from llc.kb import collections as kb_collections

    await client.create_collection("work_item:abc")

    class _KB:
        _async_chroma_client = client

    async def _kb():
        return _KB()

    monkeypatch.setattr(kb_collections, "_get_kb", _kb)

    dropped = await kb_collections.KbCollectionManager().drop_collection("work_item", "abc")

    assert dropped is True
    assert "work_item:abc" not in await client.list_collections()


@pytest.mark.asyncio
async def test_drop_collection_is_a_no_op_when_absent(client, monkeypatch):
    """Deleting an entity must not fail because its KB is already gone."""
    from llc.kb import collections as kb_collections

    class _KB:
        _async_chroma_client = client

    async def _kb():
        return _KB()

    monkeypatch.setattr(kb_collections, "_get_kb", _kb)

    assert await kb_collections.KbCollectionManager().drop_collection("work_item", "gone") is False


@pytest.mark.asyncio
async def test_drop_collection_never_raises_when_chromadb_is_down(monkeypatch):
    """The asymmetry that decides this design.

    A stranded collection is a tidiness problem; a delete that 500s because the
    vector store is unreachable is a correctness one. The entity is the source
    of truth, so the drop is best-effort by design — not by oversight.
    """
    from llc.kb import collections as kb_collections

    async def _kb():
        raise RuntimeError("chromadb unreachable")

    monkeypatch.setattr(kb_collections, "_get_kb", _kb)

    assert await kb_collections.KbCollectionManager().drop_collection("work_item", "x") is False


# ------------------------------------------------------------- wiring guards


def test_no_read_or_delete_path_still_creates_on_access():
    """The two sites this issue named must not regress to get_or_create.

    A future edit reinstating ``get_or_create_collection`` on a read path would
    restore the growth silently — nothing fails, collections just accumulate
    again, which is precisely why it went unnoticed the first time.
    """
    import pathlib

    llc = pathlib.Path(__file__).resolve().parents[1]

    # Scoped to the READ/DELETE functions, not whole files. goal.py's
    # _index_goal is a write path where get_or_create is exactly right — a
    # file-level assertion flagged it and would have pushed the fix in the
    # wrong direction.
    import ast

    for rel, func in (("kb/rag_assembler.py", "_query_collection"), ("services/goal.py", "_delete_from_chromadb")):
        tree = ast.parse((llc / rel).read_text(encoding="utf-8"))
        node = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef) and n.name == func),
            None,
        )
        assert node is not None, f"{rel} no longer defines {func} — the guard would silently cover nothing"
        called = {n.func.attr for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert (
            "get_or_create_collection" not in called
        ), f"{rel}:{func} creates a collection on a path that only reads or deletes — see #13920"


def test_every_entity_delete_drops_its_collection():
    """Each of the four delete paths reaches ``drop_collection``.

    Named individually so a regression says *which* entity leaks, rather than
    that "something" does.
    """
    import pathlib

    llc = pathlib.Path(__file__).resolve().parents[1]

    for rel in (
        "api/work_items.py",
        "api/sprints.py",
        "api/companies.py",
        "services/project_disposal.py",
    ):
        source = (llc / rel).read_text(encoding="utf-8")
        assert "drop_collection" in source, f"{rel} deletes an entity without dropping its KB collection (#13920)"
