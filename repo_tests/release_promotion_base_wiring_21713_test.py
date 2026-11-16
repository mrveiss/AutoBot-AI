# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every workflow that runs a base-reading guard on a PR into ``release`` takes the #19466 base (#21713).

On a PR into ``release`` the ratchet base is the head's merge base with main (#19466, owner ruling
2026-10-24); its one home is ``.github/actions/release-promotion-base``. A job that runs a guard
reading ``repo_tests/_ratchet_base.base_commit()`` without it falls back to ``HEAD^1`` -- the
release tip -- and every reach declaration newer than that tip raises ``BaseUnavailable``
(``docs-liquid-tags.yml`` on the promotion PR, #21713). The class is found by behaviour: a job
whose ``pytest`` names the ``repo_tests`` root or a guard whose imports reach ``_ratchet_base``,
in a workflow a PR into ``release`` triggers (``pull_request`` not filtered off ``release``, or a
reusable ``workflow_call`` body, which sees its caller's event). Each such job must call the action
after its checkout and export ``AUTOBOT_RATCHET_BASE_SHA`` from its ``base-sha`` before the guard
runs -- the two steps ``ci.yml`` uses.
"""

from __future__ import annotations

import ast
import fnmatch
import re
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_REPO_TESTS = "repo_tests"
_WORKFLOWS = ".github/workflows"
ACTION = "./.github/actions/release-promotion-base"
RELEASE = "release"
BASE_MODULE = "_ratchet_base"
# A `repo_tests` token in a run script: the bare root, or a path under it. A dotted module name
# (`-p repo_tests.stable_shard`, a plugin) is neither, so a following `.` rules the token out (#21713).
_TOKEN = re.compile(r"(?<![\w/.-])repo_tests(?:/([\w./-]+))?(?![\w.-])")
# Jobs the detector must find, so a detector that finds nothing cannot read as "all wired".
KNOWN_IN_SCOPE = {
    ("ci.yml", "python-shard"),
    ("ci.yml", "short-check"),
    ("docs-liquid-tags.yml", "docs-liquid-tags"),
    ("test-durations.yml", "store-durations"),
    ("marker-tests.yml", "marker-tests"),
    ("_gate-slm-frontend.yml", "slm-frontend-check"),
}


def _imported(tree: ast.AST) -> set[str]:
    """repo_tests module names (dotted, relative to the package) this module imports."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.removeprefix("repo_tests.") for a in node.names if a.name.startswith("repo_tests.")}
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level == 0 and mod.startswith("repo_tests."):
                out.add(mod.removeprefix("repo_tests."))
            elif (node.level == 0 and mod == "repo_tests") or (node.level == 1 and not mod):
                out |= {a.name for a in node.names}
            elif node.level == 1:
                out.add(mod)
    return out


def _module_imports(root: Path) -> dict[str, set[str]]:
    graph = {}
    tests = root / _REPO_TESTS
    for path in tests.rglob("*.py"):
        name = ".".join(path.relative_to(tests).with_suffix("").parts)
        graph[name] = _imported(ast.parse(path.read_text(encoding="utf-8")))
    return graph


def base_readers(graph: dict[str, set[str]]) -> set[str]:
    """Every module whose imports reach ``_ratchet_base``, transitively."""
    readers = {BASE_MODULE}
    grew = True
    while grew:
        new = {name for name, deps in graph.items() if name not in readers and deps & readers}
        readers |= new
        grew = bool(new)
    return readers


def _targets_base_reader(token: str | None, readers: set[str]) -> bool:
    if not token:  # the bare root collects every guard under it
        return True
    dotted = token.removesuffix(".py").strip("/").replace("/", ".")
    return any(r == dotted or r.startswith(dotted + ".") for r in readers)


def _uncommented(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def _listed(script: str, root: Path) -> str:
    """The text of tracked guard lists the script feeds to pytest (ci.yml's short-check reads one)."""
    names = re.findall(r"(?<![\w/.-])([\w./-]+\.txt)\b", script)
    return "\n".join(_uncommented((root / n).read_text(encoding="utf-8")) for n in names if (root / n).is_file())


def runs_base_reader(step: dict, readers: set[str], root: Path) -> bool:
    """True when the step's script runs pytest on a guard that reads the ratchet base."""
    script = _uncommented(str(step.get("run", "")))
    if "pytest" not in script:
        return False
    text = script + "\n" + _listed(script, root)
    return any(_targets_base_reader(m.group(1), readers) for m in _TOKEN.finditer(text))


def _matches_release(patterns) -> bool:
    return any(fnmatch.fnmatchcase(RELEASE, p) for p in patterns or [])


def release_prs_reach(doc: dict) -> bool:
    """True when a PR into ``release`` runs this workflow's jobs."""
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        on = {on: None}
    elif isinstance(on, list):
        on = dict.fromkeys(on)
    on = on or {}
    if "workflow_call" in on:
        return True
    if "pull_request" not in on:
        return False
    pr = on["pull_request"] or {}
    if "branches" in pr:
        return _matches_release(pr["branches"])
    return not _matches_release(pr.get("branches-ignore"))


def _checkout_gap(checkouts: list[dict]) -> str | None:
    """#21713: with no base named (a PR into main, a dispatch, a new branch's push) base_commit()
    reads HEAD^1, so the checkout must hold a parent: fetch-depth 0 (full) or >= 2, as a literal."""
    if not checkouts:
        return "the local action runs before any checkout"
    depth = (checkouts[0].get("with") or {}).get("fetch-depth", 1)
    if not isinstance(depth, int) or depth == 1:
        return f"the checkout's fetch-depth is {depth!r}; HEAD^1 needs 0 or >= 2"
    return None


def _condition_gap(step: dict, guard: dict, what: str) -> str | None:
    """#21713: the wiring must run whenever the guard does, so its `if:` is absent or the guard's own."""
    cond = step.get("if")
    if cond is None or cond == guard.get("if"):
        return None
    return f"the {what}'s `if: {cond}` differs from the guard's, so the guard can run without the base"


def _export_index(steps: list[dict], output: str) -> int | None:
    for i, step in enumerate(steps):
        env = (step.get("env") or {}).values()
        run = str(step.get("run", ""))
        if any(str(v).replace("${{", "").strip().startswith(output) for v in env) and (
            "AUTOBOT_RATCHET_BASE_SHA=" in run and "GITHUB_ENV" in run
        ):
            return i
    return None


def wiring_gap(steps: list[dict], readers: set[str], root: Path) -> str | None:
    """Why this job's base-reading guard would read the release tip, or None when it is wired."""
    first = next((i for i, s in enumerate(steps) if runs_base_reader(s, readers, root)), None)
    if first is None:
        return None
    action = next((i for i, s in enumerate(steps[:first]) if s.get("uses") == ACTION and s.get("id")), None)
    if action is None:
        return f"no `uses: {ACTION}` with an id before the guard step"
    gap = _checkout_gap([s for s in steps[:action] if "actions/checkout" in str(s.get("uses", ""))])
    if gap:
        return gap
    output = f"steps.{steps[action]['id']}.outputs.base-sha"
    export = _export_index(steps[action + 1 : first], output)
    if export is None:
        return f"no step between the action and the guard exports AUTOBOT_RATCHET_BASE_SHA from {output}"
    guard = steps[first]
    return _condition_gap(steps[action], guard, "action") or _condition_gap(
        steps[action + 1 + export], guard, "export step"
    )


def _jobs_in_scope(root: Path) -> list[tuple[str, str, str | None]]:
    """(workflow, job, wiring gap) for every job a PR into release runs that runs a base-reading guard."""
    readers = base_readers(_module_imports(root))
    found = []
    for path in sorted((root / _WORKFLOWS).glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not release_prs_reach(doc):
            continue
        for name, job in (doc.get("jobs") or {}).items():
            steps = job.get("steps") or []
            if any(runs_base_reader(s, readers, root) for s in steps):
                found.append((path.name, name, wiring_gap(steps, readers, root)))
    return found


# Pinned while this guard is new: the base it would compute a floor from has no such declaration
# (#19676). The live population is the six jobs in KNOWN_IN_SCOPE.
REACH = declare(
    "release-promotion-base-wiring-21713",
    discover=_jobs_in_scope,
    what="workflow jobs a pull request into release runs that run a base-reading guard",
    floor=6,
)


def test_every_base_reading_job_a_release_pr_runs_takes_the_promotion_base() -> None:
    jobs = REACH.examined(repo_root())
    in_scope = {(workflow, job) for workflow, job, _ in jobs}
    gaps = [f"{workflow}:{job}: {gap}" for workflow, job, gap in jobs if gap]
    missing = KNOWN_IN_SCOPE - in_scope
    assert not missing, f"the detector lost jobs it must see (instrument check): {sorted(missing)}"
    assert not gaps, (
        "these jobs run a base-reading guard on PRs into release without the #19466 base, so it "
        "reads the release tip and raises BaseUnavailable (#21713). Add the two steps ci.yml uses "
        f"(`uses: {ACTION}` + `Ratchet base (#19283)`):\n" + "\n".join(gaps)
    )


def test_the_closure_reaches_the_guard_that_failed_on_the_promotion_pr() -> None:
    readers = base_readers(_module_imports(repo_root()))
    assert {"_reach", "docs_liquid_tags_are_defined_17930_test"} <= readers


# --- fixtures: the checker on synthetic workflows (positive and negative) -----------------------

_READERS = {BASE_MODULE, "_reach", "x_test"}
_CHECKOUT = {"uses": "actions/checkout@v7", "with": {"fetch-depth": 2}}
_SHALLOW = {"uses": "actions/checkout@v7"}
_ONLY_MAIN = "github.event.pull_request.base.ref == 'main'"
_GUARD = {"run": "python3 -m pytest repo_tests/x_test.py -q"}
_ACTION_STEP = {"uses": ACTION, "id": "release-base"}
_EXPORT = {
    "env": {"EVENT_BASE": "${{ steps.release-base.outputs.base-sha || '' }}"},
    "run": 'echo "AUTOBOT_RATCHET_BASE_SHA=${EVENT_BASE}" >> "$GITHUB_ENV"',
}


@pytest.mark.parametrize(
    ("steps", "gap"),
    [
        ([_CHECKOUT, _GUARD], "no `uses:"),
        ([_CHECKOUT, _ACTION_STEP, _GUARD], "exports AUTOBOT_RATCHET_BASE_SHA"),
        ([_CHECKOUT, _GUARD, _ACTION_STEP, _EXPORT], "no `uses:"),
        ([_ACTION_STEP, _CHECKOUT, _EXPORT, _GUARD], "before any checkout"),
        ([_CHECKOUT, _ACTION_STEP, _EXPORT, _GUARD], None),
        ([_CHECKOUT, {"run": "python3 -m pytest repo_tests/other_test.py"}], None),
        (
            [_CHECKOUT, {"run": "python -m pytest autobot-backend repo_tests -q"}],
            "no `uses:",
        ),
        # #21713 review: a plugin module argument is not the repo_tests root.
        ([_CHECKOUT, {"run": "python -m pytest autobot-backend -p repo_tests.stable_shard -q"}], None),
        # #21713 review: the HEAD^1 fallback needs a parent in the checkout.
        ([_SHALLOW, _ACTION_STEP, _EXPORT, _GUARD], "fetch-depth is 1"),
        ([{**_CHECKOUT, "with": {"fetch-depth": 1}}, _ACTION_STEP, _EXPORT, _GUARD], "fetch-depth is 1"),
        ([{**_CHECKOUT, "with": {"fetch-depth": "${{ x }}"}}, _ACTION_STEP, _EXPORT, _GUARD], "fetch-depth is"),
        ([{**_CHECKOUT, "with": {"fetch-depth": 0}}, _ACTION_STEP, _EXPORT, _GUARD], None),
        # #21713 review: the wiring runs whenever the guard does.
        ([_CHECKOUT, {**_ACTION_STEP, "if": _ONLY_MAIN}, _EXPORT, _GUARD], "action's `if:"),
        ([_CHECKOUT, _ACTION_STEP, {**_EXPORT, "if": _ONLY_MAIN}, _GUARD], "export step's `if:"),
        (
            [
                _CHECKOUT,
                {**_ACTION_STEP, "if": "inputs.x"},
                {**_EXPORT, "if": "inputs.x"},
                {**_GUARD, "if": "inputs.x"},
            ],
            None,
        ),
    ],
)
def test_the_wiring_check_on_fixtures(steps, gap) -> None:
    found = wiring_gap(steps, _READERS, repo_root())
    assert (found is None) if gap is None else (found is not None and gap in found), found


@pytest.mark.parametrize(
    ("on", "reached"),
    [
        ({"pull_request": None}, True),
        ({"pull_request": {"branches": ["release", "main"]}}, True),
        ({"pull_request": {"branches": ["main"]}}, False),
        ({"pull_request": {"branches-ignore": ["release"]}}, False),
        ({"workflow_call": {"inputs": {}}}, True),
        ({"push": {"branches": ["main"]}, "workflow_dispatch": None}, False),
        ("pull_request", True),
    ],
)
def test_which_workflows_a_release_pr_reaches(on, reached) -> None:
    assert release_prs_reach({True: on}) is reached
