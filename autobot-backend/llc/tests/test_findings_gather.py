# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for llc.services.findings_gather (#11271).

Patch strategy
--------------
``gather_findings`` lazy-imports two helpers inside private async wrappers:
  - ``api.codebase_analytics.source_storage.get_source``
  - ``api.codebase_analytics.endpoints.stats._fetch_problems_from_chromadb``
  - ``api.codebase_analytics.storage.get_code_collection``

The llc/tests/conftest.py ``_shield_codebase_analytics_package`` hook already installs
a thin package stub whose ``__path__`` points at the real directory, so
``patch("api.codebase_analytics.source_storage.get_source", ...)`` loads the
real submodule (without __init__.py) and auto-restores on exit.

For the ChromaDB helpers we patch at their real module paths:
  - ``api.codebase_analytics.storage.get_code_collection``
  - ``api.codebase_analytics.endpoints.stats._fetch_problems_from_chromadb``
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_HIGH = {
    "type": "bug",
    "severity": "high",
    "file_path": "a.py",
    "line_number": 1,
    "description": "d1",
    "suggestion": "s1",
}
_MEDIUM = {
    "type": "style",
    "severity": "medium",
    "file_path": "b.py",
    "line_number": 2,
    "description": "d2",
    "suggestion": "s2",
}
_LOW = {
    "type": "smell",
    "severity": "low",
    "file_path": "c.py",
    "line_number": 3,
    "description": "d3",
    "suggestion": "s3",
}

_THREE_FINDINGS = [_HIGH, _MEDIUM, _LOW]


def _ready_source(source_id: str = "src-abc") -> SimpleNamespace:
    return SimpleNamespace(id=source_id, clone_path="/opt/autobot/code-sources/src-abc/", status="ready")


def _project(code_source_id: str | None = "src-abc") -> SimpleNamespace:
    return SimpleNamespace(id="proj-1", code_source_id=code_source_id)


_FAKE_COLLECTION = MagicMock()


def _patch_all(source, findings):
    """Context-manager stack: patch get_source, get_code_collection, _fetch_problems_from_chromadb."""
    return (
        patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=source)),
        patch("api.codebase_analytics.storage.get_code_collection", return_value=_FAKE_COLLECTION),
        patch("api.codebase_analytics.endpoints.stats._fetch_problems_from_chromadb", return_value=findings),
    )


# ---------------------------------------------------------------------------
# Tests — severity filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_min_severity_medium_drops_low():
    """min_severity='medium' → only high + medium returned (2 findings)."""
    from llc.services.findings_gather import gather_findings

    p1, p2, p3 = _patch_all(_ready_source(), _THREE_FINDINGS)
    with p1, p2, p3:
        result = await gather_findings(_project(), min_severity="medium", session=AsyncMock())

    severities = [f["severity"] for f in result]
    assert "low" not in severities
    assert len(result) == 2


@pytest.mark.asyncio
async def test_min_severity_low_returns_all():
    """min_severity='low' → all 3 findings returned."""
    from llc.services.findings_gather import gather_findings

    p1, p2, p3 = _patch_all(_ready_source(), _THREE_FINDINGS)
    with p1, p2, p3:
        result = await gather_findings(_project(), min_severity="low", session=AsyncMock())

    assert len(result) == 3


@pytest.mark.asyncio
async def test_min_severity_high_returns_only_high():
    """min_severity='high' → only high finding returned."""
    from llc.services.findings_gather import gather_findings

    p1, p2, p3 = _patch_all(_ready_source(), _THREE_FINDINGS)
    with p1, p2, p3:
        result = await gather_findings(_project(), min_severity="high", session=AsyncMock())

    assert len(result) == 1
    assert result[0]["severity"] == "high"


@pytest.mark.asyncio
async def test_results_sorted_high_before_medium():
    """Results are ordered high → medium → low."""
    from llc.services.findings_gather import gather_findings

    shuffled = [_LOW, _HIGH, _MEDIUM]
    p1, p2, p3 = _patch_all(_ready_source(), shuffled)
    with p1, p2, p3:
        result = await gather_findings(_project(), min_severity="low", session=AsyncMock())

    assert [f["severity"] for f in result] == ["high", "medium", "low"]


# ---------------------------------------------------------------------------
# Tests — ValueError cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_code_source_id_raises():
    """project.code_source_id is None → ValueError."""
    from llc.services.findings_gather import gather_findings

    with pytest.raises(ValueError, match="no code_source_id"):
        await gather_findings(_project(code_source_id=None), min_severity="medium", session=AsyncMock())


@pytest.mark.asyncio
async def test_missing_source_raises():
    """get_source returns None → ValueError."""
    from llc.services.findings_gather import gather_findings

    with patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=None)):
        with pytest.raises(ValueError, match="not found"):
            await gather_findings(_project(), min_severity="medium", session=AsyncMock())


@pytest.mark.asyncio
async def test_source_not_ready_raises():
    """Source with status != ready → ValueError."""
    from llc.services.findings_gather import gather_findings

    not_ready = SimpleNamespace(id="src-abc", clone_path="/x/", status="configured")
    with patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=not_ready)):
        with pytest.raises(ValueError, match="not ready"):
            await gather_findings(_project(), min_severity="medium", session=AsyncMock())


# ---------------------------------------------------------------------------
# Tests — helper unit
# ---------------------------------------------------------------------------


def test_at_or_above_medium():
    from llc.services.findings_gather import _at_or_above

    assert _at_or_above("medium") == ("high", "medium")


def test_at_or_above_low():
    from llc.services.findings_gather import _at_or_above

    assert _at_or_above("low") == ("high", "medium", "low")


def test_at_or_above_high():
    from llc.services.findings_gather import _at_or_above

    assert _at_or_above("high") == ("high",)
