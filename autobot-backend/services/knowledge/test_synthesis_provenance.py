# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for SynthesisProvenanceLog and /knowledge/synthesis/log endpoint.

Issue #4567: Synthesis provenance log.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.knowledge.synthesis_provenance import SynthesisProvenanceLog

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STREAM_KEY = "kb:synthesis:log"


def _make_redis_mock(xadd_result=b"1-1", xrevrange_result=None):
    """Return an async Redis mock with xadd / xrevrange stubbed.

    pipeline() returns a synchronous MagicMock whose xadd/hset are tracked
    and whose execute() is an AsyncMock (pipeline.execute is awaited).
    """
    mock = AsyncMock()
    # xrevrange is still called directly on the redis client
    mock.xrevrange = AsyncMock(return_value=xrevrange_result or [])
    # pipeline() is a sync call — return a MagicMock with async execute
    pipe_mock = MagicMock()
    pipe_mock.xadd = MagicMock(return_value=None)
    pipe_mock.hset = MagicMock(return_value=None)
    pipe_mock.execute = AsyncMock(return_value=[xadd_result, 1])
    mock.pipeline = MagicMock(return_value=pipe_mock)
    mock._pipe = pipe_mock  # expose for assertions
    return mock


def _raw_entry(fields: dict):
    """Encode a fields dict as bytes to simulate raw Redis response."""
    return (b"1-1", {k.encode(): v.encode() for k, v in fields.items()})


# ---------------------------------------------------------------------------
# log_run tests
# ---------------------------------------------------------------------------


