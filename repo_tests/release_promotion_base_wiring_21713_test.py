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

from tools.lint import _parse_cache as parse_cache
from tools.lint._comment_syntax import code_text

_REPO_TESTS = "repo_tests"
# Root-relative, so the glob names the tree it reads (`.yml` and `.yaml`); actionlint.yml runs this guard
# on every change to that tree, the record's dedicated-workflow route (#21713).
_WORKFLOW_FILES = ".github/workflows/*.y*ml"
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
    ("actionlint.yml", "promotion-base-wiring"),
}


def _import_from(node: ast.ImportFrom, package: tuple[str, ...]) -> set[str]:
    """Candidate module names one ``from`` import reaches: the module and each ``module.name`` submodule."""
    mod = node.module or ""
    if node.level == 0:
        if mod != "repo_tests" and not mod.startswith("repo_tests."):
            return set()
        base = mod.removeprefix("repo_tests").strip(".")
    else:  # package-relative: `.` is the importer's own package, each further dot one level up
        up = node.level - 1
        parts = package[: len(package) - up] if up <= len(package) else ()
        base = ".".join((*parts, *([mod] if mod else [])))
    names = {f"{base}.{a.name}" if base else a.name for a in node.names}
    return names | ({base} if base else set())


def _imported(tree: ast.AST, package: tuple[str, ...] = ()) -> set[str]:
    """repo_tests module names (dotted, relative to the package) this module imports."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.removeprefix("repo_tests.") for a in node.names if a.name.startswith("repo_tests.")}
        elif isinstance(node, ast.ImportFrom):
            out |= _import_from(node, package)
    return out


def _module_imports(root: Path) -> dict[str, set[str]]:
    graph = {}
    tests = root / _REPO_TESTS
    for path in tests.rglob("*.py"):
        parts = path.relative_to(tests).with_suffix("").parts
        package = parts[:-1]
        graph[".".join(parts)] = _imported(parse_cache.parse(path.read_text(encoding="utf-8"), str(path)), package)
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


def _listed(script: str, root: Path) -> str:
    """The text of tracked guard lists the script feeds to pytest (ci.yml's short-check reads one)."""
    names = re.findall(r"(?<![\w/.-])([\w./-]+\.txt)\b", script)
    return "\n".join(code_text(root / n, strip_trailing=True) for n in names if (root / n).is_file())


def runs_base_reader(step: dict, readers: set[str], root: Path) -> bool:
    """True when the step's script runs pytest on a guard that reads the ratchet base."""
    # A `run:` body is a bash script; the shared comment syntax reads it as one (#21713).
    script = code_text(str(step.get("run", "")), name="run.sh", strip_trailing=True)
    if "pytest" not in script:
        return False
    text = script + "\n" + _listed(script, root)
    return any(_targets_base_reader(m.group(1), readers) for m in _TOKEN.finditer(text))


def _matches_release(patterns) -> bool:
    """GitHub filter semantics: patterns apply in order, a later ``!`` pattern excludes and a later
    positive one re-includes (#21713 review)."""
    matched = False
    for pattern in patterns or []:
        negated = pattern.startswith("!")
        if fnmatch.fnmatchcase(RELEASE, pattern.removeprefix("!")):
            matched = not negated
    return matched


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
    """The step that exports AUTOBOT_RATCHET_BASE_SHA from an env var led by *output* (the whole
    name, not a longer one), so the exported variable is the one carrying the action's output (#21713)."""
    leads = re.compile(r"\$\{\{\s*" + re.escape(output) + r"(?![\w.-])")
    for i, step in enumerate(steps):
        run = str(step.get("run", ""))
        if "GITHUB_ENV" not in run:
            continue
        for var, value in (step.get("env") or {}).items():
            exported = re.search(
                r"AUTOBOT_RATCHET_BASE_SHA=\"?\$(?:\{" + re.escape(var) + r"\}|" + re.escape(var) + r"(?!\w))",
                run,
            )
            if leads.match(str(value).strip()) and exported:
                return i
    return None


def wiring_gap(steps: list[dict], readers: set[str], root: Path) -> str | None:
    """Why this job's base-reading guard would read the release tip, or None when it is wired."""
    first = next((i for i, s in enumerate(steps) if runs_base_reader(s, readers, root)), None)
    if first is None:
        return None
    action = next(
        (i for i, s in enumerate(steps[:first]) if s.get("uses") == ACTION and s.get("id")),
        None,
    )
    if action is None:
        return f"no `uses: {ACTION}` with an id before the guard step"
    gap = _checkout_gap([s for s in steps[:action] if "actions/checkout" in str(s.get("uses", ""))])
    if gap:
        return gap
    output = f"steps.{steps[action]['id']}.outputs.base-sha"
    export = _export_index(steps[action + 1 : first], output)
    if export is None:
        return f"no step between the action and the guard exports AUTOBOT_RATCHET_BASE_SHA from {output}"
    for guard in (s for s in steps[first:] if runs_base_reader(s, readers, root)):
        gap = _condition_gap(steps[action], guard, "action") or _condition_gap(
            steps[action + 1 + export], guard, "export step"
        )
        if gap:
            return gap
    return None


def _jobs_in_scope(root: Path) -> list[tuple[str, str, str | None]]:
    """(workflow, job, wiring gap) for every job a PR into release runs that runs a base-reading guard."""
    readers = base_readers(_module_imports(root))
    found = []
    for path in sorted(root.glob(_WORKFLOW_FILES)):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not release_prs_reach(doc):
            continue
        for name, job in (doc.get("jobs") or {}).items():
            steps = job.get("steps") or []
            if any(runs_base_reader(s, readers, root) for s in steps):
                found.append((path.name, name, wiring_gap(steps, readers, root)))
    return found


# Pinned while this guard is new: the base it would compute a floor from has no such declaration
# (#19676). The live population is the seven jobs in KNOWN_IN_SCOPE.
REACH = declare(
    "release-promotion-base-wiring-21713",
    discover=_jobs_in_scope,
    what="workflow jobs a pull request into release runs that run a base-reading guard",
    floor=7,
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
        # #21713: a longer output name is not the action's base-sha.
        (
            [
                _CHECKOUT,
                _ACTION_STEP,
                {
                    **_EXPORT,
                    "env": {"EVENT_BASE": "${{ steps.release-base.outputs.base-sha-old }}"},
                },
                _GUARD,
            ],
            "exports AUTOBOT_RATCHET_BASE_SHA",
        ),
        ([_CHECKOUT, _GUARD, _ACTION_STEP, _EXPORT], "no `uses:"),
        ([_ACTION_STEP, _CHECKOUT, _EXPORT, _GUARD], "before any checkout"),
        ([_CHECKOUT, _ACTION_STEP, _EXPORT, _GUARD], None),
        ([_CHECKOUT, {"run": "python3 -m pytest repo_tests/other_test.py"}], None),
        (
            [_CHECKOUT, {"run": "python -m pytest autobot-backend repo_tests -q"}],
            "no `uses:",
        ),
        # #21713 review: a plugin module argument is not the repo_tests root.
        (
            [
                _CHECKOUT,
                {"run": "python -m pytest autobot-backend -p repo_tests.stable_shard -q"},
            ],
            None,
        ),
        # #21713 review: the HEAD^1 fallback needs a parent in the checkout.
        ([_SHALLOW, _ACTION_STEP, _EXPORT, _GUARD], "fetch-depth is 1"),
        (
            [{**_CHECKOUT, "with": {"fetch-depth": 1}}, _ACTION_STEP, _EXPORT, _GUARD],
            "fetch-depth is 1",
        ),
        (
            [
                {**_CHECKOUT, "with": {"fetch-depth": "${{ x }}"}},
                _ACTION_STEP,
                _EXPORT,
                _GUARD,
            ],
            "fetch-depth is",
        ),
        (
            [{**_CHECKOUT, "with": {"fetch-depth": 0}}, _ACTION_STEP, _EXPORT, _GUARD],
            None,
        ),
        # #21713 review: the wiring runs whenever the guard does.
        (
            [_CHECKOUT, {**_ACTION_STEP, "if": _ONLY_MAIN}, _EXPORT, _GUARD],
            "action's `if:",
        ),
        (
            [_CHECKOUT, _ACTION_STEP, {**_EXPORT, "if": _ONLY_MAIN}, _GUARD],
            "export step's `if:",
        ),
        (
            [
                _CHECKOUT,
                {**_ACTION_STEP, "if": "inputs.x"},
                {**_EXPORT, "if": "inputs.x"},
                {**_GUARD, "if": "inputs.x"},
            ],
            None,
        ),
        # #21713 review: every base-reading guard is checked, not only the first.
        (
            [
                _CHECKOUT,
                {**_ACTION_STEP, "if": "inputs.x"},
                {**_EXPORT, "if": "inputs.x"},
                {**_GUARD, "if": "inputs.x"},
                _GUARD,
            ],
            "differs from the guard's",
        ),
        # #21713 review: the exported variable is the one carrying the action's output.
        (
            [
                _CHECKOUT,
                _ACTION_STEP,
                {
                    **_EXPORT,
                    "run": 'echo "AUTOBOT_RATCHET_BASE_SHA=wrong" >> "$GITHUB_ENV"',
                },
                _GUARD,
            ],
            "exports AUTOBOT_RATCHET_BASE_SHA",
        ),
        (
            [
                _CHECKOUT,
                _ACTION_STEP,
                {
                    **_EXPORT,
                    "env": {**_EXPORT["env"], "UNUSED": "x"},
                    "run": 'echo "AUTOBOT_RATCHET_BASE_SHA=$UNUSED" >> "$GITHUB_ENV"',
                },
                _GUARD,
            ],
            "exports AUTOBOT_RATCHET_BASE_SHA",
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
        # #21713 review: filters apply in order -- a later `!` excludes, a later positive re-includes.
        ({"pull_request": {"branches": ["*", "!release"]}}, False),
        ({"pull_request": {"branches": ["*", "!release", "release"]}}, True),
        ({"pull_request": {"branches": ["*"]}}, True),
    ],
)
def test_which_workflows_a_release_pr_reaches(on, reached) -> None:
    assert release_prs_reach({True: on}) is reached


# --- discovery fixtures: import closure, target mapping, tracked lists (positive and negative) ---


def _graph(tmp_path: Path, files: dict[str, str]) -> dict[str, set[str]]:
    for rel, text in files.items():
        path = tmp_path / _REPO_TESTS / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return _module_imports(tmp_path)


def test_the_import_closure_follows_submodule_and_relative_imports(
    tmp_path: Path,
) -> None:
    graph = _graph(
        tmp_path,
        {
            "_ratchet_base.py": "",
            "helpers/__init__.py": "",
            "helpers/base.py": "from repo_tests import _ratchet_base\n",
            "helpers/rel.py": "from .. import _ratchet_base\n",
            "a_test.py": "from repo_tests.helpers import base\n",
            "b_test.py": "from repo_tests.helpers import rel\n",
            "c_test.py": "import os\nfrom repo_tests import unrelated\n",
            "unrelated.py": "",
        },
    )
    readers = base_readers(graph)
    assert {"helpers.base", "helpers.rel", "a_test", "b_test"} <= readers
    assert not {"c_test", "unrelated"} & readers


def test_a_target_maps_to_a_reader_only_when_it_names_one() -> None:
    readers = {BASE_MODULE, "x_test", "helpers.base"}
    assert _targets_base_reader("x_test.py", readers)
    assert _targets_base_reader("helpers", readers)
    assert _targets_base_reader(None, readers)
    assert not _targets_base_reader("other_test.py", readers)


def test_a_tracked_guard_list_counts_only_active_entries(tmp_path: Path) -> None:
    (tmp_path / "guards.txt").write_text("# repo_tests/x_test.py\nrepo_tests/other_test.py\n", encoding="utf-8")
    (tmp_path / "live.txt").write_text("repo_tests/x_test.py\n", encoding="utf-8")
    step = {"run": "python -m pytest $(cat guards.txt)"}
    live = {"run": "python -m pytest $(cat live.txt)"}
    assert not runs_base_reader(step, {BASE_MODULE, "x_test"}, tmp_path)
    assert runs_base_reader(live, {BASE_MODULE, "x_test"}, tmp_path)
