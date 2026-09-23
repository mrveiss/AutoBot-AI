# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Both store_fact and update_fact redact credentials before persist/Redis/
ChromaDB all see the content (#13708 review of #16895).

sanitize_fact_content (knowledge/ingest_sanitize.py) is the shared chokepoint
both call -- store_fact for new facts, update_fact for a fact's content being
edited -- so this drives the real public methods end-to-end rather than the
internal _store_and_vectorize_fact helper: a review of the first version of
this fix found update_fact reaches persist/Redis/ChromaDB through a
completely separate path that never touched redaction at all.
"""

from unittest.mock import AsyncMock, patch

import pytest

import knowledge.facts as facts_module
from tests.helpers.fake_kb import FactsFakeKB

_SECRET = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"


def _passthrough(f, *args, **kwargs):
    return f(*args, **kwargs)


# ---------------------------------------------------------------------------
# store_fact -- new facts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_fact_redacts_before_persist_fact():
    kb = FactsFakeKB()
    captured = {}

    async def _persist(fact_id, content, metadata, **_kwargs):
        captured["persist_fact"] = content

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_persist)),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
        patch.object(type(kb), "_check_for_duplicates", new=AsyncMock(return_value=None)),
    ):
        result = await kb.store_fact(f"your API key is {_SECRET}", {}, fact_id="fact-1")

    assert result["status"] == "success"
    assert _SECRET not in captured["persist_fact"]
    assert "your API key is" in captured["persist_fact"]


@pytest.mark.asyncio
async def test_store_fact_redacts_before_the_redis_projection():
    kb = FactsFakeKB()
    captured = {}

    async def _project(fact_id, content, metadata, **_kwargs):
        captured["redis"] = content

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock()),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock(side_effect=_project)),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
        patch.object(type(kb), "_check_for_duplicates", new=AsyncMock(return_value=None)),
    ):
        await kb.store_fact(f"password is {_SECRET}", {}, fact_id="fact-2")

    assert _SECRET not in captured["redis"]


@pytest.mark.asyncio
async def test_store_fact_redacts_before_chromadb_vectorization():
    kb = FactsFakeKB()
    captured = {}

    async def _vectorize(fact_id, content, metadata):
        captured["chromadb"] = content

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock()),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock(side_effect=_vectorize)),
        patch.object(type(kb), "_check_for_duplicates", new=AsyncMock(return_value=None)),
    ):
        await kb.store_fact(f"token: {_SECRET}", {}, fact_id="fact-3")

    assert _SECRET not in captured["chromadb"]


@pytest.mark.asyncio
async def test_store_fact_a_safe_body_is_unchanged():
    """Negative control: the redaction pass must not mangle ordinary content."""
    kb = FactsFakeKB()
    captured = {}

    async def _persist(fact_id, content, metadata, **_kwargs):
        captured["persist_fact"] = content

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_persist)),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
        patch.object(type(kb), "_check_for_duplicates", new=AsyncMock(return_value=None)),
    ):
        await kb.store_fact("Redis listens on port 6379.", {}, fact_id="fact-4")

    assert captured["persist_fact"] == "Redis listens on port 6379."


# ---------------------------------------------------------------------------
# update_fact -- editing an existing fact's content (the gap the review found:
# this reaches persist/Redis/ChromaDB through a separate path from store_fact)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_fact_redacts_the_durable_store():
    kb = FactsFakeKB()
    kb.vector_store = None  # isolate to the durable write; no ChromaDB call to mock
    captured = {}

    async def _durable_update(fact_id, content, metadata, **_kwargs):
        captured["durable"] = content
        return True

    with (
        patch("knowledge.fact_projection.asyncio.to_thread", side_effect=_passthrough),
        patch.object(
            facts_module.FactsMixin,
            "_read_fact_for_write",
            new=AsyncMock(return_value=({"content": "old body", "timestamp": ""}, {})),
        ),
        patch.object(type(kb), "_durable_update_or_adopt", new=AsyncMock(side_effect=_durable_update)),
    ):
        result = await kb.update_fact("fact-1", content=f"your API key is {_SECRET}")

    assert result["status"] == "success"
    assert _SECRET not in captured["durable"]
    assert "your API key is" in captured["durable"]


@pytest.mark.asyncio
async def test_update_fact_redacts_the_redis_hset():
    kb = FactsFakeKB()
    kb.vector_store = None
    hset_calls = []
    kb.redis_client.hset = lambda key, mapping: hset_calls.append(mapping)

    with (
        patch("knowledge.fact_projection.asyncio.to_thread", side_effect=_passthrough),
        patch.object(
            facts_module.FactsMixin,
            "_read_fact_for_write",
            new=AsyncMock(return_value=({"content": "old body", "timestamp": ""}, {})),
        ),
        patch.object(type(kb), "_durable_update_or_adopt", new=AsyncMock(return_value=True)),
    ):
        await kb.update_fact("fact-2", content=f"password is {_SECRET}")

    assert len(hset_calls) == 1
    assert _SECRET not in hset_calls[0]["content"]


@pytest.mark.asyncio
async def test_update_fact_redacts_the_chromadb_revectorize():
    kb = FactsFakeKB(vector_store=object())  # truthy: update_fact only revectorizes when set
    captured = {}

    async def _revectorize(fact_id, content, current_metadata):
        captured["chromadb"] = content

    with (
        patch("knowledge.fact_projection.asyncio.to_thread", side_effect=_passthrough),
        patch.object(
            facts_module.FactsMixin,
            "_read_fact_for_write",
            new=AsyncMock(return_value=({"content": "old body", "timestamp": ""}, {})),
        ),
        patch.object(type(kb), "_durable_update_or_adopt", new=AsyncMock(return_value=True)),
        patch.object(type(kb), "_revectorize_fact", new=AsyncMock(side_effect=_revectorize)),
    ):
        result = await kb.update_fact("fact-3", content=f"token: {_SECRET}")

    assert result["status"] == "success"
    assert _SECRET not in captured["chromadb"]


@pytest.mark.asyncio
async def test_resubmitting_the_same_secret_is_recognized_as_a_duplicate():
    """#17005: dedup used to be asymmetric -- the write-side hash indexed
    redacted content while the read-side duplicate check hashed raw content,
    so a resubmitted secret never matched its own earlier (redacted) copy.
    Moving redaction ahead of _check_for_duplicates (this fix) makes both
    sides hash the same text. Real store_fact calls, real Redis-hash dedup
    logic (an in-memory fake redis_client, not a mock of _find_existing_fact
    or _project_fact_to_redis themselves) -- only persist_fact (durable row)
    and the ChromaDB layer are mocked, since they're not what dedup reads."""
    kb = FactsFakeKB()
    store = {}
    kb.redis_client.get = lambda key: store.get(key)
    kb.redis_client.set = lambda key, value: store.__setitem__(key, value)
    kb.redis_client.hset = lambda key, mapping: store.__setitem__(key, mapping)

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
    ):
        first = await kb.store_fact(f"your API key is {_SECRET}", {}, fact_id="fact-a")
        second = await kb.store_fact(f"your API key is {_SECRET}", {}, fact_id="fact-b")

    assert first["status"] == "success"
    assert second["status"] == "duplicate"
    assert second["fact_id"] == "fact-a"


