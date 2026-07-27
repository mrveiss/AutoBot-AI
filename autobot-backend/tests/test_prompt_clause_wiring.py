# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The preference and skill clauses must actually reach an assembled prompt (#12829).

Both `build_preference_clause` (#10545) and `build_skill_clause` (#12810) were
shipped, unit-tested, and never called from production code — `get_optimized_prompt`
accepted both parameters and nothing ever passed them, so learned tenant
preferences and ranked skills never influenced a single prompt.

Unit tests of the builders cannot catch that: they passed the whole time. What
needs pinning is the *connection*, so these tests assert the call site itself.
`services/llm_service.py` is parsed rather than imported because the backend test
suite stubs that module, and a stub would make any import-based assertion vacuous.
"""

import ast
from pathlib import Path

import pytest

_LLM_SERVICE = Path(__file__).parent.parent / "services" / "llm_service.py"


def _tree() -> ast.Module:
    return ast.parse(_LLM_SERVICE.read_text(encoding="utf-8"))


def _find_call(tree: ast.Module, func_name: str) -> ast.Call | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == func_name:
            return node
    return None


def _find_func(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    return None


# ---------------------------------------------------------------------------
# The wiring itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kwarg", ["preference_clause", "skill_clause"])
def test_get_optimized_prompt_is_passed_the_clause(kwarg: str) -> None:
    """The assembly call must pass both clauses, or the builders stay dead code."""
    call = _find_call(_tree(), "get_optimized_prompt")
    assert call is not None, "get_optimized_prompt call site not found in llm_service.py"

    passed = {kw.arg for kw in call.keywords}
    assert kwarg in passed, (
        f"get_optimized_prompt is not passed {kwarg!r}. Without it the clause builder "
        "is unreachable and the prompt silently loses that signal (#12829)."
    )


@pytest.mark.parametrize("builder", ["build_preference_clause", "build_skill_clause"])
def test_clause_builder_is_actually_called(builder: str) -> None:
    fn = _find_func(_tree(), "_build_prompt_clauses")
    assert fn is not None, "_build_prompt_clauses helper not found"

    called = {getattr(n.func, "id", None) for n in ast.walk(fn) if isinstance(n, ast.Call)}
    assert builder in called, f"{builder} is never called — its result cannot reach a prompt"


def test_clause_builders_are_awaited() -> None:
    """Both builders are async; calling without await would pass a coroutine object."""
    fn = _find_func(_tree(), "_build_prompt_clauses")
    awaited = {
        getattr(n.value.func, "id", None) for n in ast.walk(fn) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)
    }
    assert {"build_preference_clause", "build_skill_clause"} <= awaited


def test_preference_clause_is_scoped_to_task_class_and_tenant() -> None:
    """Biases are per task-class and per tenant; an unscoped lookup returns the wrong set."""
    fn = _find_func(_tree(), "_build_prompt_clauses")
    call = _find_call(fn, "build_preference_clause")
    assert call is not None

    passed = {kw.arg for kw in call.keywords}
    assert {"task_class", "user_id", "org_id"} <= passed


# ---------------------------------------------------------------------------
# End-to-end: a clause reaches the assembled prompt text
# ---------------------------------------------------------------------------

_PROMPT_KEY = "chat.system_prompt"


def test_assembled_prompt_contains_both_clauses() -> None:
    from prompt_manager import get_optimized_prompt

    assembled = get_optimized_prompt(
        base_prompt_key=_PROMPT_KEY,
        preference_clause="PREFERENCE_BLOCK_MARKER",
        skill_clause="SKILL_BLOCK_MARKER",
    )

    assert "PREFERENCE_BLOCK_MARKER" in assembled
    assert "SKILL_BLOCK_MARKER" in assembled


def test_prompt_unchanged_when_no_clauses() -> None:
    """No qualifying biases and no ranked skills must leave the prompt untouched."""
    from prompt_manager import get_optimized_prompt

    baseline = get_optimized_prompt(base_prompt_key=_PROMPT_KEY)
    with_none = get_optimized_prompt(base_prompt_key=_PROMPT_KEY, preference_clause=None, skill_clause=None)

    assert with_none == baseline
    assert "PREFERENCE_BLOCK_MARKER" not in baseline
