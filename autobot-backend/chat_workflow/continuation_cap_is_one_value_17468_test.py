# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The continuation cap is one value, and the LangGraph route reads it (#17468).

`ChatWorkflowManager.MAX_CONTINUATION_ITERATIONS = 5` was the named cap.
`graph.route_after_execution` hardcoded `iteration_count < 5` beside it. Both
said five, so **nothing failed and nothing logged** -- raising the constant
simply had no effect on the LangGraph path, and the only way to notice was to
raise it and watch the loop keep its old bound.

That is why a duplicated value is dangerous specifically while it is correct:
there is no failing state to observe until someone acts on the wrong one.

These tests drive the real routing function. A test asserting the two names are
equal would pass against the old code too -- both were 5 -- so the binding
assertion is the one that CHANGES the cap and checks the route's answer moves.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from chat_workflow import limits
from chat_workflow.graph import route_after_execution


def _continuing_state(iteration: int) -> dict:
    """A state that reaches the cap check: no error, loop detector quiet."""
    return {"should_continue": True, "iteration_count": iteration, "tool_loop_count": 0}


def test_raising_the_cap_lets_the_route_continue(monkeypatch: pytest.MonkeyPatch) -> None:
    """The defect, stated as a behaviour change the old code could not produce.

    At iteration 5 with a cap of 5 the route must stop. Raise the cap and it
    must continue. Against the hardcoded `< 5` the second assertion fails --
    which is exactly the bug: the constant moved and this path did not.
    """
    state = _continuing_state(5)

    monkeypatch.setattr(limits, "MAX_CONTINUATION_ITERATIONS", 5)
    assert route_after_execution(state) == "persist_conversation"

    monkeypatch.setattr(limits, "MAX_CONTINUATION_ITERATIONS", 7)
    assert (
        route_after_execution(state) == "generate_response"
    ), "the route ignored a raised cap -- it is reading its own literal, not the shared value"


def test_lowering_the_cap_stops_the_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other direction, which a raise-only test would miss.

    A hardcoded `< 5` also ignores a cap LOWERED to 2: iteration 3 would keep
    going. Both directions matter because the cap is a safety limit, and the
    dangerous failure is the one that runs longer than configured.
    """
    monkeypatch.setattr(limits, "MAX_CONTINUATION_ITERATIONS", 2)

    assert (
        route_after_execution(_continuing_state(3)) == "persist_conversation"
    ), "the route ran past a lowered cap -- a safety limit that cannot be tightened"


def test_the_manager_and_the_route_share_one_source() -> None:
    """Guards divergence rather than proving the fix.

    Deliberately weak on its own: before #17468 both were 5, so this passed
    while the bug was live. It is here to catch someone re-introducing a second
    literal, not to demonstrate the original defect -- the two tests above do
    that.
    """
    from chat_workflow.manager import ChatWorkflowManager

    assert ChatWorkflowManager.MAX_CONTINUATION_ITERATIONS == limits.MAX_CONTINUATION_ITERATIONS


def test_the_cap_is_env_backed() -> None:
    """A budget written as a bare literal cannot be changed without a deploy."""
    import inspect

    source = inspect.getsource(limits)
    assert (
        'env_int("AUTOBOT_MAX_CONTINUATION_ITERATIONS"' in source
    ), "the cap must come from an env var per the project's configuration rule"


# ---------------------------------------------------------------------------
# #17468 AC3: a second numeric cap anywhere in chat_workflow/ must fail
# ---------------------------------------------------------------------------

#: Operand text that means "how far round the continuation loop are we".
_CAP_OPERANDS = ("iteration_count", "MAX_CONTINUATION_ITERATIONS", "continuation_iterations")


def _numeric_cap_comparisons() -> list[str]:
    """Every `<cap-ish> <op> <number>` comparison in `chat_workflow/`.

    AST rather than a regex, so a docstring quoting the old `< 5` does not read
    as a reinstated cap -- this file's own docstring describes the defect and
    would match a text scan.

    The rule is not "no numbers near iteration_count". It is that the *bound*
    must be a name, because the defect was a literal bound that could not be
    changed from the one place the constant lives.
    """
    package = pathlib.Path(__file__).parent
    offenders: list[str] = []
    for path in sorted(package.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare) or len(node.comparators) != 1:
                continue
            left, right = ast.unparse(node.left), ast.unparse(node.comparators[0])
            cap_side = any(marker in left for marker in _CAP_OPERANDS)
            bound = node.comparators[0]
            if cap_side and isinstance(bound, ast.Constant) and isinstance(bound.value, (int, float)):
                offenders.append(f"{path.name}:{node.lineno}: {left} ... {right}")
    return offenders


def test_no_second_numeric_continuation_cap_exists() -> None:
    """#17468 AC3. The defect was a literal bound beside a named one.

    A bound written as a number is a second truth by construction: it cannot be
    reached from `limits`, so the two agree only until someone changes one. This
    fails on any new one rather than on the specific line that was fixed --
    fixing the instance and leaving the pattern is what #17387 taught, where the
    same bug survived in a file the guard could not see.
    """
    offenders = _numeric_cap_comparisons()

    assert not offenders, (
        "a continuation cap is compared against a numeric literal -- the bound must be a name "
        f"so `limits.MAX_CONTINUATION_ITERATIONS` is the only place it lives (#17468): {offenders}"
    )


def test_the_cap_scan_can_actually_see_a_literal_bound(tmp_path: pathlib.Path) -> None:
    """The contrast: a scan that finds nothing must be able to find something.

    Without this, `test_no_second_numeric_continuation_cap_exists` passes
    identically whether the tree is clean or the scan is broken -- the shape
    this repo has been removing from guards all week (#15826).
    """
    module = tmp_path / "probe.py"
    module.write_text('def f(state):\n    return state.get("iteration_count", 0) < 5\n', encoding="utf-8")

    tree = ast.parse(module.read_text(encoding="utf-8"))
    found = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Compare)
        and any(m in ast.unparse(n.left) for m in _CAP_OPERANDS)
        and isinstance(n.comparators[0], ast.Constant)
    ]
    assert found, "the predicate cannot see a literal bound, so its clean answer means nothing"
