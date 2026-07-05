# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for VectorWriteBuffer flush guards — Issue #10941.

Covers:
  - write() rejects entries with empty embedding at enqueue time
  - make_chromadb_flush_fn filters empty-embedding entries at flush time
  - valid entries in a mixed batch are NOT dropped alongside malformed ones
  - all-empty batch skips vector_store.add entirely
  - empty batch short-circuits before vector_store.add
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.write_buffer import BufferedWrite, VectorWriteBuffer, make_chromadb_flush_fn

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_EMBEDDING = [0.1, 0.2, 0.3]


def _make_entry(id_: str, embedding: list) -> BufferedWrite:
    return BufferedWrite(id=id_, embedding=embedding, document="doc", metadata={})


# ---------------------------------------------------------------------------
# VectorWriteBuffer.write — upstream guard (Issue #10941)
# ---------------------------------------------------------------------------


class TestWriteRejectsEmptyEmbedding:
    """write() must not enqueue entries with empty or None embeddings."""

    @pytest.mark.asyncio
    async def test_empty_list_is_rejected(self):
        flush_fn = AsyncMock()
        buf = VectorWriteBuffer(flush_fn=flush_fn, flush_size=1)
        await buf.write(id="bad", embedding=[], document="text")
        # flush_size=1 means a valid entry would trigger immediate flush;
        # since nothing was enqueued, flush_fn must NOT be called.
        flush_fn.assert_not_called()
        assert buf.pending_count == 0

    @pytest.mark.asyncio
    async def test_none_embedding_is_rejected(self):
        flush_fn = AsyncMock()
        buf = VectorWriteBuffer(flush_fn=flush_fn, flush_size=1)
        await buf.write(id="bad", embedding=None, document="text")  # type: ignore[arg-type]
        flush_fn.assert_not_called()
        assert buf.pending_count == 0

    @pytest.mark.asyncio
    async def test_valid_embedding_is_accepted(self):
        flush_fn = AsyncMock()
        buf = VectorWriteBuffer(flush_fn=flush_fn, flush_size=100)
        await buf.write(id="good", embedding=VALID_EMBEDDING, document="text")
        assert buf.pending_count == 1

    @pytest.mark.asyncio
    async def test_write_count_not_incremented_for_rejected_entry(self):
        flush_fn = AsyncMock()
        buf = VectorWriteBuffer(flush_fn=flush_fn)
        await buf.write(id="bad", embedding=[], document="text")
        # _write_count is incremented only for accepted entries
        assert buf._write_count == 0


# ---------------------------------------------------------------------------
# make_chromadb_flush_fn — flush-time guard (Issue #10941)
# ---------------------------------------------------------------------------


class TestMakeChromadbFlushFn:
    """Defense-in-depth: flush fn filters malformed entries without raising."""

    @pytest.mark.asyncio
    async def test_empty_embedding_entry_is_skipped(self):
        """A batch containing one empty-embedding entry must not call vector_store.add."""
        vector_store = MagicMock()
        vector_store.add = MagicMock(return_value=[])

        flush_fn = make_chromadb_flush_fn(vector_store)
        batch = [_make_entry("bad", [])]

        with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *a, **kw: fn(*a, **kw))):
            await flush_fn(batch)

        vector_store.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_embedding_entry_is_skipped(self):
        vector_store = MagicMock()
        vector_store.add = MagicMock(return_value=[])

        flush_fn = make_chromadb_flush_fn(vector_store)
        bad = BufferedWrite(id="bad", embedding=None, document="doc", metadata={})  # type: ignore[arg-type]

        with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *a, **kw: fn(*a, **kw))):
            await flush_fn([bad])

        vector_store.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_entries_in_mixed_batch_are_not_dropped(self):
        """Valid entries must reach vector_store.add even when the batch also contains
        malformed entries — this is the core data-loss regression guard."""
        vector_store = MagicMock()
        captured_nodes: list = []

        def _fake_add(nodes):
            captured_nodes.extend(nodes)
            return [n.node_id for n in nodes]

        vector_store.add = _fake_add

        flush_fn = make_chromadb_flush_fn(vector_store)
        batch = [
            _make_entry("bad1", []),
            _make_entry("good1", VALID_EMBEDDING),
            _make_entry("bad2", None),  # type: ignore[arg-type]
            _make_entry("good2", [0.4, 0.5, 0.6]),
        ]

        with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *a, **kw: fn(*a, **kw))):
            await flush_fn(batch)

        node_ids = [n.node_id for n in captured_nodes]
        assert "good1" in node_ids, "good1 must be stored"
        assert "good2" in node_ids, "good2 must be stored"
        assert "bad1" not in node_ids, "bad1 must be skipped"
        assert "bad2" not in node_ids, "bad2 must be skipped"
        assert len(captured_nodes) == 2

    @pytest.mark.asyncio
    async def test_all_valid_batch_passes_through_unchanged(self):
        """Happy path: an all-valid batch must call vector_store.add with all nodes."""
        vector_store = MagicMock()
        captured: list = []
        vector_store.add = lambda nodes: captured.extend(nodes) or []

        flush_fn = make_chromadb_flush_fn(vector_store)
        batch = [
            _make_entry("a", [0.1]),
            _make_entry("b", [0.2]),
        ]

        with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *a, **kw: fn(*a, **kw))):
            await flush_fn(batch)

        assert len(captured) == 2
        assert {n.node_id for n in captured} == {"a", "b"}

    @pytest.mark.asyncio
    async def test_all_empty_batch_skips_add(self):
        """An all-malformed batch must skip vector_store.add entirely (no IndexError)."""
        vector_store = MagicMock()
        vector_store.add = MagicMock(side_effect=IndexError("list index out of range"))

        flush_fn = make_chromadb_flush_fn(vector_store)
        batch = [_make_entry("x", []), _make_entry("y", [])]

        # Must not raise, must not call add
        with patch("asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *a, **kw: fn(*a, **kw))):
            await flush_fn(batch)

        vector_store.add.assert_not_called()


# ---------------------------------------------------------------------------
# VectorWriteBuffer._flush — end-to-end with make_chromadb_flush_fn
# ---------------------------------------------------------------------------


class TestFlushEndToEnd:
    """Verify the buffer + flush function together stop data loss."""

    @pytest.mark.asyncio
    async def test_no_error_logged_when_all_embeddings_valid(self):
        """flush() on an all-valid buffer must succeed without calling on_flush_error."""
        on_error = AsyncMock()
        calls: list = []

        async def flush_fn(batch):
            calls.append(batch)

        buf = VectorWriteBuffer(flush_fn=flush_fn, flush_size=100, on_flush_error=on_error)
        await buf.write("id1", VALID_EMBEDDING, "doc1")
        await buf.flush_now()

        assert len(calls) == 1
        on_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_embedding_write_never_reaches_flush_fn(self):
        """A write() with empty embedding must not enqueue, so flush_fn is never
        given a malformed entry even if the upstream guard were bypassed."""
        flush_fn = AsyncMock()
        buf = VectorWriteBuffer(flush_fn=flush_fn, flush_size=100)
        await buf.write("bad", [], "doc")
        await buf.flush_now()
        # Nothing to flush — flush_fn not called
        flush_fn.assert_not_called()
