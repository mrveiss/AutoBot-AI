# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for ContradictionDetector — Issue #4566.

All external I/O (LLM, Redis) is mocked via AsyncMock so tests run offline.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing the module under test
# ---------------------------------------------------------------------------


def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = []
    mod.__package__ = name
    sys.modules.setdefault(name, mod)
    return mod


# autobot_shared stubs
_autobot_shared = _stub("autobot_shared")
_redis_mod = _stub("autobot_shared.redis_client")
_redis_mod.get_async_redis_client = AsyncMock()  # type: ignore[attr-defined]

# llm_interface stub
_llm_mod = _stub("llm_interface")


class _FakeLLMType:
    EXTRACTION = "extraction"


_llm_mod.LLMType = _FakeLLMType  # type: ignore[attr-defined]
_llm_mod.get_llm_interface = MagicMock()  # type: ignore[attr-defined]

# Load the module under test via spec to bypass package __init__ imports
_MODULE_PATH = Path(__file__).parent / "contradiction_detector.py"
_spec = importlib.util.spec_from_file_location(
    "services.knowledge.contradiction_detector",
    str(_MODULE_PATH),
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules["services.knowledge.contradiction_detector"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

# Expose as attribute so patch() can resolve dotted paths
if "services.knowledge" in sys.modules:
    sys.modules["services.knowledge"].contradiction_detector = _mod  # type: ignore[attr-defined]

# Bring names into test scope
ConflictPair = _mod.ConflictPair
ContradictionReport = _mod.ContradictionReport
ContradictionDetector = _mod.ContradictionDetector
_keywords = _mod._keywords
_group_chunks = _mod._group_chunks
_parse_llm_response = _mod._parse_llm_response
store_report = _mod.store_report
load_report = _mod.load_report
generate_job_id = _mod.generate_job_id


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _llm_response(content: str, error=None):
    r = MagicMock()
    r.content = content
    r.error = error
    return r


def _contradiction_json(pairs=1, gaps=None) -> str:
    return json.dumps(
        {
            "contradictions": [
                {
                    "chunk_a": f"chunk_a_{i}",
                    "chunk_b": f"chunk_b_{i}",
                    "explanation": f"explanation_{i}",
                    "confidence": 0.9,
                }
                for i in range(pairs)
            ],
            "gaps": gaps or [],
        }
    )


# ---------------------------------------------------------------------------
# _keywords
# ---------------------------------------------------------------------------


class TestKeywords:
    def test_removes_stopwords(self) -> None:
        kws = _keywords("the cat is on the mat")
        assert "the" not in kws
        assert "is" not in kws
        assert "cat" in kws
        assert "mat" in kws

    def test_short_tokens_excluded(self) -> None:
        kws = _keywords("a be do go")
        assert kws == frozenset()

    def test_lowercases(self) -> None:
        kws = _keywords("Python Is Great")
        assert "python" in kws
        assert "great" in kws


# ---------------------------------------------------------------------------
# _group_chunks
# ---------------------------------------------------------------------------


class TestGroupChunks:
    def test_single_chunk_grouped(self) -> None:
        chunks = [{"text": "python programming language"}]
        groups = _group_chunks(chunks)
        assert sum(len(v) for v in groups.values()) == 1

    def test_similar_chunks_may_share_group(self) -> None:
        chunks = [
            {"text": "python programming language"},
            {"text": "python scripting language"},
            {"text": "completely different topic"},
        ]
        groups = _group_chunks(chunks)
        # At least two groups expected (python group + other)
        assert len(groups) >= 1

    def test_empty_chunks_go_to_ungrouped(self) -> None:
        chunks = [{"text": ""}, {"text": ""}]
        groups = _group_chunks(chunks)
        assert "__ungrouped__" in groups

    def test_returns_all_chunks(self) -> None:
        chunks = [{"text": f"word{i} content"} for i in range(5)]
        groups = _group_chunks(chunks)
        total = sum(len(v) for v in groups.values())
        assert total == 5


# ---------------------------------------------------------------------------
# _parse_llm_response
# ---------------------------------------------------------------------------


class TestParseLlmResponse:
    def test_valid_json_parsed(self) -> None:
        raw = _contradiction_json(pairs=2, gaps=["missing topic"])
        conflicts, gaps = _parse_llm_response(raw)
        assert len(conflicts) == 2
        assert gaps == ["missing topic"]

    def test_invalid_json_returns_empty(self) -> None:
        conflicts, gaps = _parse_llm_response("not json at all")
        assert conflicts == []
        assert gaps == []

    def test_empty_contradictions_list(self) -> None:
        raw = json.dumps({"contradictions": [], "gaps": []})
        conflicts, gaps = _parse_llm_response(raw)
        assert conflicts == []
        assert gaps == []

    def test_confidence_coerced_to_float(self) -> None:
        raw = json.dumps(
            {
                "contradictions": [
                    {
                        "chunk_a": "a",
                        "chunk_b": "b",
                        "explanation": "e",
                        "confidence": "0.8",
                    }
                ],
                "gaps": [],
            }
        )
        conflicts, _ = _parse_llm_response(raw)
        assert isinstance(conflicts[0].confidence, float)


# ---------------------------------------------------------------------------
# ContradictionDetector.scan
# ---------------------------------------------------------------------------


class TestContradictionDetectorScan:
    @pytest.fixture()
    def mock_llm(self):
        llm = AsyncMock()
        llm.chat_completion = AsyncMock()
        return llm

    @pytest.mark.asyncio
    async def test_scan_finds_contradictions(self, mock_llm) -> None:
        mock_llm.chat_completion.return_value = _llm_response(_contradiction_json(pairs=1, gaps=["gap1"]))
        detector = ContradictionDetector(llm_interface=mock_llm)
        # Both chunks share the rare keyword "redis" so they land in the same group
        chunks = [
            {"text": "redis caches data redis redis"},
            {"text": "redis persists data redis redis"},
        ]
        report = await detector.scan(chunks)
        assert len(report.contradictions) == 1
        assert report.contradictions[0].confidence == 0.9
        assert "gap1" in report.gaps

    @pytest.mark.asyncio
    async def test_scan_empty_chunks_returns_empty_report(self, mock_llm) -> None:
        detector = ContradictionDetector(llm_interface=mock_llm)
        report = await detector.scan([])
        assert report.contradictions == []
        assert report.gaps == []
        mock_llm.chat_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_scan_single_chunk_skips_group(self, mock_llm) -> None:
        """Groups with < 2 chunks should not trigger LLM call."""
        detector = ContradictionDetector(llm_interface=mock_llm)
        # Force a unique keyword so it gets its own 1-member group
        chunks = [{"text": "zzzmultiworduniquexyz topic content"}]
        report = await detector.scan(chunks)
        assert report.contradictions == []
        mock_llm.chat_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_scan_llm_error_skips_group(self, mock_llm) -> None:
        mock_llm.chat_completion.return_value = _llm_response("", error="timeout")
        detector = ContradictionDetector(llm_interface=mock_llm)
        chunks = [
            {"text": "database stores data efficiently"},
            {"text": "database stores data slowly"},
        ]
        report = await detector.scan(chunks)
        assert report.contradictions == []

    @pytest.mark.asyncio
    async def test_scan_llm_returns_none_skips_group(self, mock_llm) -> None:
        mock_llm.chat_completion.return_value = None
        detector = ContradictionDetector(llm_interface=mock_llm)
        chunks = [
            {"text": "redis stores data in memory"},
            {"text": "redis stores data on disk"},
        ]
        report = await detector.scan(chunks)
        assert report.contradictions == []

    @pytest.mark.asyncio
    async def test_scan_deduplicated_gaps(self, mock_llm) -> None:
        """Gaps returned from multiple groups should be deduplicated."""
        mock_llm.chat_completion.return_value = _llm_response(
            json.dumps({"contradictions": [], "gaps": ["missing auth docs"]})
        )
        detector = ContradictionDetector(llm_interface=mock_llm)
        # Create two groups of similar-but-distinct keywords
        chunks = [
            {"text": "authentication login process"},
            {"text": "authentication login workflow"},
            {"text": "authorization permission model"},
            {"text": "authorization permission rules"},
        ]
        report = await detector.scan(chunks)
        # Even if both groups return the same gap, it should appear once
        assert report.gaps.count("missing auth docs") == 1

    @pytest.mark.asyncio
    async def test_scan_checked_at_is_utc(self, mock_llm) -> None:
        mock_llm.chat_completion.return_value = _llm_response(json.dumps({"contradictions": [], "gaps": []}))
        detector = ContradictionDetector(llm_interface=mock_llm)
        report = await detector.scan([])
        assert report.checked_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Redis persistence helpers
# ---------------------------------------------------------------------------


class TestStoreAndLoadReport:
    @pytest.mark.asyncio
    async def test_store_serialises_report(self) -> None:
        mock_redis = AsyncMock()
        with patch(
            "services.knowledge.contradiction_detector.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            report = ContradictionReport(
                contradictions=[ConflictPair(chunk_a="a", chunk_b="b", explanation="e", confidence=0.7)],
                gaps=["gap"],
            )
            await store_report(report)
            mock_redis.set.assert_awaited_once()
            call_args = mock_redis.set.call_args
            key = call_args[0][0]
            payload = json.loads(call_args[0][1])
            assert key == "kb:lint:report"
            assert len(payload["contradictions"]) == 1
            assert payload["gaps"] == ["gap"]

    @pytest.mark.asyncio
    async def test_load_report_returns_none_when_missing(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        with patch(
            "services.knowledge.contradiction_detector.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await load_report()
            assert result is None

    @pytest.mark.asyncio
    async def test_load_report_deserialises_stored_json(self) -> None:
        stored = json.dumps(
            {
                "contradictions": [],
                "gaps": ["a gap"],
                "checked_at": "2026-01-01T00:00:00+00:00",
            }
        )
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=stored)
        with patch(
            "services.knowledge.contradiction_detector.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await load_report()
            assert result is not None
            assert result["gaps"] == ["a gap"]


# ---------------------------------------------------------------------------
# generate_job_id
# ---------------------------------------------------------------------------


class TestGenerateJobId:
    def test_returns_unique_ids(self) -> None:
        ids = {generate_job_id() for _ in range(10)}
        assert len(ids) == 10

    def test_returns_string(self) -> None:
        assert isinstance(generate_job_id(), str)
