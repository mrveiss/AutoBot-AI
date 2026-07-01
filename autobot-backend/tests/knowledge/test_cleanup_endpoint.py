# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for BulkOperationsMixin.cleanup() — #10750 E1.

Verifies:
- cleanup() accepts all kwargs the endpoint sends (no TypeError regression)
- dry_run=True returns issues_found + issues_details, fixes_applied=None
- dry_run=False returns fixes_applied, issues_details=None
- Empty KB returns zeroed counts

Heavy dependencies (Redis, ChromaDB, llama_index) are stubbed via
sys.modules patching so these tests run without a live backend.
"""

from __future__ import annotations

import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub heavy imports before pulling in knowledge.bulk
# ---------------------------------------------------------------------------

for _mod in (
    "llama_index",
    "llama_index.core",
    "llama_index.vector_stores",
    "llama_index.vector_stores.chroma",
    "llama_index.llms",
    "llama_index.llms.ollama",
    "llama_index.embeddings",
    "llama_index.embeddings.ollama",
    "chromadb",
    "redis",
    "redis.asyncio",
):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

# Minimal stubs for symbols referenced at module load
_redis_mod = sys.modules["redis"]
_redis_mod.RedisError = Exception  # type: ignore[attr-defined]
_redis_mod.Redis = MagicMock  # type: ignore[attr-defined]

_aioredis_mod = sys.modules["redis.asyncio"]
_aioredis_mod.Redis = MagicMock  # type: ignore[attr-defined]

from knowledge.bulk import BulkOperationsMixin  # noqa: E402


# ---------------------------------------------------------------------------
# Fake composed KB that drives BulkOperationsMixin without a real Redis
# ---------------------------------------------------------------------------


class _FakeKB(BulkOperationsMixin):
    """Minimal KB stub exercising cleanup() with controllable in-memory data."""

    def __init__(self, facts: list[dict], tags: list[dict]) -> None:
        """
        Args:
            facts: List of {key, content, metadata_raw} dicts representing Redis hashes.
            tags:  List of {tag, fact_count} dicts for list_all_tags result.
        """
        self._facts = facts
        self._tags = tags
        self.redis_client = MagicMock()
        self._deleted: list[str] = []
        self._updated: list[tuple[str, dict]] = []
        self._tags_deleted: list[str] = []

    # ---- abstract stubs implemented for the test ----

    async def _scan_redis_keys_async(self, pattern: str) -> list[str]:
        return [f["key"] for f in self._facts]

    async def list_all_tags(self) -> dict:
        return {"status": "success", "tags": list(self._tags)}

    async def delete_tag_globally(self, tag: str) -> dict:
        self._tags_deleted.append(tag)
        # Remove from internal list so repeated calls work correctly
        self._tags = [t for t in self._tags if t["tag"] != tag]
        return {"success": True}

    async def bulk_delete(self, fact_ids: list[str]) -> dict:
        self._deleted.extend(fact_ids)
        return {"status": "success", "deleted": len(fact_ids), "errors": 0, "total": len(fact_ids)}

    async def update_fact(self, fact_id: str, **kwargs) -> dict:
        self._updated.append((fact_id, kwargs))
        return {"status": "success", "fact_id": fact_id}

    def _schedule_bm25_refresh(self) -> None:
        pass

    # ---- pipeline mock wired to self._facts ----

    def _setup_pipeline(self) -> None:
        """Wire redis_client.pipeline() to return pairs from self._facts."""
        results = []
        for f in self._facts:
            content = f.get("content", "").encode("utf-8")
            raw_meta = f.get("metadata_raw", "")
            meta = raw_meta.encode("utf-8") if raw_meta else b""
            results.append([content, meta])

        pipe_mock = MagicMock()
        pipe_mock.hmget.return_value = None
        pipe_mock.execute.return_value = results
        self.redis_client.pipeline.return_value = pipe_mock


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_kb(facts=None, tags=None) -> _FakeKB:
    kb = _FakeKB(facts or [], tags or [])
    kb._setup_pipeline()
    return kb


# ---------------------------------------------------------------------------
# Tests — dry_run=True (default)
# ---------------------------------------------------------------------------


class TestCleanupDryRun:
    @pytest.mark.asyncio
    async def test_empty_kb_returns_zero_counts(self):
        kb = _make_kb()
        result = await kb.cleanup(dry_run=True)

        assert result["status"] == "success"
        assert result["dry_run"] is True
        assert result["issues_found"] == {"empty_facts": 0, "orphaned_tags": 0, "malformed_metadata": 0}
        assert result["fixes_applied"] is None

    @pytest.mark.asyncio
    async def test_detects_empty_content_fact(self):
        kb = _make_kb(facts=[{"key": "fact:abc", "content": "  ", "metadata_raw": "{}"}])
        result = await kb.cleanup(remove_empty=True, dry_run=True)

        assert result["issues_found"]["empty_facts"] == 1
        assert "abc" in result["issues_details"]["empty_fact_ids"]
        assert result["fixes_applied"] is None

    @pytest.mark.asyncio
    async def test_detects_orphaned_tag(self):
        kb = _make_kb(tags=[{"tag": "stale-tag", "fact_count": 0}])
        result = await kb.cleanup(remove_orphaned_tags=True, dry_run=True)

        assert result["issues_found"]["orphaned_tags"] == 1
        assert "stale-tag" in result["issues_details"]["orphaned_tag_names"]

    @pytest.mark.asyncio
    async def test_detects_malformed_metadata(self):
        kb = _make_kb(
            facts=[{"key": "fact:xyz", "content": "hello", "metadata_raw": "not-json!!"}]
        )
        result = await kb.cleanup(fix_metadata=True, dry_run=True)

        assert result["issues_found"]["malformed_metadata"] == 1
        assert "xyz" in result["issues_details"]["malformed_fact_ids"]

    @pytest.mark.asyncio
    async def test_dry_run_does_not_mutate(self):
        kb = _make_kb(
            facts=[{"key": "fact:e1", "content": "", "metadata_raw": "bad"}],
            tags=[{"tag": "ghost", "fact_count": 0}],
        )
        await kb.cleanup(remove_empty=True, remove_orphaned_tags=True, fix_metadata=True, dry_run=True)

        assert kb._deleted == []
        assert kb._updated == []
        assert kb._tags_deleted == []

    @pytest.mark.asyncio
    async def test_accepts_all_endpoint_kwargs_no_type_error(self):
        """Regression: the old signature raised TypeError on these kwargs."""
        kb = _make_kb()
        # Must not raise — this is the exact call the endpoint makes
        result = await kb.cleanup(
            remove_empty=True,
            remove_orphaned_tags=True,
            fix_metadata=True,
            dry_run=True,
        )
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Tests — dry_run=False (apply fixes)
# ---------------------------------------------------------------------------


class TestCleanupApplyFixes:
    @pytest.mark.asyncio
    async def test_removes_empty_facts(self):
        kb = _make_kb(facts=[{"key": "fact:empty1", "content": "", "metadata_raw": "{}"}])
        result = await kb.cleanup(remove_empty=True, dry_run=False)

        assert "empty1" in kb._deleted
        assert result["fixes_applied"]["empty_facts_removed"] == 1
        assert result["issues_details"] is None

    @pytest.mark.asyncio
    async def test_removes_orphaned_tags(self):
        kb = _make_kb(tags=[{"tag": "dead-tag", "fact_count": 0}])
        result = await kb.cleanup(remove_orphaned_tags=True, dry_run=False)

        assert "dead-tag" in kb._tags_deleted
        assert result["fixes_applied"]["orphaned_tags_removed"] == 1

    @pytest.mark.asyncio
    async def test_fixes_malformed_metadata(self):
        kb = _make_kb(
            facts=[{"key": "fact:bad-meta", "content": "some content", "metadata_raw": "{bad json"}]
        )
        result = await kb.cleanup(fix_metadata=True, dry_run=False)

        assert any(fid == "bad-meta" for fid, _ in kb._updated)
        assert result["fixes_applied"]["metadata_fixed"] == 1

    @pytest.mark.asyncio
    async def test_valid_metadata_not_touched(self):
        kb = _make_kb(
            facts=[{"key": "fact:ok", "content": "content", "metadata_raw": json.dumps({"k": "v"})}]
        )
        result = await kb.cleanup(fix_metadata=True, dry_run=False)

        assert kb._updated == []
        assert result["fixes_applied"]["metadata_fixed"] == 0
