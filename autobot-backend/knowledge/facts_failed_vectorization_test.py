# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Regression tests for Issue #12312 — embedding failures must not silently drop
vectors during inline fact vectorization.

Asserts that when embedding generation returns an empty result, the fact is:
  - NOT reported as a success (no vector write attempted);
  - marked ``vectorization_status=failed`` on its Redis hash (queryable);
  - added to the background reconciler's pending set (retriable / auto-backfill);
  - logged at ERROR level (visible without log forensics).
"""

from __future__ import annotations

import logging
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from background_vectorization import PENDING_SET_KEY
from knowledge.facts import FactsMixin

# Bind the loaded module via sys.modules so patch.object targets the same dict the
# FactsMixin methods resolve module-level globals in (conftest stub-trap safe).
facts_mod = sys.modules["knowledge.facts"]


class _KB(FactsMixin):
    """Minimal FactsMixin host with the collaborators the paths under test touch."""

    def __init__(self):
        self.redis_client = MagicMock()
        self.vector_store = MagicMock()  # truthy so vectorization is attempted
        self._write_buffer = MagicMock()
        self._write_buffer.write = AsyncMock()


@pytest.mark.asyncio
async def test_record_failed_vectorization_marks_and_queues(caplog):
    kb = _KB()

    with caplog.at_level(logging.ERROR):
        await kb._record_failed_vectorization("fact-1", "embedding generation returned an empty result")

    # Queryable failed-state written to the fact hash.
    hset_call = kb.redis_client.hset.call_args
    assert hset_call.args[0] == "fact:fact-1"
    mapping = hset_call.kwargs["mapping"]
    assert mapping["vectorization_status"] == "failed"
    assert "empty" in mapping["vectorization_error"]
    assert mapping["vectorization_failed_at"]

    # Retriable: added to the reconciler's pending set.
    kb.redis_client.sadd.assert_called_once_with(PENDING_SET_KEY, "fact-1")

    # Visible: ERROR log names the fact.
    assert any(r.levelno >= logging.ERROR and "fact-1" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_empty_embedding_records_failure_and_skips_write(caplog):
    kb = _KB()

    with patch.object(facts_mod, "_generate_embedding_with_npu_fallback", AsyncMock(return_value=[])):
        with caplog.at_level(logging.ERROR):
            await kb._vectorize_fact_in_chromadb("fact-2", "some content", {})

    # No vector was written (not a false success).
    kb._write_buffer.write.assert_not_called()
    # Failure was recorded as retriable/queryable state.
    kb.redis_client.sadd.assert_called_once_with(PENDING_SET_KEY, "fact-2")
    assert kb.redis_client.hset.call_args.kwargs["mapping"]["vectorization_status"] == "failed"


@pytest.mark.asyncio
async def test_valid_embedding_writes_and_does_not_record_failure():
    kb = _KB()

    with patch.object(facts_mod, "_generate_embedding_with_npu_fallback", AsyncMock(return_value=[0.1, 0.2, 0.3])):
        await kb._vectorize_fact_in_chromadb("fact-3", "some content", {})

    # Vector was buffered; no failure recorded.
    kb._write_buffer.write.assert_awaited_once()
    kb.redis_client.sadd.assert_not_called()
