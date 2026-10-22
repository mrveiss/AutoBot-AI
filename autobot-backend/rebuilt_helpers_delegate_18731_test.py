# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Rebuilt helpers reach the one implementation they were merged into (#18731).

Each test patches the KEPT implementation and calls the OLD entry point, so a
regression back to a private copy fails (the patched kept function is never hit).
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.ssot_config import config as ssot_config


def test_network_constants_websocket_url_delegates_to_ssot_config(monkeypatch):
    import autobot_shared.ssot_config as ssot_module
    from constants.network_constants import NetworkConstants

    monkeypatch.setattr(ssot_module, "config", SimpleNamespace(websocket_url="ws://kept.example/api/ws"))
    assert NetworkConstants.get_websocket_url() == "ws://kept.example/api/ws"


def test_frontend_config_reads_the_ssot_websocket_url():
    from api import frontend_config

    assert frontend_config.ssot_config is ssot_config


@pytest.mark.asyncio
async def test_sandbox_check_permission_delegates_to_files(monkeypatch):
    from api import sandbox_files

    kept = AsyncMock(return_value={"username": "u"})
    monkeypatch.setattr(sandbox_files, "_check_file_permission", kept)
    request = object()
    assert await sandbox_files._check_permission(request, "view") == {"username": "u"}
    kept.assert_called_once_with(request, "view")


@pytest.mark.asyncio
async def test_sandbox_tree_and_stats_use_the_files_walkers(monkeypatch, tmp_path):
    from api import sandbox_files

    monkeypatch.setattr(sandbox_files, "_check_permission", AsyncMock(return_value={}))
    monkeypatch.setattr(sandbox_files, "_validate_path", lambda path: tmp_path)
    monkeypatch.setattr(sandbox_files, "SANDBOX_FILES_ROOT", tmp_path)
    tree = MagicMock(return_value=[])
    stats = MagicMock(return_value=(1, 2, 3))
    monkeypatch.setattr(sandbox_files, "build_directory_tree", tree)
    monkeypatch.setattr(sandbox_files, "collect_directory_stats", stats)

    assert (await sandbox_files.get_directory_tree(object(), ""))["tree"] == []
    tree.assert_called_once_with(tmp_path, tmp_path)
    result = await sandbox_files.get_file_stats(object())
    stats.assert_called_once_with(tmp_path)
    assert (result["total_files"], result["total_directories"], result["total_size"]) == (1, 2, 3)


def test_directory_walkers_shape(tmp_path):
    from api.files import build_directory_tree, collect_directory_stats

    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "x.PY").write_text("abc", encoding="utf-8")
    tree = build_directory_tree(tmp_path, tmp_path)
    assert tree == [
        {
            "name": "d",
            "path": "d",
            "type": "directory",
            "children": [
                {
                    "name": "x.PY",
                    "path": str(__import__("pathlib").Path("d") / "x.PY"),
                    "type": "file",
                    "size": 3,
                    "extension": ".py",
                }
            ],
        }
    ]
    assert collect_directory_stats(tmp_path) == (1, 1, 3)


@pytest.mark.asyncio
async def test_sprint_lookups_delegate_to_load_sprint(monkeypatch):
    from llc.services import agent_scorecard, sprint_planning

    sid = uuid.uuid4()
    kept = AsyncMock(return_value="sprint")
    monkeypatch.setattr(sprint_planning, "load_sprint", kept)
    monkeypatch.setattr(agent_scorecard, "load_sprint", kept)
    session = object()
    svc = object.__new__(sprint_planning.SprintPlanningService)
    card = object.__new__(agent_scorecard.AgentScorecardService)
    assert await svc._get_sprint(session, sid) == "sprint"
    assert await card._load_sprint(session, sid) == "sprint"
    assert kept.await_count == 2


@pytest.mark.asyncio
async def test_load_sprint_raises_sprint_not_found():
    from llc.services.sprint_planning import SprintNotFound, load_sprint

    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    with pytest.raises(SprintNotFound):
        await load_sprint(session, uuid.uuid4())


_CI_DIR = Path(__file__).resolve().parent / "code_intelligence"


