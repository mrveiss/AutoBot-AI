# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One name builder for LLC KB collections, shared by create and query (#19519).

Creation stored ``company:<id>`` while the heartbeat RAG query asked for
``<id>:company``, so an agent's company context was always empty. These tests
pin the two directions to the same builder, prove a real create-then-query
round trip finds the document, and guard against a hand-built name coming back.
"""

import ast
import re
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.kb.collections import (
    KbCollectionManager,
    agent_collection,
    company_collection,
    company_id_of,
    project_collection,
)
from llc.kb.inheritance import KbInheritanceResolver
from llc.kb.rag_assembler import AssemblerProfile, LLCRAGAssembler, _collections_for

_LLC_ROOT = Path(__file__).resolve().parents[1]
_BUILDER_MODULE = _LLC_ROOT / "kb" / "collections.py"


def test_create_and_query_build_the_same_names() -> None:
    cid, pid, aid = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    created = {
        KbCollectionManager.collection_name(KbCollectionManager.COMPANY_PREFIX, cid),
        KbCollectionManager.collection_name(KbCollectionManager.PROJECT_PREFIX, pid),
        KbCollectionManager.collection_name(KbCollectionManager.AGENT_PREFIX, aid),
    }
    queried = set(_collections_for(cid, pid, aid))
    assert queried == created
    assert company_collection(cid) == f"company:{cid}"
    assert project_collection(pid) == f"project:{pid}"
    assert agent_collection(aid) == f"agent:{aid}"


def test_company_id_parses_back_from_every_company_name() -> None:
    cid = str(uuid.uuid4())
    for suffix in (None, KbCollectionManager.AGENTS_SUFFIX, KbCollectionManager.DECISIONS_SUFFIX):
        assert company_id_of(company_collection(cid, suffix)) == cid
    for bad in (f"{cid}:company", f"project:{cid}", "company:", "company"):
        with pytest.raises(ValueError):
            company_id_of(bad)


@pytest.mark.asyncio
async def test_inheritance_chain_names_are_the_created_names() -> None:
    org = SimpleNamespace(id=uuid.uuid4(), parent_org_id=None, kb_inheritance_weight=0.6)
    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=org))
    chain = await KbInheritanceResolver().get_query_collections(session, str(org.id))
    created = KbCollectionManager.collection_name(KbCollectionManager.COMPANY_PREFIX, org.id)
    assert chain == [(created, pytest.approx(1.0))]


_CHROMA_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{1,510}[a-zA-Z0-9]$")


class _FakeRawCollection:
    """Stores upserted documents; a query returns them all at distance 0."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._docs: dict[str, tuple[str, dict | None]] = {}

    async def upsert(self, ids, documents=None, metadatas=None, embeddings=None):
        for i, doc_id in enumerate(ids):
            self._docs[doc_id] = (documents[i], metadatas[i] if metadatas else None)

    async def query(self, **_kwargs):
        docs = list(self._docs.values())
        return {
            "documents": [[d for d, _ in docs]],
            "metadatas": [[m for _, m in docs]],
            "distances": [[0.0 for _ in docs]],
        }


class _FakeRawChroma:
    """Stand-in for ``utils.async_chromadb_client.AsyncChromaClient``.

    Enforces ChromaDB 1.x's collection-name rule — the reason a raw lookup of
    ``company:<id>`` fails in production — so the round trip below exercises
    the real adapter's name mapping on both the create and the query side.
    """

    def __init__(self) -> None:
        self.collections: dict[str, _FakeRawCollection] = {}

    def _check(self, name: str) -> str:
        if not _CHROMA_NAME.match(name):
            raise ValueError(f"invalid ChromaDB collection name: {name!r}")
        return name

    async def get_or_create_collection(self, name, metadata=None, embedding_function=None):
        return self.collections.setdefault(self._check(name), _FakeRawCollection(name))

    async def get_collection(self, name, embedding_function=None):
        return self.collections[self._check(name)]

    async def get_collection_or_none(self, name, embedding_function=None):
        return self.collections.get(self._check(name))


def _kb_client():
    from knowledge.backends.async_chromadb_adapter import AsyncChromaDBClient

    return AsyncChromaDBClient(_FakeRawChroma())


@pytest.mark.asyncio
async def test_round_trip_created_company_collection_is_found_by_heartbeat_query() -> None:
    client = _kb_client()
    company_id = str(uuid.uuid4())
    with patch("llc.kb.collections._get_kb", new=AsyncMock(return_value=SimpleNamespace(_async_chroma_client=client))):
        name = await KbCollectionManager().ensure_collection(KbCollectionManager.COMPANY_PREFIX, company_id)
        collection = await client.get_collection(name)
        await collection.upsert(ids=["policy-1"], documents=["Ship on Fridays"])

        ctx = await LLCRAGAssembler().assemble(
            company_id=company_id, profile=AssemblerProfile.HEARTBEAT, query_text="when do we ship"
        )

    assert [c["content"] for c in ctx.chunks] == ["Ship on Fridays"]
    assert ctx.sources == [company_collection(company_id)]


