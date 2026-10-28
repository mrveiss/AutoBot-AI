# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The tool-call and tool-group budgets have one home: ``autobot_shared.tool_timeouts`` (#19729).

The agent loop and the parallel tool executor each restated 30000 / 60000 ms as literals.
Both now default to the shared constants, and an env override reaches both.
"""

import importlib

import pytest

from agent_loop.types import AgentLoopConfig
from autobot_shared import tool_timeouts
from tools.parallel.executor import ParallelExecutorConfig


def test_both_modules_resolve_to_the_same_shared_budgets() -> None:
    loop, executor = AgentLoopConfig(), ParallelExecutorConfig()
    assert loop.tool_timeout_ms == executor.per_call_timeout_ms == tool_timeouts.TOOL_CALL_TIMEOUT_MS
    assert loop.iteration_timeout_ms == executor.group_timeout_ms == tool_timeouts.TOOL_GROUP_TIMEOUT_MS


def test_the_defaults_are_the_values_both_modules_used_to_hardcode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOBOT_TOOL_CALL_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("AUTOBOT_TOOL_GROUP_TIMEOUT_MS", raising=False)
    try:
        fresh = importlib.reload(tool_timeouts)
        assert (fresh.TOOL_CALL_TIMEOUT_MS, fresh.TOOL_GROUP_TIMEOUT_MS) == (30000, 60000)
    finally:
        importlib.reload(tool_timeouts)


def test_the_env_overrides_the_budgets_and_a_non_positive_value_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOBOT_TOOL_CALL_TIMEOUT_MS", "4500")
    monkeypatch.setenv("AUTOBOT_TOOL_GROUP_TIMEOUT_MS", "0")
    try:
        fresh = importlib.reload(tool_timeouts)
        assert (fresh.TOOL_CALL_TIMEOUT_MS, fresh.TOOL_GROUP_TIMEOUT_MS) == (4500, 1)
    finally:
        monkeypatch.undo()
        importlib.reload(tool_timeouts)


_FIELDS = {
    "agent_loop/types.py": ("AgentLoopConfig", {"tool_timeout_ms", "iteration_timeout_ms"}),
    "tools/parallel/executor.py": ("ParallelExecutorConfig", {"per_call_timeout_ms", "group_timeout_ms"}),
}


def literal_budget_fields(source: str, cls: str, fields: set[str]) -> list[str]:
    """Budget fields of *cls* in *source* whose default is a numeric literal."""
    import ast

    body = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ClassDef) and n.name == cls).body
    return [
        n.target.id
        for n in body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id in fields
        if isinstance(n.value, ast.Constant) and isinstance(n.value.value, int)
    ]


@pytest.mark.parametrize("rel", sorted(_FIELDS))
def test_neither_module_restates_a_budget_as_a_literal(rel: str) -> None:
    from pathlib import Path

    cls, fields = _FIELDS[rel]
    source = (Path(__file__).resolve().parents[1] / rel).read_text(encoding="utf-8")
    assert literal_budget_fields(source, cls, fields) == []


def test_the_literal_detector_sees_a_restated_budget() -> None:
    source = "class ParallelExecutorConfig:\n    per_call_timeout_ms: int = 30000\n    group_timeout_ms: int = X\n"
    assert literal_budget_fields(source, "ParallelExecutorConfig", {"per_call_timeout_ms", "group_timeout_ms"}) == [
        "per_call_timeout_ms"
    ]
