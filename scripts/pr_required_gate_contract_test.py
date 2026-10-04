# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The gate's CONTRACT with its callers — split out of pr_required_gate_test.py.

That file tests what the gate answers. This one tests the two properties a
caller depends on and neither of which any verdict can show:

* **the verdict vocabulary is closed** (#16044) — every code path returns one
  of a declared set, so a sixth blind spot cannot join the merge-clearing
  answers without a line in the diff saying a state was invented;
* **something invokes the gate** (#15995) — it shipped correct and reached by
  nothing, which makes it the rule in CLAUDE_REVIEW.md it was written to
  replace rather than an enforcement of it.

Split because `pr_required_gate_test.py` reached the 600-line ceiling
(`scripts/check_python_file_size.py`); the boundary is the subject, not the
line count.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pr_required_gate as gate_module  # noqa: E402

GATE_SOURCE = pathlib.Path(gate_module.__file__).read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# The verdict vocabulary is closed (#16044 AC3/AC4).
#
# The tool's history is five blind spots found one at a time, each fixed by
# adding a case. What that makes cheap is adding a SIXTH case silently: a new
# `return "GREEN-SOMETHING"` reads as a refinement of an existing green and
# joins the merge-clearing answers with nothing in the diff saying a state was
# invented. These tests make that diff mandatory.
# ---------------------------------------------------------------------------

GATE_SOURCE = pathlib.Path(gate_module.__file__).read_text(encoding="utf-8")

#: The four syntactic shapes a verdict string can be produced in. Enumerated
#: independently of how the extractor looks for them, and each one carries a
#: control below -- a control witnesses only the shape it is written in, so one
#: control would attest to one shape and read as attesting to the detector.
_ESCAPE_CONTROLS = {
    "bare return": 'def f():\n    return "GREEN-ISH"\n',
    "return of a module constant": 'GREEN_ISH = "GREEN-ISH"\n\n\ndef f():\n    return GREEN_ISH\n',
    "verdict key, plain": 'def f(r):\n    r["verdict"] = "GREEN-ISH"\n',
    "verdict key, f-string": 'def f(r, s):\n    r["verdict"] = f"GREEN-ISH ({s})"\n',
}


def _module_strings(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "literal"`` bindings, so a Name can be resolved.

    Without this the extractor is blind to one whole shape: binding the new
    state to a constant and returning the name. Resolved from the SOURCE rather
    than from the imported module, so the test judges the file in the diff.
    """
    bindings: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                bindings[target.id] = node.value.value
    return bindings


def _as_verdict(node, bindings: dict[str, str]) -> str | None:
    """The verdict token a node produces, detail suffix stripped, or ``None``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.split(" (", 1)[0]
    if isinstance(node, ast.Name) and node.id in bindings:
        return bindings[node.id].split(" (", 1)[0]
    if isinstance(node, ast.JoinedStr):
        head = next((part.value for part in node.values if isinstance(part, ast.Constant)), None)
        return None if head is None else str(head).split(" (", 1)[0]
    return None


def _verdict_escapes(source: str) -> list[str]:
    """Verdict strings produced WITHOUT passing through ``declared()``.

    ``declared()`` is the module's only verdict producer and refuses anything
    outside ``VERDICTS`` at runtime, so the only way a new state reaches the
    output is by going around it. Two routes exist: returning a string from a
    function (every function in this module that returns a bare string returns a
    verdict -- nothing else here does), and assigning one to the ``"verdict"``
    key of the result dict.
    """
    tree = ast.parse(source)
    bindings = _module_strings(tree)
    escapes: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Return):
            token = _as_verdict(node.value, bindings)
            if token is not None:
                escapes.append(token)
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "verdict"
            ):
                token = _as_verdict(node.value, bindings)
                if token is not None:
                    escapes.append(token)
    return escapes


def _declared_literals(source: str) -> list[str]:
    """Every verdict token handed to ``declared()`` as its first argument."""
    tree = ast.parse(source)
    bindings = _module_strings(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "declared"):
            continue
        if not node.args:
            continue
        token = _as_verdict(node.args[0], bindings)
        if token is not None:
            found.append(token)
    return found


def test_the_escape_detector_finds_each_shape_a_new_verdict_can_take():
    """The control set, one case per shape — asserted BEFORE the count below.

    A detector that matched nothing would make the closure test pass by seeing
    nothing, which is the failure this whole module exists to catch, inside its
    own suite.
    """
    for shape, source in _ESCAPE_CONTROLS.items():
        assert "GREEN-ISH" in _verdict_escapes(source), f"detector blind to: {shape}"


def test_no_verdict_reaches_the_output_without_being_declared():
    """AC3/AC4: a new verdict literal cannot escape the declared set.

    Add `return "GREEN-ISH"` to `_required_result`, or
    `result["verdict"] = "GREEN-ISH"` to `main`, and this fails naming it.
    """
    escapes = _verdict_escapes(GATE_SOURCE)
    assert escapes == [], (
        "verdict string(s) produced outside declared(): "
        f"{escapes} -- route them through declared() and add them to VERDICTS (#16044)"
    )


def test_every_declared_literal_is_in_the_set_and_the_set_is_fully_used():
    """Both directions. One catches a new state; the other catches a dead entry.

    The membership half is also enforced at runtime by ``declared()``; it is
    asserted statically too because a branch no test exercises never runs it.
    """
    literals = _declared_literals(GATE_SOURCE)
    assert "CONTEXTS-GREEN" in literals, "known positive absent — the extractor found nothing to judge"
    undeclared = sorted(set(literals) - gate_module.VERDICTS)
    assert undeclared == [], f"declared() called with {undeclared}, which is not in VERDICTS"
    unreachable = sorted(gate_module.VERDICTS - set(literals))
    assert unreachable == [], f"VERDICTS carries {unreachable}, which no code path produces"


def test_declared_refuses_a_verdict_nobody_registered():
    """The runtime half: the mutation that matters, executed rather than parsed."""
    with pytest.raises(ValueError, match="undeclared verdict"):
        gate_module.declared("GREEN-ISH")


@pytest.mark.parametrize(
    "required,observed",
    [
        (["a"], {"a": "success"}),
        (["a"], {}),
        (["a"], {"a": "failure"}),
        (["a"], {"a": "queued"}),
        (["a"], {"a": "success", "b": "failure"}),
        (["a"], {"a": "success", "b": "in_progress"}),
        ([], {}),
    ],
)
def test_every_branch_of_the_verdict_returns_a_declared_state(required, observed):
    """The behavioural half of the closure: drive the branches, read the labels."""
    result = gate_module.verdict(required, observed)
    assert gate_module.base_verdict(result["verdict"]) in gate_module.VERDICTS, result


def test_a_not_open_verdict_keeps_its_detail_and_still_reads_as_declared(monkeypatch):
    """`NOT-OPEN (MERGED)` is not a member of VERDICTS by equality, and must still pass."""
    monkeypatch.setattr(
        gate_module,
        "_fetch",
        lambda pr, repo, base: {
            "required": ["smoke-test"],
            "app_pinned": [],
            "observed": {"smoke-test": "success"},
            "head": "0" * 40,
            "pr_state": "MERGED",
        },
    )
    emitted: list[str] = []
    monkeypatch.setattr(gate_module, "_emit", emitted.append)
    assert gate_module.main(["123"]) == 1
    line = next(entry for entry in emitted if "NOT-OPEN" in entry)
    assert "NOT-OPEN (MERGED)" in line
    assert gate_module.base_verdict("NOT-OPEN (MERGED)") in gate_module.VERDICTS


# ---------------------------------------------------------------------------
# AC1 of #15995: "a shared helper answers 'is this PR mergeable on required
# contexts', USED BY whatever automation merges."
#
# The tool was correct and reached by nothing: `git grep -l pr_required_gate`
# returned its own test, one research document and a pytest timing file. A gate
# nobody calls is the same thing as the prose rule in CLAUDE_REVIEW.md that it
# was written to replace -- which is why the reach is a test rather than a
# sentence in the issue.
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(gate_module.__file__).resolve().parents[1]

#: The caller, and the exact line that makes it one. Anchored on the DEFAULT of
#: the override rather than on the name appearing somewhere in the file: the
#: first draft of this guard grepped for `pr_required_gate` and passed on a
#: mutant that pointed the invocation at another script, because the
#: explanatory comment above it still carried the name. A mention is not a
#: call, and that is the one failure this repository has recorded most.
#:
#: What the caller DOES with the verdict is covered behaviourally in
#: `scripts/pr-merge-gate_test.sh`, which drives it through
#: `PR_MERGE_GATE_SCRIPT` with a stub and asserts the pass and fail arms.
MERGE_GATE = REPO_ROOT / "scripts" / "pr-merge-gate.sh"
INVOCATION_DEFAULT = 'GATE_SCRIPT="${PR_MERGE_GATE_SCRIPT:-$REPO_ROOT/scripts/pr_required_gate.py}"'


def test_the_premerge_script_resolves_the_gate_by_default():
    """AC1 of #15995: whatever decides a merge calls the gate.

    Point `GATE_SCRIPT` anywhere else and this fails, even though every comment
    around it still names the gate.
    """
    source = MERGE_GATE.read_text(encoding="utf-8")
    executed = [line.strip() for line in source.splitlines() if not line.strip().startswith("#")]
    assert any("pr_required_gate" in line for line in executed), (
        "nothing in scripts/pr-merge-gate.sh invokes the gate on an executed line "
        "(#15995 AC1) -- a gate reached only by its own test is prose with a shebang"
    )
    assert INVOCATION_DEFAULT in executed, (
        "scripts/pr-merge-gate.sh no longer defaults GATE_SCRIPT to scripts/pr_required_gate.py; "
        f"expected the line {INVOCATION_DEFAULT!r}"
    )
