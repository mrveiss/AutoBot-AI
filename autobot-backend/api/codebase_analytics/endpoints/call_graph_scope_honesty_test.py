# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #13468: call-graph endpoint must report the scope it actually scanned.

Previously ``_analyze_python_files`` hardcoded ``python_files[:300]`` with no
comment, no config, and no acknowledgement in the response -- a 3,541-file
backend was silently sampled at 8% and every ``summary`` statistic
(``resolution_rate``, ``total_functions``, orphan counts, top callers/callees)
was reported as if it described the whole codebase.

These tests pin:
- ``AUTOBOT_CALL_GRAPH_MAX_FILES`` resolution (default unlimited, validated
  override), mirroring the established ``chat_history/cache_test.py`` pattern
  for env-var-driven module constants.
- ``get_call_graph``'s response states ``files_scanned``/``files_total``/
  ``truncated`` for whatever scope it actually analysed.
- ``_build_call_graph_response`` discloses truncation of the node/edge/
  orphan slices (still capped at 500/2000/500 for response size) via
  matching ``*_total``/``*_truncated`` fields instead of silently dropping
  entries.
"""

import importlib
import json
import logging
import os
from unittest.mock import AsyncMock

import pytest

from autobot_shared.ssot_config import config


def _reload_call_graph_with_env(env_value):
    """Reload call_graph with a given AUTOBOT_CALL_GRAPH_MAX_FILES value (None = unset)."""
    if env_value is None:
        os.environ.pop("AUTOBOT_CALL_GRAPH_MAX_FILES", None)
    else:
        config.misc.call_graph_max_files = env_value
    import api.codebase_analytics.endpoints.call_graph as call_graph_mod

    importlib.reload(call_graph_mod)
    return call_graph_mod


@pytest.fixture(autouse=True)
def _restore_env():
    saved = config.misc.call_graph_max_files
    yield
    if not saved:
        os.environ.pop("AUTOBOT_CALL_GRAPH_MAX_FILES", None)
    else:
        config.misc.call_graph_max_files = saved
    import api.codebase_analytics.endpoints.call_graph as call_graph_mod

    importlib.reload(call_graph_mod)


class TestResolveCallGraphMaxFiles:
    """Unit tests for the env-var-driven cap resolution."""

    def test_default_is_unlimited(self):
        mod = _reload_call_graph_with_env(None)
        assert mod.CALL_GRAPH_MAX_FILES is None

    def test_env_var_override_accepts_positive_int(self):
        mod = _reload_call_graph_with_env("42")
        assert mod.CALL_GRAPH_MAX_FILES == 42

    def test_env_var_non_integer_falls_back_to_unlimited_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="api.codebase_analytics.endpoints.call_graph"):
            mod = _reload_call_graph_with_env("not-a-number")
        assert mod.CALL_GRAPH_MAX_FILES is None
        assert any("not an integer" in r.getMessage() for r in caplog.records)

    def test_env_var_zero_or_negative_falls_back_to_unlimited_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="api.codebase_analytics.endpoints.call_graph"):
            mod = _reload_call_graph_with_env("0")
        assert mod.CALL_GRAPH_MAX_FILES is None
        assert any("must be positive" in r.getMessage() for r in caplog.records)


def _write_fixture_tree(root, count: int) -> None:
    for i in range(count):
        (root / f"mod_{i}.py").write_text(f"def fn_{i}():\n    return {i}\n", encoding="utf-8")


class TestCallGraphResponseScopeHonesty:
    """End-to-end: the response must state exactly what it scanned."""

    async def test_unlimited_default_scans_every_file(self, tmp_path, monkeypatch):
        from api.codebase_analytics.endpoints import call_graph, shared

        root = tmp_path / "proj"
        root.mkdir()
        _write_fixture_tree(root, 5)

        monkeypatch.setattr(shared, "resolve_source_root", AsyncMock(return_value=root))
        monkeypatch.setattr(call_graph, "CALL_GRAPH_MAX_FILES", None)

        resp = await call_graph.get_call_graph(refresh=True, source_id="demo")
        summary = json.loads(resp.body)["summary"]

        assert summary["files_scanned"] == 5
        assert summary["files_total"] == 5
        assert summary["truncated"] is False

    async def test_capped_scan_reports_truncation(self, tmp_path, monkeypatch):
        from api.codebase_analytics.endpoints import call_graph, shared

        root = tmp_path / "proj"
        root.mkdir()
        _write_fixture_tree(root, 5)

        monkeypatch.setattr(shared, "resolve_source_root", AsyncMock(return_value=root))
        monkeypatch.setattr(call_graph, "CALL_GRAPH_MAX_FILES", 2)

        resp = await call_graph.get_call_graph(refresh=True, source_id="demo")
        summary = json.loads(resp.body)["summary"]

        # Every other summary statistic must describe files_scanned, not files_total.
        assert summary["files_scanned"] == 2
        assert summary["files_total"] == 5
        assert summary["truncated"] is True
        assert summary["total_functions"] == 2


class TestBuildCallGraphResponseSliceHonesty:
    """Unit tests for the node/edge/orphan slice truncation metadata."""

    def test_small_result_reports_no_slice_truncation(self):
        from api.codebase_analytics.endpoints.call_graph import _build_call_graph_response

        functions = {"a": {}, "b": {}}
        nodes = [{"id": "a"}, {"id": "b"}]
        data = _build_call_graph_response(functions, nodes, [], [], [], [], files_scanned=1, files_total=1)

        assert data["call_graph"]["nodes_total"] == 2
        assert data["call_graph"]["nodes_truncated"] is False
        assert data["call_graph"]["edges_truncated"] is False
        assert data["orphaned_functions_truncated"] is False

    def test_oversized_result_reports_slice_truncation(self):
        from api.codebase_analytics.endpoints.call_graph import _build_call_graph_response

        nodes = [{"id": str(i)} for i in range(600)]
        edges = [{"from": "a", "to": "b", "to_name": "b", "resolved": True} for _ in range(2500)]
        orphans = [{"id": str(i)} for i in range(501)]
        data = _build_call_graph_response({}, nodes, orphans, edges, [], [], files_scanned=1, files_total=1)

        assert data["call_graph"]["nodes_total"] == 600
        assert len(data["call_graph"]["nodes"]) == 500
        assert data["call_graph"]["nodes_truncated"] is True
        assert data["call_graph"]["edges_total"] == 2500
        assert len(data["call_graph"]["edges"]) == 2000
        assert data["call_graph"]["edges_truncated"] is True
        assert data["orphaned_functions_total"] == 501
        assert data["orphaned_functions_truncated"] is True
