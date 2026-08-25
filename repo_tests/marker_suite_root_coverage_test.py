#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every marker-carrying test must be named by a marker-tests.yml root (#13286).

`ci.yml` runs the Python suite with
`-m "not integration and not slow and not distributed and not performance"`, so
a test carrying one of those markers runs ONLY if some other invocation selects
it back in. `.github/workflows/marker-tests.yml` is that other invocation — but
selecting a marker is not enough on its own: pytest also has to be pointed at
the tree the test lives in.

That second half is what went missing. `autobot-infrastructure/shared/tests` and
`libs` were named by no pytest invocation in any workflow, so 12 marker-carrying
tests there were selected by *nothing*, while the workflow that exists to run
marker-carrying tests reported green. A workflow whose roots do not cover its
own population is the defect this repository keeps meeting: a check that reads
as a verdict on the whole set while looking at part of it.

Both ends are derived, never listed:

* the population comes from the git index, parsed with `ast` (module-level
  ``pytestmark``, class decorators and function decorators all count);
* the roots and the per-invocation floors come from the workflow itself.

So a tree renamed at either end breaks a test instead of quietly shrinking what
is checked, and `TestTheScannerCanSee` keeps "found nothing outside the roots"
distinguishable from "looks at nothing".
"""

from __future__ import annotations

import ast
import configparser
import subprocess  # nosec B404
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "marker-tests.yml"

# The markers ci.yml deselects. Kept here as the subject of the test, and
# cross-checked against the workflow's own selection expression below so the two
# cannot drift apart silently.
SELECTION_MARKERS = ("integration", "slow", "distributed", "performance")


def _marker_of(decorator: ast.expr) -> str | None:
    """``pytest.mark.NAME`` (called or not) -> ``NAME``; anything else -> None."""
    node = decorator.func if isinstance(decorator, ast.Call) else decorator
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    parts.reverse()
    if len(parts) >= 3 and parts[0] == "pytest" and parts[1] == "mark":
        return parts[2]
    return None


def _module_level_markers(tree: ast.Module) -> set[str]:
    """Markers applied to the whole module through ``pytestmark``."""
    found: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            continue
        value = node.value
        elements = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
        found |= {name for element in elements if (name := _marker_of(element))}
    return found


def _decorator_markers(tree: ast.Module) -> set[str]:
    """Markers applied to any class or test function in the module."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            found |= {name for d in node.decorator_list if (name := _marker_of(d))}
    return found


def markers_in(source: str) -> set[str]:
    """Every ``pytest.mark`` name a module applies, at any of the three levels."""
    tree = ast.parse(source)
    return _module_level_markers(tree) | _decorator_markers(tree)


