# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A fact with no `verification_status` key still passes the store-side serving clause (#18820).

`SERVING_TRUST_WHERE` is `{"verification_status": {"$ne": "rejected"}}` (or `$nin` once #18077 withholds
more states). Facts written before the trust field existed carry no such key, and the whole fix is wrong
if the store treats "no key" as "does not match": every legacy fact would silently stop being served.

This pins the behaviour against the REAL library, and requires the in-memory fake
(`knowledge/backends/memory_adapter.py`) to agree with it on the same clauses, so the fake cannot drift.
It lives under `repo_tests/` because `autobot-backend/conftest.py` replaces `chromadb` with a stub.
"""

from __future__ import annotations

import uuid

import pytest

from knowledge.backends.memory_adapter import InMemoryCollection
from knowledge.serving import SERVING_TRUST_WHERE

_chromadb = pytest.importorskip("chromadb")
if not list(getattr(_chromadb, "__path__", []) or []):
    pytest.skip("chromadb is stubbed, not the real library", allow_module_level=True)

_IDS = ["no_key", "verified", "rejected", "pending"]
_METADATAS = [
    {"collection": "docs"},
    {"verification_status": "verified"},
    {"verification_status": "rejected"},
    {"verification_status": "pending_review"},
]
_EMBEDDINGS = [[1.0, 0.0], [1.0, 0.1], [1.0, 0.2], [1.0, 0.3]]

_CLAUSES = {
    "ne": ({"verification_status": {"$ne": "rejected"}}, ["no_key", "verified", "pending"]),
    "nin": ({"verification_status": {"$nin": ["rejected", "pending_review"]}}, ["no_key", "verified"]),
    "and_ne": (
        {"$and": [{"collection": {"$ne": "research"}}, {"verification_status": {"$ne": "rejected"}}]},
        ["no_key", "verified", "pending"],
    ),
    "and_nin": (
        {
            "$and": [
                {"collection": {"$ne": "research"}},
                {"verification_status": {"$nin": ["rejected", "pending_review"]}},
            ]
        },
        ["no_key", "verified"],
    ),
}


def _real_collection():
    collection = _chromadb.EphemeralClient().create_collection(
        f"serving-where-{uuid.uuid4().hex}", embedding_function=None
    )
    collection.add(ids=_IDS, embeddings=_EMBEDDINGS, metadatas=_METADATAS)
    return collection


def _fake_collection():
    collection = InMemoryCollection("serving_where_18820")
    collection.add(ids=_IDS, documents=_IDS, embeddings=_EMBEDDINGS, metadatas=_METADATAS)
    return collection


@pytest.mark.parametrize("name", sorted(_CLAUSES))
def test_real_chromadb_matches_a_record_with_no_status_key(name: str) -> None:
    where, expected = _CLAUSES[name]
    got = _real_collection().get(where=where)["ids"]
    assert sorted(got) == sorted(expected)


@pytest.mark.parametrize("name", sorted(_CLAUSES))
def test_the_in_memory_fake_agrees_with_real_chromadb(name: str) -> None:
    where, _ = _CLAUSES[name]
    assert sorted(_fake_collection().get(where=where)["ids"]) == sorted(_real_collection().get(where=where)["ids"])


def test_the_shipped_serving_clause_keeps_the_record_with_no_key() -> None:
    """The control: the clause the code actually ships, not a copy of it."""
    ids = _real_collection().query(query_embeddings=[[1.0, 0.0]], n_results=4, where=SERVING_TRUST_WHERE)["ids"][0]
    assert "no_key" in ids
    assert "rejected" not in ids


_AND_WITH_SIBLING = {"$and": [{"verification_status": {"$ne": "rejected"}}], "collection": "docs"}


def test_real_chromadb_rejects_and_beside_another_top_level_key() -> None:
    """The control for the fake's rejection: the real library refuses this shape."""
    with pytest.raises(ValueError, match="exactly one operator"):
        _real_collection().get(where=_AND_WITH_SIBLING)


@pytest.mark.parametrize("call", ["get", "query", "delete"])
def test_the_in_memory_fake_rejects_and_beside_another_top_level_key(call: str) -> None:
    """Evaluating ``$and`` alone would ignore ``collection`` and return more than the store would."""
    fake = _fake_collection()
    with pytest.raises(ValueError, match="exactly one operator"):
        if call == "query":
            fake.query(query_embeddings=[[1.0, 0.0]], n_results=4, where=_AND_WITH_SIBLING)
        else:
            getattr(fake, call)(where=_AND_WITH_SIBLING)
    with pytest.raises(ValueError, match="exactly one operator"):
        InMemoryCollection("empty_18820").get(where=_AND_WITH_SIBLING)
