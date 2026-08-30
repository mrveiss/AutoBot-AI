#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The per-root collection floor must not be satisfiable by nothing (#15161).

The defect it exists for was an *absence* reading as a presence:
`autobot-infrastructure/shared/tests` was a declared CI root whose conftest
raised ImportError, so it contributed zero tests while every report above it
was green. A guard against that shape is worthless if it can itself inspect
nothing and pass, so most of these cases feed it exactly that and assert it
fails.

Two halves, and both are needed:

* **The logic.** Node-id extraction, longest-prefix attribution, and every
  refusal in `check`.
* **The wiring.** A guard that is correct and unreferenced guards nothing. The
  last class asserts `marker-tests.yml` actually runs the script, and that it
  runs it with no root list of its own — the roots must stay derived from the
  workflow, or a root added there would go unchecked.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "marker-tests.yml"
SCRIPT = Path(__file__).with_name("pytest_root_collection_floor.py")

_MODULE_NAME = "pytest_root_collection_floor"


def _load_script():
    """Load the checker, leaving no ``sys.modules`` entry behind.

    Same idiom as this directory's other guard tests — the repo-wide
    sys.modules leak guard (#13337) fails a shard that strands a synthetic
    entry, and a sibling import via ``sys.path`` would strand one.
    """
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, SCRIPT)
    assert spec is not None and spec.loader is not None, f"cannot build an import spec for {SCRIPT}"
    module = importlib.util.module_from_spec(spec)

    had_previous = _MODULE_NAME in sys.modules
    previous = sys.modules.get(_MODULE_NAME)
    sys.modules[_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if had_previous:
            sys.modules[_MODULE_NAME] = previous
        else:
            sys.modules.pop(_MODULE_NAME, None)
    return module


_floor = _load_script()
CollectionFloorError = _floor.CollectionFloorError
check = _floor.check
counts_by_root = _floor.counts_by_root
nodeids = _floor.nodeids
roots_in = _floor.roots_in
workflow_roots = _floor.workflow_roots


def _result(stdout: str = "", returncode: int = 0, stderr: str = ""):
    """A stand-in for the CompletedProcess `collect()` returns."""
    return subprocess.CompletedProcess(args=["pytest"], returncode=returncode, stdout=stdout, stderr=stderr)


HEALTHY = (
    "libs/autobot-sdk-python/tests/test_integration.py::test_a\n"
    "autobot-infrastructure/shared/tests/distributed/test_db_initialization.py::TestX::test_b\n"
)


class TestNodeIdExtraction:
    """Everything downstream is a count of these, so a miss here empties the check."""

    def test_a_plain_node_id_is_read(self):
        assert nodeids("pkg/test_a.py::test_x\n") == ["pkg/test_a.py::test_x"]

    def test_a_class_qualified_node_id_is_read(self):
        assert nodeids("pkg/test_a.py::TestX::test_y\n") == ["pkg/test_a.py::TestX::test_y"]

    def test_the_summary_line_is_not_counted_as_a_test(self):
        assert nodeids("2/2 tests collected in 0.12s\n") == []

    def test_an_error_block_is_not_counted_as_a_test(self):
        noise = "ERROR pkg/test_a.py - ImportError: cannot import name 'x'\n=== 1 error in 0.10s ===\n"
        assert nodeids(noise) == []

    def test_the_tree_form_is_not_mistaken_for_node_ids(self):
        """Verbosity >= 0 prints `<Module ...>`; reading it as items would fake a pass."""
        assert nodeids("<Module test_a.py>\n  <Function test_x>\n") == []


class TestAttribution:
    def test_items_land_on_the_root_that_contains_them(self):
        tally = counts_by_root(nodeids(HEALTHY), ["libs", "autobot-infrastructure/shared/tests"])
        assert tally == {"libs": 1, "autobot-infrastructure/shared/tests": 1}

    def test_a_root_with_no_items_counts_zero_rather_than_vanishing(self):
        assert counts_by_root(nodeids(HEALTHY), ["libs", "tools"])["tools"] == 0

    def test_the_longest_matching_root_wins(self):
        """A nested root must not have its items absorbed by its parent."""
        collected = ["libs/sdk/tests/test_a.py::test_x"]
        assert counts_by_root(collected, ["libs", "libs/sdk"]) == {"libs": 0, "libs/sdk": 1}

    def test_a_sibling_prefix_does_not_match(self):
        """`libs` must not claim `libs-extra/...` on a bare string prefix."""
        assert counts_by_root(["libs-extra/test_a.py::test_x"], ["libs"]) == {"libs": 0}


class TestTheCheckRefuses:
    def test_a_root_that_collects_nothing_fails(self):
        """The #15161 shape itself: a declared root contributing zero."""
        with pytest.raises(CollectionFloorError, match="collect NO tests"):
            check(_result(HEALTHY), ["libs", "autobot-infrastructure/shared/tests", "tools"])

    def test_it_names_the_empty_root(self):
        with pytest.raises(CollectionFloorError) as raised:
            check(_result(HEALTHY), ["libs", "autobot-infrastructure/shared/tests", "tools"])
        assert "tools" in str(raised.value)

    def test_an_empty_root_list_fails_rather_than_passing_vacuously(self):
        with pytest.raises(CollectionFloorError, match="inspect"):
            check(_result(HEALTHY), [])

    def test_a_pytest_that_could_not_start_fails(self):
        with pytest.raises(CollectionFloorError, match="usage error"):
            check(_result("", returncode=4, stderr="unrecognized arguments"), ["libs"])

    def test_collecting_nothing_at_all_fails(self):
        with pytest.raises(CollectionFloorError, match="no test at all"):
            check(_result("no tests ran\n"), ["libs"])

    def test_the_healthy_case_passes_and_reports_counts(self):
        """Without this the class above would be satisfied by a check that always raises."""
        assert check(_result(HEALTHY), ["libs", "autobot-infrastructure/shared/tests"]) == {
            "libs": 1,
            "autobot-infrastructure/shared/tests": 1,
        }

    def test_a_collection_error_alongside_real_items_is_not_this_check_s_failure(self):
        """Owned by the workflow's own pytest steps; see the script's docstring."""
        assert check(_result(HEALTHY, returncode=2), ["libs", "autobot-infrastructure/shared/tests"])


class TestRootDerivation:
    def test_an_option_value_is_not_read_as_a_root(self, tmp_path):
        (tmp_path / "auto").mkdir()
        assert roots_in(["-n", "auto", "repo_tests"], tmp_path) == []

    def test_a_path_that_does_not_exist_is_not_read_as_a_root(self, tmp_path):
        assert roots_in(["ghost_tree"], tmp_path) == []

    def test_the_real_workflow_yields_its_roots(self):
        derived = workflow_roots(WORKFLOW)
        assert "autobot-infrastructure/shared/tests" in derived, (
            "the root #15161 is about is no longer derived from marker-tests.yml, so the "
            "floor would stop checking the very tree it was written for"
        )
        assert "autobot-backend" in derived

    @staticmethod
    def _command_tokens(run: str) -> list[str]:
        """A step's shell, with comments removed, as whitespace tokens.

        #15051: comments MUST go before tokenising. This parse used to take the
        first bare `pytest` token in the block, which a comment mentioning
        pytest -- and naming a step called "... infrastructure, libs and
        frontend" -- put ahead of the real command. `libs` was then read as the
        first root out of PROSE, and this check went red against a workflow that
        was correct. The script it cross-checks never had the bug: it anchors on
        the literal `python -m pytest`, which no comment produces.
        """
        without_comments = "\n".join(
            line for line in run.splitlines() if not line.lstrip().startswith("#")
        )
        return without_comments.replace("\\\n", " ").split()

    @staticmethod
    def _invocation_starts(tokens: list[str]) -> list[int]:
        """Index just past each `python -m pytest`, matching the script's own anchor.

        The three-token sequence, not a bare `pytest`: `pip install pytest ...`
        in the dependency step is not an invocation and names no roots.
        """
        return [
            index + 3
            for index in range(len(tokens) - 2)
            if tokens[index : index + 3] == ["python", "-m", "pytest"]
        ]

    def test_the_derivation_agrees_with_an_independent_yaml_parse(self):
        """The script reads the raw text; this reads the YAML. A regex that quietly
        stopped matching an invocation would narrow the check without any failure."""
        job = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["marker-tests"]
        expected: list[str] = []
        for step in job["steps"]:
            tokens = self._command_tokens(step.get("run", ""))
            for start in self._invocation_starts(tokens):
                for root in roots_in(tokens[start:], REPO_ROOT):
                    if root not in expected:
                        expected.append(root)
        assert expected, "this comparison parsed no invocation, so it compares nothing"
        assert workflow_roots(WORKFLOW) == expected

    def test_a_comment_naming_pytest_does_not_become_a_root(self):
        """The exact #15051 regression, pinned: prose must not feed the parse."""
        run = (
            "          # these run in no pytest invocation -- see 'infrastructure, libs\n"
            "          # and frontend' below\n"
            "          python -m pytest repo_tests -n auto\n"
        )
        tokens = self._command_tokens(run)
        assert "libs" not in tokens, "comment text survived the strip and can still be read as a root"
        starts = self._invocation_starts(tokens)
        assert starts == [3], f"expected one invocation anchored at the command, got {starts}"
        assert roots_in(tokens[starts[0]:], REPO_ROOT) == ["repo_tests"]

    def test_a_pip_install_line_is_not_read_as_an_invocation(self):
        """`pip install pytest ...` names packages, not roots."""
        tokens = self._command_tokens("          pip install pytest pytest-asyncio libs\n")
        assert self._invocation_starts(tokens) == []


class TestTheGuardIsWired:
    @pytest.fixture(scope="class")
    def run_steps(self) -> list[str]:
        job = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["marker-tests"]
        return [step["run"] for step in job["steps"] if "run" in step]

    def test_the_workflow_runs_the_script(self, run_steps):
        assert any(
            SCRIPT.name in run for run in run_steps
        ), f"marker-tests.yml no longer runs {SCRIPT.name} — the per-root floor is correct and guarding nothing"

    def test_the_workflow_passes_it_no_root_list(self, run_steps):
        """Roots must stay derived. A hand-written list there would go stale silently."""
        for run in run_steps:
            if SCRIPT.name not in run:
                continue
            tokens = run.replace("\\\n", " ").split()
            after = tokens[tokens.index(next(t for t in tokens if t.endswith(SCRIPT.name))) + 1 :]
            assert not [t for t in after if not t.startswith("-")], (
                f"marker-tests.yml passes explicit roots to {SCRIPT.name}: {after}. "
                "The roots must be derived from the workflow, not listed twice."
            )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