@pytest.mark.parametrize(
    "relpath, cls_name, method",
    [
        ("anti_pattern_detection/analyzer.py", "AntiPatternSuiteAnalyzer", "_get_python_files"),
        ("fingerprinting/detector.py", "CloneDetector", "_get_python_files"),
        ("pattern_analysis/analyzer.py", "CodePatternAnalyzer", "collect_python_files"),
    ],
)
def test_python_file_collectors_delegate_to_the_shared_walk(relpath, cls_name, method):
    """Source-level: conftest stubs ``code_intelligence.*``, so the real classes cannot be imported."""
    tree = ast.parse((_CI_DIR / relpath).read_text(encoding="utf-8"))
    imports_shared = any(
        isinstance(n, ast.ImportFrom)
        and n.module == "code_intelligence.python_files"
        and any(a.name == "collect_python_files" for a in n.names)
        for n in ast.walk(tree)
    )
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == cls_name)
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method)
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "collect_python_files"]
    assert imports_shared and len(calls) == 1
    assert not any(isinstance(n, ast.Attribute) and n.attr == "rglob" for n in ast.walk(fn))


def test_shared_python_file_walk_sorts_and_excludes(tmp_path):
    from code_intelligence.python_files import collect_python_files

    (tmp_path / "skipme").mkdir()
    (tmp_path / "skipme" / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "z.py").write_text("", encoding="utf-8")
    (tmp_path / "b.py").write_text("", encoding="utf-8")
    assert collect_python_files(str(tmp_path), ["skipme"]) == [str(tmp_path / "b.py"), str(tmp_path / "z.py")]


def test_repo_sync_manifest_parse_delegates_to_the_shared_frontmatter_parser(monkeypatch):
    from skills.sync import base_sync

    kept = MagicMock(return_value={"name": "n"})
    monkeypatch.setattr(base_sync, "parse_frontmatter_mapping", kept)
    assert base_sync.BaseRepoSync._parse_skill_md("---\nname: n\n---\n") == {"name": "n"}
    kept.assert_called_once()


@pytest.mark.asyncio
async def test_status_routes_share_the_task_status_response(monkeypatch):
    from api import knowledge_claude_memory, knowledge_population
    from services.knowledge.task_status_manager import TaskStatusManager

    kept = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(TaskStatusManager, "get_task_response", kept)
    for handler in (
        knowledge_population.get_populate_status,
        knowledge_population.get_index_code_status,
        knowledge_claude_memory.get_import_claude_memory_status,
    ):
        assert await handler("t1") == {"status": "ok"}
    assert kept.await_count == 3


@pytest.mark.asyncio
async def test_task_status_response_not_found_and_found(monkeypatch):
    from services.knowledge.task_status_manager import TaskStatusManager

    monkeypatch.setattr(TaskStatusManager, "get_task", AsyncMock(return_value=None))
    assert await TaskStatusManager.get_task_response("t9") == {
        "status": "not_found",
        "message": "Task t9 not found",
        "task_id": "t9",
    }
    record = MagicMock()
    record.to_response_dict.return_value = {"task_id": "t9", "status": "running"}
    monkeypatch.setattr(TaskStatusManager, "get_task", AsyncMock(return_value=record))
    assert await TaskStatusManager.get_task_response("t9") == {"task_id": "t9", "status": "running"}


def test_chat_and_dedup_share_one_public_timestamp_parser():
    """api.chat uses the public chat_history parser; no private cross-module import (#18731 G076)."""
    from api import chat
    from chat_history import deduplication

    assert chat.parse_message_timestamp is deduplication.parse_message_timestamp
    assert not hasattr(deduplication, "_parse_timestamp")


def test_skill_manifest_parsers_are_the_one_shared_function():
    """generator and base_sync bind autobot_shared.frontmatter directly, no private alias (#18731)."""
    from autobot_shared.frontmatter import parse_frontmatter_mapping
    from skills import generator
    from skills.sync import base_sync

    assert generator.parse_frontmatter_mapping is parse_frontmatter_mapping
    assert base_sync.parse_frontmatter_mapping is parse_frontmatter_mapping
