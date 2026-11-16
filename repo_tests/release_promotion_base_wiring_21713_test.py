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

import pytest
import yaml
from repo_tests._paths import repo_root

REPO_TESTS = repo_root() / "repo_tests"
WORKFLOWS = repo_root() / ".github" / "workflows"
ACTION = "./.github/actions/release-promotion-base"
RELEASE = "release"
BASE_MODULE = "_ratchet_base"
# A `repo_tests` token in a run script: the bare root, or a path under it.
_TOKEN = re.compile(r"(?<![\w/.-])repo_tests(?:/([\w./-]+))?(?![\w-])")
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


def _module_imports() -> dict[str, set[str]]:
    graph = {}
    for path in REPO_TESTS.rglob("*.py"):
        name = ".".join(path.relative_to(REPO_TESTS).with_suffix("").parts)
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


def _listed(script: str) -> str:
    """The text of tracked guard lists the script feeds to pytest (ci.yml's short-check reads one)."""
    names = re.findall(r"(?<![\w/.-])([\w./-]+\.txt)\b", script)
    return "\n".join(
        _uncommented((repo_root() / n).read_text(encoding="utf-8")) for n in names if (repo_root() / n).is_file()
    )


def runs_base_reader(step: dict, readers: set[str]) -> bool:
    """True when the step's script runs pytest on a guard that reads the ratchet base."""
    script = _uncommented(str(step.get("run", "")))
    if "pytest" not in script:
        return False
    text = script + "\n" + _listed(script)
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


def wiring_gap(steps: list[dict], readers: set[str]) -> str | None:
    """Why this job's base-reading guard would read the release tip, or None when it is wired."""
    first = next((i for i, s in enumerate(steps) if runs_base_reader(s, readers)), None)
    if first is None:
        return None
    action = next(
        (i for i, s in enumerate(steps[:first]) if s.get("uses") == ACTION and s.get("id")),
        None,
    )
    if action is None:
        return f"no `uses: {ACTION}` with an id before the guard step"
    if not any("actions/checkout" in str(s.get("uses", "")) for s in steps[:action]):
        return "the local action runs before any checkout"
    output = f"steps.{steps[action]['id']}.outputs.base-sha"
    for step in steps[action + 1 : first]:
        env_refs = any(str(v).replace("${{", "").strip().startswith(output) for v in (step.get("env") or {}).values())
        run = str(step.get("run", ""))
        if env_refs and "AUTOBOT_RATCHET_BASE_SHA=" in run and "GITHUB_ENV" in run:
            return None
    return f"no step between the action and the guard exports AUTOBOT_RATCHET_BASE_SHA from {output}"


def _scan() -> tuple[set[tuple[str, str]], list[str]]:
    readers = base_readers(_module_imports())
    in_scope, gaps = set(), []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not release_prs_reach(doc):
            continue
        for name, job in (doc.get("jobs") or {}).items():
            steps = job.get("steps") or []
            if any(runs_base_reader(s, readers) for s in steps):
                in_scope.add((path.name, name))
                gap = wiring_gap(steps, readers)
                if gap:
                    gaps.append(f"{path.name}:{name}: {gap}")
    return in_scope, gaps


def test_every_base_reading_job_a_release_pr_runs_takes_the_promotion_base() -> None:
    in_scope, gaps = _scan()
    missing = KNOWN_IN_SCOPE - in_scope
    assert not missing, f"the detector lost jobs it must see (instrument check): {sorted(missing)}"
    assert not gaps, (
        "these jobs run a base-reading guard on PRs into release without the #19466 base, so it "
        "reads the release tip and raises BaseUnavailable (#21713). Add the two steps ci.yml uses "
        f"(`uses: {ACTION}` + `Ratchet base (#19283)`):\n" + "\n".join(gaps)
    )


def test_the_closure_reaches_the_guard_that_failed_on_the_promotion_pr() -> None:
    readers = base_readers(_module_imports())
    assert {"_reach", "docs_liquid_tags_are_defined_17930_test"} <= readers


# --- fixtures: the checker on synthetic workflows (positive and negative) -----------------------

_READERS = {BASE_MODULE, "_reach", "x_test"}
_CHECKOUT = {"uses": "actions/checkout@v7"}
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
    ],
)
def test_the_wiring_check_on_fixtures(steps, gap) -> None:
    found = wiring_gap(steps, _READERS)
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