def _test_modules() -> list[str]:
    """Test modules tracked by git, by this repository's two naming conventions.

    Filtered on the BASENAME in Python rather than by a git pathspec: `git
    ls-files 'test_*.py'` anchors the glob at the start of the path, so it
    matches only a module at the repository root and silently returned none of
    the `test_*.py` files in nested trees — which is exactly how a population
    scan comes back empty while looking like it searched.
    """
    listed = subprocess.run(  # nosec B603
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [
        path
        for path in listed.split("\0")
        if path and (Path(path).name.startswith("test_") or path.endswith("_test.py"))
    ]


def marked_modules() -> dict[str, set[str]]:
    """Tracked test modules carrying a deselected marker -> the markers they carry."""
    population: dict[str, set[str]] = {}
    for relative in _test_modules():
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        if "pytest.mark" not in source:
            continue
        carried = markers_in(source) & set(SELECTION_MARKERS)
        if carried:
            population[relative] = carried
    return population


def _command_tokens(run: str) -> list[str]:
    """A shell `run:` block flattened to tokens, continuations removed."""
    return run.replace("\\\n", " ").split()


def _roots(tokens: list[str]) -> list[str]:
    """The test roots an invocation names.

    A bare token that exists as a path and is not the value of the option before
    it — `-n auto` and `--dist loadscope` name no path, but `-m pytest` would
    read as one if the preceding option were ignored.
    """
    return [
        token
        for index, token in enumerate(tokens)
        if not token.startswith("-")
        and not (index and tokens[index - 1].startswith("-"))
        and (REPO_ROOT / token).exists()
    ]


def _junit_path(tokens: list[str]) -> str | None:
    for token in tokens:
        if token.startswith("--junitxml="):
            return token.split("=", 1)[1]
    return None


@pytest.fixture(scope="module")
def job() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["marker-tests"]


@pytest.fixture(scope="module")
def run_steps(job) -> list[str]:
    return [step["run"] for step in job["steps"] if "run" in step]


@pytest.fixture(scope="module")
def report_tokens(run_steps) -> list[str]:
    for run in run_steps:
        if "marker_suite_report.py" in run:
            return _command_tokens(run)
    pytest.fail("marker-tests.yml no longer runs marker_suite_report.py")
    return []


@pytest.fixture(scope="module")
def invocations(run_steps, report_tokens) -> dict[str, list[str]]:
    """Invocation label -> the roots it names, both read off the workflow.

    The label comes from the report step's ``NAME=report.xml`` argument matched
    to the ``--junitxml`` the pytest step writes, so renaming either end is a
    failure here rather than a silently unchecked invocation.
    """
    labels = {
        value: name for name, _, value in (token.partition("=") for token in report_tokens) if value.endswith(".xml")
    }
    mapped: dict[str, list[str]] = {}
    for run in run_steps:
        tokens = _command_tokens(run)
        if "pytest" not in tokens:
            continue
        junit = _junit_path(tokens)
        if junit is None:
            continue
        assert junit in labels, f"{junit} is written by pytest but named by no floor: {sorted(labels)}"
        mapped[labels[junit]] = _roots(tokens)
    return mapped


@pytest.fixture(scope="module")
def population() -> dict[str, set[str]]:
    return marked_modules()


class TestTheScannerCanSee:
    """Without this, "no marked module outside the roots" could mean "sees none".

    The population feeds every assertion below, so an extractor that silently
    stopped recognising a marker form would turn this whole file green while
    covering nothing — the failure mode of an allowlist emptied without an
    oracle. These cases are synthetic on purpose: they hold whatever the
    repository's own style happens to be today.
    """

    def test_a_function_decorator_is_seen(self):
        assert markers_in("import pytest\n\n@pytest.mark.slow\ndef test_x():\n    pass\n") == {"slow"}

    def test_a_class_decorator_is_seen(self):
        source = "import pytest\n\n@pytest.mark.integration\nclass TestX:\n    def test_y(self):\n        pass\n"
        assert markers_in(source) == {"integration"}

    def test_a_module_level_pytestmark_is_seen(self):
        assert markers_in("import pytest\n\npytestmark = pytest.mark.performance\n") == {"performance"}

    def test_a_module_level_list_of_marks_is_seen(self):
        source = "import pytest\n\npytestmark = [pytest.mark.distributed, pytest.mark.slow]\n"
        assert markers_in(source) == {"distributed", "slow"}

    def test_an_unrelated_decorator_is_not_seen(self):
        assert markers_in("import pytest\n\n@pytest.fixture\ndef thing():\n    pass\n") == set()

    def test_the_population_is_not_empty(self, population):
        assert population, (
            "no tracked test module carries any of "
            f"{SELECTION_MARKERS} — either the markers were all removed (in which "
            "case marker-tests.yml has nothing left to run and should be retired "
            "deliberately) or this scan has stopped seeing them"
        )


class TestRootCoverage:
    def test_the_workflow_selects_exactly_the_markers_ci_deselects(self, job):
        expression = job["env"]["MARKER_EXPRESSION"]
        missing = [marker for marker in SELECTION_MARKERS if marker not in expression]
        assert not missing, (
            f"marker-tests.yml no longer selects {missing}; those markers are deselected by "
            "ci.yml and would run in no workflow at all"
        )

    def test_every_marked_module_is_under_a_root(self, invocations, population):
        covered = [root for roots in invocations.values() for root in roots]
        orphans = sorted(
            path for path in population if not any(path == root or path.startswith(f"{root}/") for root in covered)
        )
        assert not orphans, (
            "these tracked test modules carry a marker ci.yml deselects and live under no "
            "marker-tests.yml root, so they run in NO workflow at all (#13286):\n  " + "\n  ".join(orphans)
        )

    def test_every_invocation_names_at_least_one_root(self, invocations):
        assert invocations, "no pytest invocation in marker-tests.yml writes a junit report"
        empty = sorted(name for name, roots in invocations.items() if not roots)
        assert not empty, f"these invocations name no test root that exists: {empty}"


class TestDeclaredEmptyInvocations:
    """A floor of 0 is a claim about the tree, and it has to stay true.

    `--min-collected slm=0` says `autobot-slm-backend` carries no marker-selected
    test. That is checkable, so it is checked here: the moment it gains one, this
    fails and the floor has to be raised rather than continuing to accept an empty
    result from an invocation that should now be producing one.
    """

    @staticmethod
    def _declared_zero(report_tokens: list[str]) -> set[str]:
        return {name for name, _, value in (token.partition("=") for token in report_tokens) if value == "0"}

    def _marked_under(self, roots: list[str], population: dict[str, set[str]]) -> list[str]:
        return sorted(path for path in population if any(path == root or path.startswith(f"{root}/") for root in roots))

    def test_the_declared_zeros_match_the_tree(self, report_tokens, invocations, population):
        declared = self._declared_zero(report_tokens)
        actually_empty = {name for name, roots in invocations.items() if not self._marked_under(roots, population)}
        assert declared == actually_empty, (
            "the per-invocation floors in marker-tests.yml disagree with the tree. "
            f"declared empty: {sorted(declared)}; actually empty: {sorted(actually_empty)}. "
            "An invocation that has gained marker-carrying tests must not keep a floor of 0, "
            "and one that has none must say so rather than lean on a sibling's count."
        )

    def test_a_declared_zero_names_a_real_invocation(self, report_tokens, invocations):
        unknown = sorted(self._declared_zero(report_tokens) - set(invocations))
        assert not unknown, f"floor declared for invocation(s) that do not exist: {unknown}"


class TestSdkPathDoesNotShadowTheBackend:
    """`libs/autobot-sdk-python` must stay LAST on `pythonpath` (#13286).

    It was added there so `libs/autobot-sdk-python/tests/test_integration.py`,
    which the marker suite now runs, can import `autobot_sdk` at all. But that
    directory also holds a `tests/__init__.py`, so it publishes a top-level
    `tests` package — and five backend e2e modules do `from tests.test_helpers
    import get_test_backend_url`, expecting `autobot-backend/tests`.

    pytest inserts `pythonpath` entries in declared order, so today the backend
    wins and nothing breaks. Reordering the line would silently repoint those
    imports at a package with no `test_helpers` in it, and the error would name
    the helper rather than the ini file that caused it. Hence this guard.
    """

    @staticmethod
    def _pythonpath() -> list[str]:
        parser = configparser.ConfigParser()
        parser.read(REPO_ROOT / "pytest.ini", encoding="utf-8")
        return parser["pytest"]["pythonpath"].split()

    def test_the_sdk_entry_is_present_and_last(self):
        entries = self._pythonpath()

        assert "libs/autobot-sdk-python" in entries, (
            "libs/autobot-sdk-python left pytest.ini's pythonpath — "
            "libs/autobot-sdk-python/tests/test_integration.py can no longer import autobot_sdk"
        )
        assert entries[-1] == "libs/autobot-sdk-python", (
            f"libs/autobot-sdk-python must stay last on pythonpath, got {entries}. It publishes a "
            "top-level `tests` package that would otherwise shadow autobot-backend/tests"
        )

    def test_the_backend_still_owns_the_top_level_tests_package(self):
        """Re-derived from the trees, so it cannot go stale if either moves."""
        entries = self._pythonpath()
        owners = [entry for entry in entries if (REPO_ROOT / entry / "tests" / "__init__.py").exists()]

        assert owners, "no pythonpath entry publishes a top-level `tests` package; this check inspects nothing"
        assert owners[0] == "autobot-backend", (
            f"the first pythonpath entry publishing a top-level `tests` package is {owners[0]!r}, "
            "not autobot-backend — `from tests.test_helpers import ...` now resolves elsewhere"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