class TestLogRun:
    """Tests for SynthesisProvenanceLog.log_run()."""

    @pytest.mark.asyncio
    async def test_xadd_called_with_correct_stream_key(self):
        """log_run writes to the kb:synthesis:log stream key."""
        mock_redis = _make_redis_mock()
        with patch(
            "services.knowledge.synthesis_provenance.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            svc = SynthesisProvenanceLog()
            await svc.log_run(
                run_id="run-1",
                source_docs=["doc-a"],
                synthesis_ids=["ins-1"],
                llm_model="gpt-4",
                prompt_template="v1",
                duration_ms=120,
            )
        mock_redis._pipe.xadd.assert_called_once()
        key_used = mock_redis._pipe.xadd.call_args[0][0]
        assert key_used == _STREAM_KEY

    @pytest.mark.asyncio
    async def test_xadd_entry_contains_run_id(self):
        """log_run payload includes run_id."""
        mock_redis = _make_redis_mock()
        with patch(
            "services.knowledge.synthesis_provenance.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            svc = SynthesisProvenanceLog()
            await svc.log_run(
                run_id="run-42",
                source_docs=[],
                synthesis_ids=[],
                llm_model="ollama",
                prompt_template="v1",
                duration_ms=0,
            )
        fields = mock_redis._pipe.xadd.call_args[0][1]
        assert fields["run_id"] == "run-42"

    @pytest.mark.asyncio
    async def test_xadd_entry_source_docs_json_encoded(self):
        """source_docs field is JSON-encoded in the stream entry."""
        mock_redis = _make_redis_mock()
        with patch(
            "services.knowledge.synthesis_provenance.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            svc = SynthesisProvenanceLog()
            await svc.log_run(
                run_id="r",
                source_docs=["doc-1", "doc-2"],
                synthesis_ids=[],
                llm_model="m",
                prompt_template="t",
                duration_ms=1,
            )
        fields = mock_redis._pipe.xadd.call_args[0][1]
        assert json.loads(fields["source_docs"]) == ["doc-1", "doc-2"]

    @pytest.mark.asyncio
    async def test_xadd_entry_synthesis_ids_json_encoded(self):
        """synthesis_ids field is JSON-encoded in the stream entry."""
        mock_redis = _make_redis_mock()
        with patch(
            "services.knowledge.synthesis_provenance.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            svc = SynthesisProvenanceLog()
            await svc.log_run(
                run_id="r",
                source_docs=[],
                synthesis_ids=["ins-a", "ins-b"],
                llm_model="m",
                prompt_template="t",
                duration_ms=1,
            )
        fields = mock_redis._pipe.xadd.call_args[0][1]
        assert json.loads(fields["synthesis_ids"]) == ["ins-a", "ins-b"]

    @pytest.mark.asyncio
    async def test_xadd_entry_duration_ms_as_string(self):
        """duration_ms stored as string (Redis requires string values)."""
        mock_redis = _make_redis_mock()
        with patch(
            "services.knowledge.synthesis_provenance.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            svc = SynthesisProvenanceLog()
            await svc.log_run(
                run_id="r",
                source_docs=[],
                synthesis_ids=[],
                llm_model="m",
                prompt_template="t",
                duration_ms=250,
            )
        fields = mock_redis._pipe.xadd.call_args[0][1]
        assert fields["duration_ms"] == "250"

    @pytest.mark.asyncio
    async def test_log_run_swallows_redis_exception(self):
        """log_run does not propagate Redis exceptions."""
        mock_redis = AsyncMock()
        pipe_mock = MagicMock()
        pipe_mock.xadd = MagicMock(return_value=None)
        pipe_mock.hset = MagicMock(return_value=None)
        pipe_mock.execute = AsyncMock(side_effect=ConnectionError("Redis down"))
        mock_redis.pipeline = MagicMock(return_value=pipe_mock)
        with patch(
            "services.knowledge.synthesis_provenance.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            svc = SynthesisProvenanceLog()
            # Must not raise
            await svc.log_run(
                run_id="r",
                source_docs=[],
                synthesis_ids=[],
                llm_model="m",
                prompt_template="t",
                duration_ms=0,
            )


# ---------------------------------------------------------------------------
# get_recent tests
# ---------------------------------------------------------------------------


class TestGetRecent:
    """Tests for SynthesisProvenanceLog.get_recent()."""

    @pytest.mark.asyncio
    async def test_xrevrange_called_with_limit(self):
        """get_recent passes count=limit to xrevrange."""
        mock_redis = _make_redis_mock()
        with patch(
            "services.knowledge.synthesis_provenance.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            svc = SynthesisProvenanceLog()
            await svc.get_recent(limit=10)
        mock_redis.xrevrange.assert_called_once_with(_STREAM_KEY, count=10)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_entries(self):
        """get_recent returns [] when the stream is empty."""
        mock_redis = _make_redis_mock(xrevrange_result=[])
        with patch(
            "services.knowledge.synthesis_provenance.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            svc = SynthesisProvenanceLog()
            result = await svc.get_recent()
        assert result == []

    @pytest.mark.asyncio
    async def test_deserializes_source_docs(self):
        """get_recent decodes JSON-encoded source_docs list."""
        raw = [
            _raw_entry(
                {
                    "run_id": "r1",
                    "source_docs": '["doc-a"]',
                    "synthesis_ids": "[]",
                    "llm_model": "gpt-4",
                    "prompt_template": "v1",
                    "ran_at": "2026-01-01T00:00:00+00:00",
                    "duration_ms": "100",
                }
            )
        ]
        mock_redis = _make_redis_mock(xrevrange_result=raw)
        with patch(
            "services.knowledge.synthesis_provenance.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            svc = SynthesisProvenanceLog()
            result = await svc.get_recent()
        assert result[0]["source_docs"] == ["doc-a"]

    @pytest.mark.asyncio
    async def test_deserializes_synthesis_ids(self):
        """get_recent decodes JSON-encoded synthesis_ids list."""
        raw = [
            _raw_entry(
                {
                    "run_id": "r1",
                    "source_docs": "[]",
                    "synthesis_ids": '["ins-1","ins-2"]',
                    "llm_model": "m",
                    "prompt_template": "t",
                    "ran_at": "2026-01-01T00:00:00+00:00",
                    "duration_ms": "50",
                }
            )
        ]
        mock_redis = _make_redis_mock(xrevrange_result=raw)
        with patch(
            "services.knowledge.synthesis_provenance.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            svc = SynthesisProvenanceLog()
            result = await svc.get_recent()
        assert result[0]["synthesis_ids"] == ["ins-1", "ins-2"]

    @pytest.mark.asyncio
    async def test_duration_ms_cast_to_int(self):
        """get_recent casts duration_ms string to int."""
        raw = [
            _raw_entry(
                {
                    "run_id": "r",
                    "source_docs": "[]",
                    "synthesis_ids": "[]",
                    "llm_model": "m",
                    "prompt_template": "t",
                    "ran_at": "2026-01-01T00:00:00+00:00",
                    "duration_ms": "999",
                }
            )
        ]
        mock_redis = _make_redis_mock(xrevrange_result=raw)
        with patch(
            "services.knowledge.synthesis_provenance.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            svc = SynthesisProvenanceLog()
            result = await svc.get_recent()
        assert result[0]["duration_ms"] == 999
        assert isinstance(result[0]["duration_ms"], int)

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_redis_error(self):
        """get_recent returns [] when Redis raises an exception."""
        mock_redis = AsyncMock()
        mock_redis.xrevrange = AsyncMock(side_effect=ConnectionError("Redis down"))
        with patch(
            "services.knowledge.synthesis_provenance.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            svc = SynthesisProvenanceLog()
            result = await svc.get_recent()
        assert result == []


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestSynthesisLogEndpoint:
    """Tests for GET /knowledge/synthesis/log endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_returns_200(self):
        """GET /synthesis/log returns HTTP 200."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.knowledge_maintenance import router

        app = FastAPI()
        app.include_router(router, prefix="/knowledge")

        mock_entries = [{"run_id": "r1", "llm_model": "gpt-4"}]
        with patch(
            "api.knowledge_maintenance._provenance_log.get_recent",
            new=AsyncMock(return_value=mock_entries),
        ):
            client = TestClient(app)
            response = client.get("/knowledge/synthesis/log")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_endpoint_returns_entries_and_count(self):
        """Response body contains 'entries' and 'count' keys."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.knowledge_maintenance import router

        app = FastAPI()
        app.include_router(router, prefix="/knowledge")

        mock_entries = [{"run_id": "r1"}, {"run_id": "r2"}]
        with patch(
            "api.knowledge_maintenance._provenance_log.get_recent",
            new=AsyncMock(return_value=mock_entries),
        ):
            client = TestClient(app)
            response = client.get("/knowledge/synthesis/log")

        body = response.json()
        assert "entries" in body
        assert body["count"] == 2

    @pytest.mark.asyncio
    async def test_endpoint_respects_limit_param(self):
        """get_recent is called with the limit query parameter."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.knowledge_maintenance import router

        app = FastAPI()
        app.include_router(router, prefix="/knowledge")

        mock_get_recent = AsyncMock(return_value=[])
        with patch(
            "api.knowledge_maintenance._provenance_log.get_recent",
            new=mock_get_recent,
        ):
            client = TestClient(app)
            client.get("/knowledge/synthesis/log?limit=25")
            mock_get_recent.assert_called_once_with(limit=25)
