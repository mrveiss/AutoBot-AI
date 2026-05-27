# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
"""
Unit tests for the belief state prototype (MVA-1407).

Covers:
  - Assertion dataclasses
  - TaskContext.assertions / contradictions fields
  - BeliefStateUpdater: insert / reconfirm / contradiction
  - ReadFileExtractor
  - RunCommandExtractor (exit code + port detection)
  - WebSearchExtractor
  - AgentLoopConfig.belief_state_enabled flag
"""

import hashlib
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from agent_loop.belief_state import BeliefStateUpdater
from agent_loop.extractors.read_file import ReadFileExtractor
from agent_loop.extractors.run_command import RunCommandExtractor
from agent_loop.extractors.web_search import WebSearchExtractor
from agent_loop.types import (
    AgentLoopConfig,
    Assertion,
    ContradictionRecord,
    TaskContext,
    ToolExecutionRef,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_ctx() -> TaskContext:
    return TaskContext(task_id="test-task", description="test")


def make_ref(tool="read_file", iteration=1, call_hash="abc") -> ToolExecutionRef:
    return ToolExecutionRef(tool_name=tool, iteration=iteration, call_hash=call_hash)


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


def test_tool_execution_ref_fields():
    ref = ToolExecutionRef(tool_name="run_command", iteration=3, call_hash="xyz")
    assert ref.tool_name == "run_command"
    assert ref.iteration == 3
    assert ref.call_hash == "xyz"


def test_assertion_is_active():
    a = Assertion(
        key="k",
        value=True,
        confidence=1.0,
        sources=[make_ref()],
        confirmed_at=datetime.now(tz=timezone.utc),
    )
    assert a.is_active is True
    a.refuted_at = datetime.now(tz=timezone.utc)
    assert a.is_active is False


def test_contradiction_record_fields():
    cr = ContradictionRecord(
        key="k",
        prior_value="old",
        prior_confidence=0.8,
        new_value="new",
        new_confidence=0.9,
        iteration=2,
        resolution="updated",
    )
    assert cr.resolution == "updated"
    assert isinstance(cr.timestamp, datetime)


def test_task_context_default_fields():
    ctx = make_ctx()
    assert ctx.assertions == {}
    assert ctx.contradictions == []


def test_agent_loop_config_belief_state_disabled_by_default():
    cfg = AgentLoopConfig()
    assert cfg.belief_state_enabled is False


# ---------------------------------------------------------------------------
# BeliefStateUpdater
# ---------------------------------------------------------------------------


class _FakeExtractor:
    def __init__(self, items):
        self._items = items

    def extract(self, _):
        return list(self._items)


@contextmanager
def _registry(mapping: dict):
    import sys

    ext_mod = sys.modules.get("agent_loop.extractors")
    original = getattr(ext_mod, "EXTRACTOR_REGISTRY", {}) if ext_mod else {}
    if ext_mod is not None:
        ext_mod.EXTRACTOR_REGISTRY = mapping
    try:
        yield
    finally:
        if ext_mod is not None:
            ext_mod.EXTRACTOR_REGISTRY = original


def test_belief_updater_insert():
    ctx = make_ctx()
    updater = BeliefStateUpdater()
    with _registry({"my_tool": _FakeExtractor([("key:a", "val", 0.9)])}):
        contradictions = updater.update(ctx, "my_tool", {}, "h1", 1)
    assert len(contradictions) == 0
    assert "key:a" in ctx.assertions
    assert ctx.assertions["key:a"].value == "val"
    assert ctx.assertions["key:a"].confidence == 0.9


def test_belief_updater_reconfirm():
    ctx = make_ctx()
    updater = BeliefStateUpdater()
    with _registry({"my_tool": _FakeExtractor([("key:a", "val", 0.9)])}):
        updater.update(ctx, "my_tool", {}, "h1", 1)
        updater.update(ctx, "my_tool", {}, "h2", 2)
    a = ctx.assertions["key:a"]
    assert len(a.sources) == 2
    assert a.confidence == 0.9
    assert len(ctx.contradictions) == 0


def test_belief_updater_contradiction_updated():
    ctx = make_ctx()
    updater = BeliefStateUpdater()
    # delta = |0.6 - 0.5| = 0.1 < 0.3, new_confidence > prior → updated
    with _registry({"my_tool": _FakeExtractor([("key:a", "old", 0.5)])}):
        updater.update(ctx, "my_tool", {}, "h1", 1)
    with _registry({"my_tool": _FakeExtractor([("key:a", "new", 0.6)])}):
        contradictions = updater.update(ctx, "my_tool", {}, "h2", 2)
    assert len(contradictions) == 1
    assert contradictions[0].resolution == "updated"
    assert ctx.assertions["key:a"].value == "new"


def test_belief_updater_contradiction_suppressed():
    ctx = make_ctx()
    updater = BeliefStateUpdater()
    # delta = |0.7 - 0.9| = 0.2 < 0.3, new < prior → suppressed
    with _registry({"my_tool": _FakeExtractor([("key:a", "old", 0.9)])}):
        updater.update(ctx, "my_tool", {}, "h1", 1)
    with _registry({"my_tool": _FakeExtractor([("key:a", "new", 0.7)])}):
        contradictions = updater.update(ctx, "my_tool", {}, "h2", 2)
    assert contradictions[0].resolution == "suppressed"
    assert ctx.assertions["key:a"].value == "old"


def test_belief_updater_contradiction_surfaced():
    ctx = make_ctx()
    updater = BeliefStateUpdater()
    # delta = |0.9 - 0.5| = 0.4 >= 0.3 → surfaced_to_think
    with _registry({"my_tool": _FakeExtractor([("key:a", "old", 0.9)])}):
        updater.update(ctx, "my_tool", {}, "h1", 1)
    with _registry({"my_tool": _FakeExtractor([("key:a", "new", 0.5)])}):
        contradictions = updater.update(ctx, "my_tool", {}, "h2", 2)
    assert contradictions[0].resolution == "surfaced_to_think"
    assert ctx.assertions["key:a"].value == "new"
    assert ctx.contradictions[0].resolution == "surfaced_to_think"


def test_belief_updater_no_extractor():
    ctx = make_ctx()
    updater = BeliefStateUpdater()
    result = updater.update(ctx, "unknown_tool", {}, "h1", 1)
    assert result == []
    assert ctx.assertions == {}


# ---------------------------------------------------------------------------
# ReadFileExtractor
# ---------------------------------------------------------------------------


def test_read_file_extractor_exists_and_hash():
    ex = ReadFileExtractor()
    content = "hello world"
    output = {"path": "/tmp/foo.txt", "content": content}
    items = ex.extract(output)
    keys = {k for k, _, _ in items}
    assert "read_file:/tmp/foo.txt:exists" in keys
    assert "read_file:/tmp/foo.txt:hash" in keys
    expected_hash = hashlib.sha256(content.encode()).hexdigest()
    for k, v, _ in items:
        if k.endswith(":hash"):
            assert v == expected_hash


def test_read_file_extractor_missing():
    ex = ReadFileExtractor()
    output = {"path": "/tmp/missing.txt", "error": "File not found"}
    items = ex.extract(output)
    assert len(items) == 1
    key, value, conf = items[0]
    assert key == "read_file:/tmp/missing.txt:exists"
    assert value is False
    assert conf == 1.0


def test_read_file_extractor_no_path():
    ex = ReadFileExtractor()
    assert ex.extract({}) == []


# ---------------------------------------------------------------------------
# RunCommandExtractor
# ---------------------------------------------------------------------------


def test_run_command_exit_code():
    ex = RunCommandExtractor()
    items = ex.extract({"command": "git status", "exit_code": 0, "stdout": ""})
    keys = {k for k, _, _ in items}
    assert "run_command:exit_code/git" in keys


def test_run_command_port_from_lsof():
    ex = RunCommandExtractor()
    stdout = "node    1234 user   22u  IPv4  0t0  TCP *:3000 (LISTEN)"
    items = ex.extract({"command": "lsof -i", "exit_code": 0, "stdout": stdout})
    port_items = [(k, v) for k, v, _ in items if "port" in k]
    assert any(v == 3000 for _, v in port_items)


def test_run_command_port_from_flag():
    ex = RunCommandExtractor()
    stdout = "Starting server with --port 8080"
    items = ex.extract({"command": "python app.py", "exit_code": 0, "stdout": stdout})
    port_items = [(k, v) for k, v, _ in items if "port" in k]
    assert any(v == 8080 for _, v in port_items)


def test_run_command_port_from_ss():
    ex = RunCommandExtractor()
    stdout = "LISTEN  0  128  0.0.0.0:5432  0.0.0.0:*"
    items = ex.extract({"command": "ss -tlnp", "exit_code": 0, "stdout": stdout})
    port_items = [v for k, v, _ in items if "port" in k]
    assert 5432 in port_items


# ---------------------------------------------------------------------------
# WebSearchExtractor
# ---------------------------------------------------------------------------


def test_web_search_answered():
    ex = WebSearchExtractor()
    output = {
        "query": "Python async tutorial",
        "results": [{"title": "Python Asyncio Guide", "url": "https://example.com"}],
    }
    items = ex.extract(output)
    answered = {k: v for k, v, _ in items}
    assert answered.get("web_search:python_async_tutorial:answered") is True


def test_web_search_top_entity():
    ex = WebSearchExtractor()
    output = {
        "query": "best Python web framework",
        "results": [{"title": "FastAPI", "url": "https://fastapi.tiangolo.com"}],
    }
    items = {k: v for k, v, _ in ex.extract(output)}
    assert items.get("web_search:best_python_web_framework:top_entity") == "FastAPI"


def test_web_search_no_results():
    ex = WebSearchExtractor()
    output = {"query": "xyz obscure query", "results": []}
    items = {k: v for k, v, _ in ex.extract(output)}
    assert items.get("web_search:xyz_obscure_query:answered") is False


def test_web_search_no_query():
    ex = WebSearchExtractor()
    assert ex.extract({"results": []}) == []
