# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-board lane runs the test files a head adds or changes, and fails when they fail (#21509, #18499).

A member's own new tests used to execute for the first time inside the merge train. The ``own-tests`` job of
``dispatch-preboard-guards.yml`` runs them first, with the suite's xdist options. This file holds:

* the selection (``changed-tests``) on synthetic path lists: which file goes to which interpreter, which is
  left to the guard shards, which the suite never collects, and that a deleted file is not selected;
* the verdict: a failed, cancelled or missing ``own-tests`` job is not boardable;
* the workflow: the job exists, merges the pinned base, runs the suite's options, takes its files from the
  selection and names no test root, and the result job needs it.

What it does not cover: no lane run is dispatched here, so that a failing own test turns the lane red is
proved by the first lane run on a real member (the last criterion of #21509).
"""

from __future__ import annotations

import json
import shlex
from typing import Any

import pytest
import yaml
from repo_tests import _preboard_guard_lane_support as support
from repo_tests._paths import repo_root

_ROOT = repo_root()
_WORKFLOW = _ROOT / ".github" / "workflows" / "dispatch-preboard-guards.yml"
_SUITE = _ROOT / ".github" / "workflows" / "ci.yml"
_PATTERNS = ["test_*.py", "*_test.py"]
_HEAD = "a" * 40


@pytest.fixture(scope="module")
def lane():
    yield from support.load_lane()


@pytest.fixture(scope="module")
def jobs() -> dict[str, Any]:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))["jobs"]


@pytest.mark.parametrize(
    "path,group",
    [
        ("autobot-backend/services/foo_test.py", "main"),
        ("autobot-backend/api/test_bar.py", "main"),
        ("autobot-tts-worker/engine_test.py", "main"),
        ("libs/autobot-sdk-python/tests/test_x.py", "main"),
        ("plugins/core-plugins/a/b_test.py", "main"),
        ("autobot-slm-backend/services/foo_test.py", "slm"),
        ("repo_tests/foo_test.py", "guarded"),
        ("autobot_shared/x_test.py", "guarded"),
        ("pipeline-scripts/y_test.py", "guarded"),
        ("autobot-slm-backend/ansible/roles/z_test.py", "uncollected"),
        ("some-new-tree/z_test.py", "uncollected"),
        ("autobot-backend/services/foo.py", None),
        ("autobot-backend/services/conftest.py", None),
        ("autobot-backend/services/foo_test.txt", None),
        ("autobot-backend/services/testing_helpers.py", None),
    ],
)
def test_a_changed_file_goes_to_the_session_that_owns_it(lane, path, group) -> None:
    assert lane.group_of(path, _PATTERNS) == group


def test_the_collection_patterns_are_the_ones_pytest_ini_declares(lane) -> None:
    assert lane.python_file_patterns(_ROOT) == _PATTERNS


def test_only_files_that_still_exist_are_selected_and_each_once(lane) -> None:
    paths = ["autobot-backend/a_test.py", "autobot-backend/a_test.py", "autobot-backend/gone_test.py", "README.md"]
    groups = lane.select_own_tests(paths, _PATTERNS, lambda p: not p.endswith("gone_test.py"))
    assert groups["main"] == ["autobot-backend/a_test.py"]
    assert set(groups) == set(lane.OWN_GROUPS)
    assert not groups["slm"] and not groups["guarded"] and not groups["uncollected"]


def test_the_groups_cover_every_test_root_exactly_once(lane) -> None:
    runs = set(lane.OWN_TEST_ROOTS) | {lane.SLM_ROOT}
    assert runs == set(lane.PRODUCT_ROOTS), "a product root is run by neither own-tests session"
    assert not runs & set(lane.GUARD_ROOTS), "a root is run twice"


def test_the_selection_is_written_one_file_per_group_with_counts(lane, tmp_path, monkeypatch) -> None:
    (tmp_path / "autobot-backend").mkdir()
    (tmp_path / "autobot-backend" / "a_test.py").write_text("", encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\npython_files = test_*.py *_test.py\n", encoding="utf-8")
    changed = ["autobot-backend/a_test.py", "repo_tests/x_test.py"]
    monkeypatch.setattr(lane, "changed_paths", lambda base, head: changed)
    counts = lane.write_own_tests(tmp_path, _HEAD, _HEAD, tmp_path / "out")
    assert counts == {"main": 1, "slm": 0, "guarded": 0, "uncollected": 0}
    assert (tmp_path / "out" / "main.txt").read_text(encoding="utf-8") == "autobot-backend/a_test.py\n"
    assert (tmp_path / "out" / "slm.txt").read_text(encoding="utf-8") == ""


def test_an_empty_selection_says_so_and_selects_nothing(lane, tmp_path, monkeypatch, capsys) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\npython_files = test_*.py *_test.py\n", encoding="utf-8")
    monkeypatch.setattr(lane, "changed_paths", lambda base, head: ["docs/a.md"])
    monkeypatch.chdir(tmp_path)
    argv = ["changed-tests", "--base-sha", _HEAD, "--head-sha", _HEAD, "--out-dir", str(tmp_path / "o")]
    assert lane.main(argv) == 0
    captured = capsys.readouterr()
    assert "main=0" in captured.out and "slm=0" in captured.out
    assert "no changed test files" in captured.err


def test_a_commit_that_is_not_a_full_id_is_refused(lane) -> None:
    with pytest.raises(SystemExit):
        lane.changed_paths("main", _HEAD)


def _green_shards() -> list[dict[str, Any]]:
    return [support.shard(1, 1, 0, support.passing("repo_tests/m_test.py", 9))]


@pytest.mark.parametrize(
    "own,expected", [("success", "green"), ("failure", "red"), ("skipped", "red"), ("cancelled", "cancelled")]
)
def test_the_own_tests_job_decides_the_lane(lane, tmp_path, own, expected) -> None:
    needs = json.dumps({"guards": {"result": "success"}, "own-tests": {"result": own}, "types": {"result": "success"}})
    result = support.verdict(lane, tmp_path, _green_shards(), NEEDS_JSON=needs)
    assert result["overall"] == expected and result["checks"]["own_tests"]["status"] == own


def test_a_needs_without_the_own_tests_job_is_red(lane, tmp_path) -> None:
    needs = json.dumps({"guards": {"result": "success"}, "types": {"result": "success"}})
    result = support.verdict(lane, tmp_path, _green_shards(), NEEDS_JSON=needs)
    assert result["overall"] == "red" and result["checks"]["own_tests"]["status"] == "missing"


def _runs(job: dict[str, Any]) -> str:
    return "\n".join(s["run"] for s in job["steps"] if "run" in s)


def test_the_result_job_needs_own_tests_and_the_job_merges_the_pinned_base(jobs) -> None:
    assert "own-tests" in jobs["result"]["needs"] and jobs["own-tests"]["needs"] == ["pin"]
    assert "timeout-minutes" in jobs["own-tests"]
    assert 'merge --base-sha "$PINNED_BASE_SHA"' in _runs(jobs["own-tests"])
    assert jobs["own-tests"]["steps"][1]["with"] == {"python-version-file": ".python-version"}


_FILES_ARG = '"${FILES[@]}"'
#: Options own-tests uses that take a separate value, and flags that take none. An option outside both
#: (and not ``--name=value``) fails the parse, so a new one has to be classified here.
_VALUE_OPTIONS = {"-n", "--dist", "-m", "-o"}
_FLAG_OPTIONS = {"-q", "-rs"}
_PYTEST_NAMES = {"pytest", "py.test"}
_SHELL_ENDS = {"||", "&&", ";", "|"}


def _lines(script: str) -> list[list[str]]:
    """Each logical line of *script* as tokens, quotes kept (so a quoted array expansion stays recognisable)."""
    joined = script.replace("\\\n", " ")
    lines = [line for line in joined.splitlines() if line.strip() and not line.strip().startswith("#")]
    return [shlex.split(line, posix=False) for line in lines]


def _positionals(tokens: list[str]) -> list[str]:
    """Every non-option token of one invocation, skipping option values; an unclassified option fails."""
    found: list[str] = []
    i = 0
    while i < len(tokens) and tokens[i] not in _SHELL_ENDS:
        token = tokens[i]
        if token in _VALUE_OPTIONS:
            i += 1
        elif token.startswith("--") and "=" in token or token in _FLAG_OPTIONS:
            pass
        elif token.startswith("-"):
            raise AssertionError(f"option {token!r} is not classified in the own-tests guard")
        else:
            found.append(token)
        i += 1
    return found


def _pytest_positionals(script: str) -> list[str]:
    """The positional arguments of every ``pytest`` / ``py.test`` / ``-m pytest`` invocation in *script*."""
    found: list[str] = []
    for tokens in _lines(script):
        for i, token in enumerate(tokens):
            if token in _PYTEST_NAMES:
                found += _positionals(tokens[i + 1 :])
    return found


def _not_the_selection(script: str) -> list[str]:
    """The pytest arguments that are not exactly the literal array expansion of the selection list."""
    return [a for a in _pytest_positionals(script) if a != _FILES_ARG]


def test_own_tests_takes_its_files_from_the_selection_and_names_no_root(jobs) -> None:
    body = _runs(jobs["own-tests"])
    assert "preboard_guard_lane.py changed-tests" in body and "main.txt" in body and "slm.txt" in body
    assert _pytest_positionals(body) == [_FILES_ARG, _FILES_ARG], "each session takes exactly its selection list"
    assert not _not_the_selection(body)
    assert any(s.get("id") == "suite" for s in jobs["own-tests"]["steps"]), "the SLM step reads the suite step's output"


_CLEAN = (
    "python3 pipeline-scripts/preboard_guard_lane.py changed-tests --out-dir o\n" 'python -m pytest "${FILES[@]}" -q\n'
)


@pytest.mark.parametrize(
    "script,bad",
    [
        ("python -m pytest repo_tests \\\n  -n auto -q\n", ["repo_tests"]),
        ('python -m pytest "${FILES[@]}" repo_tests\n', ["repo_tests"]),
        ('python -m pytest "${FILES[@]}" -n auto repo_tests\n', ["repo_tests"]),
        ("pytest repo_tests\n", ["repo_tests"]),
        ("py.test autobot-backend/\n", ["autobot-backend/"]),
        ('python -m pytest "$ROOT" -q\n', ['"$ROOT"']),
        ("python -m pytest ${FILES[@]} -q\n", ["${FILES[@]}"]),
        ("python -m pytest autobot-slm-backend/services/x_test.py -q\n", ["autobot-slm-backend/services/x_test.py"]),
    ],
)
def test_a_pytest_argument_other_than_the_selection_is_caught_but_the_script_path_is_not(script, bad) -> None:
    assert not _not_the_selection(_CLEAN)
    assert _not_the_selection(script) == bad


def test_an_option_nobody_classified_fails_the_parse() -> None:
    with pytest.raises(AssertionError, match="not classified"):
        _pytest_positionals('python -m pytest "${FILES[@]}" --maxfail 1\n')


def test_own_tests_runs_with_the_suites_xdist_and_marker_options(jobs) -> None:
    suite = yaml.safe_load(_SUITE.read_text(encoding="utf-8"))["jobs"]["python-shard"]
    marker = '-m "not integration and not slow and not distributed and not performance"'
    suite_run = next(s["run"] for s in suite["steps"] if "--shard-durations .test_durations \\" in s.get("run", ""))
    own = _runs(jobs["own-tests"])
    assert marker in suite_run and own.count(marker) == 2, "the marker selection differs from the suite's"
    assert own.count("-n auto --dist loadscope") == 2 and "-n auto --dist loadscope" in suite_run
    assert "stable_shard" not in own and "--shard-" not in own, "a shard plugin would drop the selected files"
    assert "-x" not in own.split() and "--maxfail" not in own


def test_the_slm_files_run_under_the_slm_interpreter_the_suite_uses(jobs) -> None:
    step = next(s for s in jobs["own-tests"]["steps"] if s.get("name", "").endswith("slm-backend"))
    assert step["env"]["SLM_PYTHON"] == "${{ steps.suite.outputs.slm-venv }}/bin/python"
    assert '"$SLM_PYTHON" -m pytest' in step["run"]
    assert "steps.suite.outcome == 'success'" in step["if"]
