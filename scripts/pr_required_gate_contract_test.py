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
import json
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


def test_an_empty_requirement_list_is_not_a_pass(monkeypatch):
    """`verdict([], {})` returned CONTEXTS-GREEN: the happy path reached by a failed load.

    The control is the second half. A gate that returned NO-REQUIREMENTS for
    everything would also satisfy the first assertion, and it is the failure
    mode that gets a gate disabled rather than repaired.
    """
    assert gate_module.base_verdict(gate_module.verdict([], {})["verdict"]) == gate_module.NO_REQUIREMENTS
    assert gate_module.NO_REQUIREMENTS not in gate_module.CLEARING_VERDICTS

    # CONTROL: one requirement, reported green -> still clears.
    cleared = gate_module.verdict(["smoke-test"], {"smoke-test": "success"})
    assert gate_module.base_verdict(cleared["verdict"]) == "CONTEXTS-GREEN"


def test_an_empty_requirement_list_exits_non_zero_end_to_end(monkeypatch):
    """Through `main`, because the exit code is what a caller branches on."""
    monkeypatch.setattr(
        gate_module,
        "_fetch",
        lambda pr, repo, base: {
            "required": [],
            "app_pinned": [],
            "observed": {"smoke-test": "success"},
            "head": "0" * 40,
            "pr_state": "OPEN",
            "is_draft": False,
        },
    )
    emitted: list[str] = []
    monkeypatch.setattr(gate_module, "_emit", emitted.append)
    assert gate_module.main(["123"]) == 1, "a PR with no required contexts cleared the gate"
    assert any(gate_module.NO_REQUIREMENTS in line for line in emitted), emitted
    assert any("not a pass" in line for line in emitted), "the reason was not reported"


def test_an_operational_failure_is_not_reported_as_a_verdict(monkeypatch):
    """A raising `gh` exited 1, the same status as BLOCKED, and the wrapper said

    "NOT clear to merge ... verdict above" with no verdict above it. The status
    must differ from BOTH the clearing and the non-clearing verdict codes.
    """
    import subprocess

    def _boom(pr, repo, base):
        raise subprocess.CalledProcessError(1, ["gh", "api", "..."], stderr="gh: not found")

    monkeypatch.setattr(gate_module, "_fetch", _boom)
    emitted: list[str] = []
    monkeypatch.setattr(gate_module, "_emit", emitted.append)

    rc = gate_module.main(["17962"])
    assert rc == gate_module.EXIT_GATE_ERROR, f"operational failure exited {rc}"
    assert rc != 0, "an unreachable verdict must not read as clearance"
    assert rc != 1, "an unreachable verdict must not read as BLOCKED"
    assert any("GATE-ERROR" in line for line in emitted), emitted
    # The word a reader scans for must NOT appear: this is the failure mode.
    assert not any("GREEN" in line for line in emitted), emitted
    # And it must not have smuggled itself into the verdict vocabulary.
    assert "GATE-ERROR" not in gate_module.VERDICTS


def test_each_gate_error_type_is_caught_and_a_real_bug_is_not(monkeypatch):
    """The catch is narrow ON PURPOSE.

    A bare `except Exception` would turn a genuine bug in the verdict logic
    into a tidy "could not reach a verdict" -- substituting a plausible answer
    for a real one, which is what this tool exists to stop. So every listed
    error type is asserted to be caught, and an UNLISTED one is asserted to
    propagate.
    """
    import json as _json
    import subprocess

    emitted: list[str] = []
    monkeypatch.setattr(gate_module, "_emit", emitted.append)

    for exc in (
        subprocess.CalledProcessError(1, ["gh"]),
        _json.JSONDecodeError("bad", "{", 0),
        KeyError("headRefOid"),
        OSError("network down"),
    ):
        monkeypatch.setattr(gate_module, "_fetch", lambda p, r, b, e=exc: (_ for _ in ()).throw(e))
        assert gate_module.main(["1"]) == gate_module.EXIT_GATE_ERROR, f"not caught: {exc!r}"

    # CONTROL: a bug in the logic must still crash loudly, not be laundered.
    monkeypatch.setattr(gate_module, "_fetch", lambda p, r, b: (_ for _ in ()).throw(ZeroDivisionError("real bug")))
    with pytest.raises(ZeroDivisionError):
        gate_module.main(["1"])


def test_the_premerge_lookup_is_scoped_by_repo_and_base():
    """The PR lookup and the verdict must be about the same PR.

    The lookup took neither `--repo` nor `--base` while the gate took both, so
    with `--repo R` it searched the checkout, and with two open PRs sharing a
    head branch it could return the one targeting a different base -- which the
    gate then judged against the requested base's protection. `gh pr view`
    never fetches the target branch, so nothing downstream caught it.

    Anchored on the forwarding lines rather than on the flags appearing
    anywhere in the file: both strings already occur in `GATE_ARGS` just below,
    so a file-wide grep would pass on the unfixed script.
    """
    script = MERGE_GATE.read_text(encoding="utf-8")
    lookup = script.split("LOOKUP_ARGS=(", 1)
    assert len(lookup) == 2, "the lookup no longer builds an argument array — guard is stale"
    body = lookup[1].split("if ! PR_NUMBER=", 1)[0]
    assert 'LOOKUP_ARGS+=(--repo "$REPO")' in body, "the PR lookup does not forward --repo"
    assert 'LOOKUP_ARGS+=(--base "$BASE")' in body, "the PR lookup does not forward --base"
    assert 'gh pr list "${LOOKUP_ARGS[@]}"' in script, "the lookup does not use the scoped array"


