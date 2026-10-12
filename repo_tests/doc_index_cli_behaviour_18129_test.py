# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the retired indexers' scoping flags DO on the one CLI, not just that they parse (#18129)."""

import asyncio
import importlib.util
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from repo_tests._paths import repo_root


def _cli():
    path = repo_root() / "tools" / "index_documentation.py"
    spec = importlib.util.spec_from_file_location("index_documentation_18129_behaviour", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._install_import_paths()
    return module


def _service(monkeypatch) -> MagicMock:
    from services.knowledge import doc_indexer
    from services.knowledge.doc_indexer import IndexResult

    service = MagicMock()
    service.plan.return_value = [("docs/api/a.md", 1), ("docs/api/b.md", 2)]
    service.resolve_tier.return_value = 3
    service.index_all = AsyncMock(return_value=IndexResult(success=2, total_files=2, elapsed_seconds=0.5))
    service.index_file = AsyncMock(return_value=IndexResult(success=1, total_files=1))
    service.initialize = AsyncMock(return_value=True)
    service.get_stats = AsyncMock(return_value={"status": "ok", "count": 7})
    rank = SimpleNamespace(hybrid_score=0.9, source_path="docs/api/a.md", content="hit body")
    service.search = AsyncMock(return_value=[rank])
    monkeypatch.setattr(doc_indexer, "get_doc_indexer_service", lambda *a, **k: service)
    return service


def _run(cli, argv: list[str]) -> int:
    args = cli.parse_args(argv)
    return asyncio.run(cli.run_index(force=args.force, rebuild=args.rebuild, args=args))


def test_dry_run_lists_the_plan_and_changes_nothing(monkeypatch) -> None:
    cli = _cli()
    service = _service(monkeypatch)
    assert _run(cli, ["--dry-run", "--tier", "1", "--category", "api"]) == 0
    service.plan.assert_called_once_with(force=False, tier=1, category="api")
    service.index_all.assert_not_called()
    service.index_file.assert_not_called()


def test_output_writes_the_result_as_json(monkeypatch, tmp_path) -> None:
    cli = _cli()
    service = _service(monkeypatch)
    out = tmp_path / "result.json"
    assert _run(cli, ["--full", "--output", str(out)]) == 0
    service.index_all.assert_awaited_once_with(force=True, tier=None, category=None)
    written = json.loads(out.read_text(encoding="utf-8"))
    assert (written["success"], written["total_files"]) == (2, 2)


def test_search_queries_the_collection_and_indexes_nothing(monkeypatch) -> None:
    cli = _cli()
    service = _service(monkeypatch)
    assert _run(cli, ["--search", "deploy", "--results", "3"]) == 0
    service.search.assert_awaited_once_with("deploy", n_results=3)
    service.index_all.assert_not_called()


def test_stats_reads_the_collection_and_indexes_nothing(monkeypatch) -> None:
    cli = _cli()
    service = _service(monkeypatch)
    assert _run(cli, ["--stats"]) == 0
    service.get_stats.assert_awaited_once()
    service.search.assert_not_called()
    service.index_all.assert_not_called()


@pytest.mark.parametrize("flags", [["--file", "CLAUDE.md"], ["--tier", "2", "--category", "api"]])
def test_scoping_flags_reach_the_service(monkeypatch, flags: list[str]) -> None:
    cli = _cli()
    service = _service(monkeypatch)
    assert _run(cli, flags) == 0
    if "--file" in flags:
        assert service.index_file.await_args.kwargs == {"tier": 3, "force": False}
    else:
        service.index_all.assert_awaited_once_with(force=False, tier=2, category="api")