def _string_prefix(node: ast.AST) -> str | None:
    """Leading literal text of a str constant or f-string, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) and node.values and isinstance(node.values[0], ast.Constant):
        return str(node.values[0].value)
    return None


_ENTITY_PREFIXES = tuple(
    f"{p}:"
    for p in (
        KbCollectionManager.COMPANY_PREFIX,
        KbCollectionManager.PROJECT_PREFIX,
        KbCollectionManager.SPRINT_PREFIX,
        KbCollectionManager.WORK_ITEM_PREFIX,
        KbCollectionManager.AGENT_PREFIX,
    )
)
_OLD_FRAGMENTS = (":company", ":project:", ":agent:")


def _is_name_literal(node: ast.AST) -> bool:
    text = _string_prefix(node)
    return (text is not None and text.startswith(_ENTITY_PREFIXES)) or _is_old_format(node)


def _is_old_format(node: ast.AST) -> bool:
    """``f"{id}:company"`` and kin — the reader-only spelling, flagged anywhere."""
    if not isinstance(node, ast.JoinedStr):
        return False
    parts = [v.value for v in node.values if isinstance(v, ast.Constant)]
    return any(str(p).startswith(_OLD_FRAGMENTS) for p in parts)


def _names_collection(node: ast.AST) -> bool:
    """True for a Name/Attribute/Call whose identifier says 'collection'."""
    if isinstance(node, ast.Call):
        return _names_collection(node.func)
    if isinstance(node, ast.Attribute):
        return "collection" in node.attr.lower() or _names_collection(node.value)
    return isinstance(node, ast.Name) and "collection" in node.id.lower()


def _collection_contexts(tree: ast.AST):
    """Subtrees whose value becomes a collection name: assigned, passed or returned as one."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(_names_collection(t) for t in node.targets):
            yield node.value
        elif isinstance(node, ast.Call) and _names_collection(node.func):
            yield from node.args
            yield from (kw.value for kw in node.keywords if kw.arg in (None, "name"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and "collection" in node.name.lower():
            yield from (n.value for n in ast.walk(node) if isinstance(n, ast.Return) and n.value is not None)


def _hand_built_names(tree: ast.AST) -> list[int]:
    """Lines that spell an entity collection name by hand where a name is expected."""
    hits = [
        n.lineno
        for ctx in _collection_contexts(tree)
        for n in ast.walk(ctx)
        if isinstance(n, (ast.Constant, ast.JoinedStr)) and _is_name_literal(n)
    ]
    hits += [n.lineno for n in ast.walk(tree) if _is_old_format(n)]
    return sorted(set(hits))


def _collection_name_parses(tree: ast.AST) -> list[int]:
    """Lines that split a collection name by hand instead of ``company_id_of``."""
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("split", "partition") and _names_collection(node.func.value):
                hits.append(node.lineno)
    return sorted(set(hits))


def _offenders() -> list[str]:
    found = []
    for path in sorted(_LLC_ROOT.rglob("*.py")):
        if "tests" in path.parts or path.name.endswith("_test.py") or path == _BUILDER_MODULE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        lines = _hand_built_names(tree) + _collection_name_parses(tree)
        found += [f"{path.relative_to(_LLC_ROOT)}:{n}" for n in sorted(set(lines))]
    return found


_CONTROL_SOURCE = """
collections_to_query.append(f"{cid}:company")
collection_name = f"project:{pid}"
def _collection_name(cid):
    return f"company:{cid}:agents"
await client.get_collection(f"company:{cid}")
cid = collection_name.split(":")[0]
channel = f"company:{cid}"
doc_id = f"agent:{aid}"
names.append(f"{cid}:company")
key = f"llc:company:{cid}:paused"
"""


def test_guard_detector_sees_every_hand_built_shape() -> None:
    """Control: each shape the original sites used is flagged; channels and doc ids are not."""
    tree = ast.parse(_CONTROL_SOURCE)
    assert _hand_built_names(tree) == [2, 3, 5, 6, 10]
    assert _collection_name_parses(tree) == [7]


def test_no_llc_module_hand_builds_or_parses_collection_names() -> None:
    offenders = _offenders()
    assert not offenders, f"build/parse LLC KB collection names via llc.kb.collections, not by hand: {offenders}"