def test_the_premerge_wrapper_separates_unknown_from_refused():
    """Three outcomes: green (0), judged-and-not-green (1), could-not-judge (2).

    The wrapper's final branch was the `else` of a two-way test, so any
    non-zero gate status printed "is NOT clear to merge ... verdict above".
    """
    script = MERGE_GATE.read_text(encoding="utf-8")
    assert '[ "$GATE_RC" -ne 1 ]' in script, "the wrapper does not separate UNKNOWN from refused"
    unknown = script.split('[ "$GATE_RC" -ne 1 ]', 1)[1].split("fi", 1)[0]
    assert "exit 2" in unknown, "the UNKNOWN arm does not exit 2"
    assert "not a refusal" in unknown, "the UNKNOWN arm does not say it is not a refusal"


def _draft_fetch(*, pr_state: str = "OPEN", is_draft: bool = True):
    """A fetch whose CONTEXTS are unanimously green, so only the PR state can block.

    Every required context reports `skipped`, which is what a draft actually
    produces here: the heavy jobs are gated on `draft == false`, so they never
    start and publish a skip. If the verdict came from the contexts alone this
    would be `CONTEXTS-GREEN`, which is the defect.
    """
    return lambda pr, repo, base: {
        "required": ["python-suite", "code-quality"],
        "app_pinned": [],
        "observed": {"python-suite": "skipped", "code-quality": "skipped"},
        "head": "0" * 40,
        "pr_state": pr_state,
        "is_draft": is_draft,
    }


def test_a_draft_pr_does_not_clear_however_green_its_contexts_read(monkeypatch):
    """The sixth blind spot (#17962): the gate said green, the merge API said draft.

    The control is the `is_draft=False` half. Without it this test passes on a
    gate that blocks EVERY PR, which is the other way to get the draft case
    wrong and the way that gets a gate switched off rather than fixed.
    """
    emitted: list[str] = []
    monkeypatch.setattr(gate_module, "_emit", emitted.append)

    monkeypatch.setattr(gate_module, "_fetch", _draft_fetch())
    assert gate_module.main(["17962"]) == 1, "a draft PR cleared the gate"
    assert any("DRAFT" in line for line in emitted), f"no DRAFT verdict in {emitted}"
    assert gate_module.DRAFT not in gate_module.CLEARING_VERDICTS

    # CONTROL: identical contexts, not a draft -> the same inputs must clear.
    emitted.clear()
    monkeypatch.setattr(gate_module, "_fetch", _draft_fetch(is_draft=False))
    assert gate_module.main(["17962"]) == 0, "skipped contexts must still clear a ready PR"
    assert any("CONTEXTS-GREEN" in line for line in emitted), f"no green verdict in {emitted}"


def test_a_closed_draft_reports_not_open_rather_than_draft(monkeypatch):
    """Precedence, not coincidence: telling someone to undraft a closed PR is the wrong fix."""
    emitted: list[str] = []
    monkeypatch.setattr(gate_module, "_emit", emitted.append)
    monkeypatch.setattr(gate_module, "_fetch", _draft_fetch(pr_state="CLOSED", is_draft=True))
    assert gate_module.main(["17962"]) == 1
    line = next(entry for entry in emitted if "#17962" in entry)
    assert "NOT-OPEN (CLOSED)" in line, line
    assert "DRAFT" not in line, f"NOT-OPEN must win over DRAFT: {line}"


def test_the_fetch_actually_requests_the_draft_field(monkeypatch):
    """A verdict that reads `is_draft` is useless if nothing ever populates it.

    `_fetch` is the only place the field enters the program, and it enters as a
    name inside a comma-separated `--json` argument -- so a rename there fails
    silently into the `False` default rather than raising. This asserts the
    request, which is the half the other tests monkeypatch away.
    """
    calls: list[tuple[str, ...]] = []

    def _fake_gh(*args: str) -> str:
        calls.append(args)
        if "api" in args:
            return json.dumps({"required_status_checks": {"contexts": ["smoke-test"]}})
        if "pr" in args:
            return json.dumps({"headRefOid": "0" * 40, "state": "OPEN", "isDraft": True})
        return "[]"

    monkeypatch.setattr(gate_module, "_gh", _fake_gh)
    monkeypatch.setattr(gate_module, "check_runs_for", lambda repo, head: [])
    monkeypatch.setattr(gate_module, "_all_pages", lambda endpoint: [])
    fetched = gate_module._fetch(17962, "mrveiss/AutoBot-AI", "main")

    pr_view = next(args for args in calls if "pr" in args and "view" in args)
    json_fields = pr_view[pr_view.index("--json") + 1].split(",")
    assert "isDraft" in json_fields, f"_fetch never asks for isDraft: {json_fields}"
    assert fetched["is_draft"] is True


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