@pytest.mark.asyncio
async def test_two_different_secrets_do_not_collide_as_duplicates():
    """#13708 round 4: the regression this fix's OWN first draft introduced.

    redact_content masks every credential to the identical fixed placeholder,
    so hashing the REDACTED text (what the previous draft of this fix did)
    makes "token: A" and "token: B" hash identically -- the second, genuinely
    different fact would be silently rejected as a duplicate of the first,
    which is real data loss. The dedup hash must key on what the caller
    submitted (store_fact's own local `raw_content`, captured before
    sanitize_fact_content runs), not the redacted text that's actually stored.
    Mirrors the same-secret test's real store_fact + in-memory-Redis setup."""
    kb = FactsFakeKB()
    store = {}
    kb.redis_client.get = lambda key: store.get(key)
    kb.redis_client.set = lambda key, value: store.__setitem__(key, value)
    kb.redis_client.hset = lambda key, mapping: store.__setitem__(key, mapping)

    secret_a = "sk-" + "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    secret_b = "sk-" + "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
    ):
        first = await kb.store_fact(f"your API key is {secret_a}", {}, fact_id="fact-a")
        second = await kb.store_fact(f"your API key is {secret_b}", {}, fact_id="fact-b")

    assert first["status"] == "success"
    assert second["status"] == "success", "two different secrets must not be treated as duplicates"


@pytest.mark.asyncio
async def test_two_different_secrets_get_different_durable_content_hashes():
    """#13708 round 4 review, BLOCK 2: the durable Postgres content_hash column
    (fact_store._row_values) kept hashing the REDACTED content, because
    hash_content was threaded through the Redis-side projection but never
    through fact_store.persist_fact/update_fact -- so two different secrets,
    both masked to the identical placeholder, collided into the SAME durable
    dedup hash even after the Redis-side collision (above) was fixed.

    The other dedup tests in this file mock fact_store.persist_fact away
    entirely, so they cannot see this: the real content_hash() computation
    never runs. This one fakes only the SQLAlchemy session factory, so the
    real fact_store.persist_fact -> _row_values -> content_hash chain
    executes and its actual output is asserted on.
    """
    import knowledge.fact_store as fact_store_module

    written_rows = []

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def get(self, _model, _fact_id):
            return None

        def add(self, row):
            written_rows.append(row)

        async def commit(self):
            pass

    def _factory():
        return _FakeSession()

    kb = FactsFakeKB()
    secret_a = "sk-" + "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    secret_b = "sk-" + "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    with (
        patch.object(fact_store_module, "get_async_session_factory", return_value=_factory),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
        patch.object(type(kb), "_check_for_duplicates", new=AsyncMock(return_value=None)),
    ):
        await kb.store_fact(f"your API key is {secret_a}", {}, fact_id="fact-a")
        await kb.store_fact(f"your API key is {secret_b}", {}, fact_id="fact-b")

    assert len(written_rows) == 2
    hash_a, hash_b = written_rows[0].content_hash, written_rows[1].content_hash
    assert hash_a != hash_b, "two different secrets must not collide into the same durable content_hash"
    assert hash_a == fact_store_module.content_hash(f"your API key is {secret_a}")
    assert hash_b == fact_store_module.content_hash(f"your API key is {secret_b}")


@pytest.mark.asyncio
async def test_update_fact_a_safe_body_is_unchanged():
    """Negative control for the update_fact path."""
    kb = FactsFakeKB()
    kb.vector_store = None
    captured = {}

    async def _durable_update(fact_id, content, metadata, **_kwargs):
        captured["durable"] = content
        return True

    with (
        patch("knowledge.fact_projection.asyncio.to_thread", side_effect=_passthrough),
        patch.object(
            facts_module.FactsMixin,
            "_read_fact_for_write",
            new=AsyncMock(return_value=({"content": "old body", "timestamp": ""}, {})),
        ),
        patch.object(type(kb), "_durable_update_or_adopt", new=AsyncMock(side_effect=_durable_update)),
    ):
        await kb.update_fact("fact-4", content="Redis listens on port 6379.")

    assert captured["durable"] == "Redis listens on port 6379."
