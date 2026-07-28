# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /security/score must not scan in the request (#12866).

The endpoint ran ``SecurityAnalyzer.analyze_directory()`` via
``asyncio.to_thread``. That looks non-blocking but is not: the scan is pure
Python and GIL-bound, so the worker thread holds the GIL for its whole
duration and starves the event loop. Every other request on the worker stalls
with it — which is what pushed ``/service-monitor/vms/status`` past the GUI's
5s probe budget (p90 12s, 27.5% of polls) and made a backend with zero
restarts report itself "Unreachable".

The Celery path for this exact work already existed. These tests pin that the
endpoint serves the cached result and enqueues a refresh, and never analyses
inline again.
"""

import ast
from pathlib import Path

import pytest

_SOURCE = Path(__file__).resolve().parent / "code_intelligence.py"


def _endpoint_source() -> str:
    """Source text of get_security_score, isolated from its neighbours."""
    tree = ast.parse(_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_security_score":
            return ast.get_source_segment(_SOURCE.read_text(encoding="utf-8"), node) or ""
    raise AssertionError("get_security_score not found — was it renamed?")


def _called_names(source: str) -> set[str]:
    """Every function/method/attribute actually *called* in *source*."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            names.add(getattr(func, "attr", None) or getattr(func, "id", "") or "")
    return names


class TestNoInlineScan:
    """The regression guard: the scan must not come back into the request path."""

    def test_endpoint_does_not_call_the_analyzer_inline(self):
        """Asserted on the AST, not the text: the comment explaining *why* the
        scan was removed necessarily names it, and a substring check would trip
        on its own rationale."""
        called = _called_names(_endpoint_source())

        assert "analyze_directory" not in called, "the GIL-bound scan is back in the request path"
        assert "SecurityAnalyzer" not in called, "the analyzer must not be constructed per request"

    def test_endpoint_enqueues_the_existing_celery_task(self):
        """Reuses run_security_analysis rather than introducing a second path."""
        source = _endpoint_source()

        assert "run_security_analysis.delay" in source

    def test_endpoint_serves_the_cached_result_first(self):
        """A completed scan must answer immediately; only a miss enqueues."""
        source = _endpoint_source()

        cache_read = source.index("get_latest_task_result")
        enqueue = source.index("run_security_analysis.delay")
        assert cache_read < enqueue, "cache must be consulted before enqueueing"

    def test_queued_task_id_is_recorded_for_later_lookup(self):
        """Without this the result is orphaned — nothing can find it again."""
        assert "store_latest_task_id" in _endpoint_source()


class TestResponseContract:
    """Callers must not have to change — the shape is the same either way."""

    def test_cached_response_keeps_the_success_status(self):
        """useCodeIntelScores maps on `status === 'success'`; anything else is dropped."""
        source = _endpoint_source()

        assert '"status": "success"' in source
        assert '"from_cache": True' in source

    def test_cache_miss_reports_pending_not_a_fabricated_score(self):
        """A zero score would read as 'perfectly insecure', not 'not yet known'."""
        source = _endpoint_source()

        assert '"status": "pending"' in source
        assert '"task_id"' in source

    @pytest.mark.parametrize("field", ["completed_at", "path"])
    def test_cached_response_carries_provenance(self, field):
        """The GUI shows results as-of a time; both halves need it."""
        assert f'"{field}"' in _endpoint_source()
