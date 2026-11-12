# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-board guard lane's workflow and roots say what its verdict claims (#21359, #18499 AC4).

``dispatch-preboard-guards.yml`` runs the suite's guard trees on a branch head merged with its base,
so a merge-train operator learns, before boarding, every guard the head would fail. A lane that is
green because it ran a different set from the one the train runs is worse than no lane: the operator
boards on its word. This file reads the workflow and the module statically:

* dispatch-only, its own concurrency group, no stop-on-first-failure, the suite's own options, no
  test root written in it, the result artifact uploaded, the types job reusing the composite action;
* the roots: one definition, every ``pytest.ini`` root either run or named as left to the suite;
* the equivalence the suite has: the base merged first, the reach audit on, the ratchet base named;
* the skip allowlist: every entry names a skip that still exists and the issue that removes it;
* the result fields documented in the workflow header.

The verdict logic is exercised on synthetic reports in ``preboard_guard_lane_verdict_21359_test.py``.
What neither covers: no run is dispatched here. It cannot be before the workflow is on the default
branch, so the first dispatched run is the end-to-end evidence.
"""

from __future__ import annotations

import ast
import re
import shlex
from pathlib import Path
from typing import Any

import pytest
import yaml
from repo_tests import _preboard_guard_lane_support as support
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import BASE_SHA_ENV
from repo_tests._reach import REACH_AUDIT_ENV

from tools.lint import _parse_cache as parse_cache
from tools.lint._comment_syntax import code_text
from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()
_LANE_WORKFLOW = _ROOT / ".github" / "workflows" / "dispatch-preboard-guards.yml"
_SUITE_WORKFLOW = _ROOT / ".github" / "workflows" / "ci.yml"
_TYPES_ACTION = "./.github/actions/generated-types-autofix"
_STOP_EARLY = ("-x", "--exitfirst", "--maxfail")
_SHARED_OPTIONS = ("-n", "--dist", "-p", "--shard-durations", "-m")
_GUARDS_STEP = "Run the guard tests of this shard"


def _workflow_files() -> list[Path]:
    """Every workflow file, enumerated through git rather than a glob of the directory."""
    return [_ROOT / rel for rel in tracked_paths(_ROOT, ".github/workflows") if rel.endswith(".yml")]


def _doc(path: Path) -> dict[str, Any]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if True in doc:
        doc["on"] = doc.pop(True)  # PyYAML reads the bare key `on` as True
    return doc


def _scripts(doc: dict[str, Any]) -> list[str]:
    return [s["run"] for job in doc["jobs"].values() for s in job.get("steps", []) if "run" in s]


def _tokens(script: str) -> list[str]:
    text = code_text(script, name="step.sh", strip_trailing=True, join_continuations=True)
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _invocation(script: str) -> list[str]:
    """The tokens after the first module-run of the test runner in *script*."""
    tokens = _tokens(script)
    for index in range(len(tokens) - 2):
        if tokens[index : index + 2] == ["-m", "pytest"]:
            return tokens[index + 2 :]
    return []


def _options(tokens: list[str]) -> dict[str, str]:
    return {o: tokens[tokens.index(o) + 1] for o in _SHARED_OPTIONS if o in tokens}


def _suite_invocation() -> list[str]:
    """The backend shard step of the suite: the one carrying the shard plugin and the backend tree."""
    steps = _doc(_SUITE_WORKFLOW)["jobs"]["python-shard"]["steps"]
    found = [_invocation(s["run"]) for s in steps if "run" in s and "--shard-durations .test_durations" in s["run"]]
    found = [tokens for tokens in found if "autobot-backend" in tokens]
    assert len(found) == 1, f"expected one backend shard invocation in the suite, found {len(found)}"
    return found[0]


def _step(workflow: dict[str, Any], job: str, name: str) -> dict[str, Any]:
    return next(s for s in workflow["jobs"][job]["steps"] if s.get("name") == name)


@pytest.fixture(scope="module")
def lane():
    yield from support.load_lane()


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    return _doc(_LANE_WORKFLOW)


# ------------------------------------------------------------------ the workflow, statically


def test_it_is_dispatch_only_so_it_never_competes_with_train_runs(workflow) -> None:
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["on"]["workflow_dispatch"]["inputs"]["base"]["default"] == "main"
    assert workflow["permissions"] == {"contents": "read", "packages": "read"}


def test_it_has_its_own_concurrency_group_and_a_unique_name(workflow) -> None:
    group = workflow["concurrency"]
    assert "github.workflow" in group["group"] and "github.ref" in group["group"]
    assert group["cancel-in-progress"] is True
    files = _workflow_files()
    assert _LANE_WORKFLOW in files and len(files) > 20, "the enumeration found too few workflows to prove a name unique"
    names = [(yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("name") for p in files]
    assert names.count(workflow["name"]) == 1, "another workflow shares this name, so they could share a group"


def test_every_job_is_bounded(workflow) -> None:
    unbounded = [name for name, job in workflow["jobs"].items() if "timeout-minutes" not in job]
    assert not unbounded, f"jobs without timeout-minutes: {unbounded}"


def test_it_reports_every_failure_and_never_stops_early(workflow) -> None:
    guards = workflow["jobs"]["guards"]
    assert guards["strategy"]["fail-fast"] is False
    invocations = [tokens for tokens in map(_invocation, _scripts(workflow)) if tokens]
    assert len(invocations) == 1, "the lane must run the test runner exactly once per shard"
    flags = [t for t in invocations[0] if t in _STOP_EARLY or t.startswith("--maxfail")]
    assert not flags, f"stop-on-first-failure options: {flags}"


def test_it_runs_the_suites_own_options_and_balances_over_its_own_roots(workflow) -> None:
    lane_options = _options([t for s in _scripts(workflow) for t in _invocation(s)])
    suite_options = _options(_suite_invocation())
    assert set(lane_options) == set(_SHARED_OPTIONS), "an option was dropped from one side or both"
    shared = [o for o in _SHARED_OPTIONS if o != "--shard-durations"]
    assert {o: lane_options[o] for o in shared} == {o: suite_options[o] for o in shared}
    assert suite_options["--shard-durations"] == ".test_durations"
    assert lane_options["--shard-durations"].endswith("durations.json")
    assert any("preboard_guard_lane.py durations" in s for s in _scripts(workflow)), "the file is made by the lane"
    suite_env = _doc(_SUITE_WORKFLOW)["jobs"]["python-shard"]["env"]["PYTEST_FAULTHANDLER_TIMEOUT_S"]
    assert workflow["jobs"]["guards"]["env"]["PYTEST_FAULTHANDLER_TIMEOUT_S"] == suite_env


def test_it_restates_no_test_root(workflow, lane) -> None:
    roots = set(lane.testpaths(_ROOT))
    scripts = _scripts(workflow)
    tokens = {t.rstrip("/") for script in scripts for t in _tokens(script)}
    assert len(tokens) > 20 and roots, "the sweep read nothing, so finding no root proves nothing"
    assert not (tokens & roots), f"test roots written in the workflow: {sorted(tokens & roots)}"
    assert any("preboard_guard_lane.py roots" in s for s in scripts) and any("${ROOTS[@]}" in s for s in scripts)


def test_every_pytest_root_is_run_by_the_lane_or_named_as_left_to_the_suite(lane) -> None:
    declared, guard, product = set(lane.testpaths(_ROOT)), set(lane.GUARD_ROOTS), set(lane.PRODUCT_ROOTS)
    assert lane.guard_roots(_ROOT) == list(lane.GUARD_ROOTS)
    assert not guard & product, f"in both lists: {sorted(guard & product)}"
    assert declared == guard | product, f"undecided roots: {sorted(declared ^ (guard | product))}"
    suite = set(_suite_invocation())
    assert guard <= suite, f"roots the suite's backend shard step does not name: {sorted(guard - suite)}"


def test_the_types_check_is_the_one_composite_action(workflow) -> None:
    steps = workflow["jobs"]["types"]["steps"]
    assert [s.get("uses") for s in steps][-1] == _TYPES_ACTION
    assert all("ref" not in s.get("with", {}) for s in steps), "a dispatch checkout takes no ref"


def test_the_result_is_uploaded_whatever_the_outcome(workflow) -> None:
    result = workflow["jobs"]["result"]
    assert result["needs"] == ["guards", "types"] and "always()" in result["if"]
    upload = next(s for s in result["steps"] if s.get("with", {}).get("name") == "preboard-guards-result")
    assert upload["uses"].startswith("actions/upload-artifact@") and upload["if"] == "always()"
    assert upload["with"]["if-no-files-found"] == "error"


def test_every_action_pin_is_one_the_suite_already_uses(workflow) -> None:
    used = {s["uses"] for job in workflow["jobs"].values() for s in job["steps"] if "uses" in s}
    external = {u for u in used if not u.startswith("./")}
    known = {
        step["uses"]
        for path in _workflow_files()
        if path != _LANE_WORKFLOW
        for job in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("jobs", {}).values()
        for step in job.get("steps", [])
        if "uses" in step
    }
    assert external and external <= known, f"pins no other workflow uses: {sorted(external - known)}"


# ------------------------------------------------------------------ equivalence with the suite


def test_the_tests_run_on_the_head_merged_with_the_base_before_the_environment_is_built(workflow) -> None:
    for job in ("guards", "types"):
        steps = workflow["jobs"][job]["steps"]
        merge = next(i for i, s in enumerate(steps) if "preboard_guard_lane.py merge" in s.get("run", ""))
        later = [i for i, s in enumerate(steps) if s.get("uses", "").startswith("./.github/actions/")]
        assert later and merge < min(later), f"{job}: the merge must precede the environment setup"
        assert steps[0]["with"]["fetch-depth"] == 0, f"{job}: a merge needs the history"
    run = _step(workflow, "guards", _GUARDS_STEP)
    assert run["if"] == "steps.base.outputs.merged == 'true'"
    conflict = next(s for s in workflow["jobs"]["guards"]["steps"] if "conflicts" in s.get("name", ""))
    assert conflict["if"] == "steps.base.outputs.merged != 'true'" and "exit 1" in conflict["run"]


def test_the_lane_enables_what_the_suite_enables_on_a_merge_train(workflow) -> None:
    env = _step(workflow, "guards", _GUARDS_STEP)["env"]
    assert env[REACH_AUDIT_ENV] == "1", "the reach-floor staleness band is the check that failed a train"
    assert env[BASE_SHA_ENV] == "${{ steps.base.outputs.base_sha }}"
    suite_steps = _doc(_SUITE_WORKFLOW)["jobs"]["python-shard"]["steps"]
    assert any(f"{REACH_AUDIT_ENV}=1" in s.get("run", "") for s in suite_steps), "the suite no longer sets it"


def test_nothing_the_lane_runs_pushes(workflow, lane) -> None:
    assert not [s for s in _scripts(workflow) if "push" in _tokens(s)]
    tree = parse_cache.parse(support.LANE_MODULE.read_text(encoding="utf-8"))
    strings = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "push" not in strings and "merge" in strings


def test_every_allowlisted_skip_names_a_skip_that_still_exists_and_its_follow_up(lane) -> None:
    allowlist = lane.report.SKIP_ALLOWLIST
    assert allowlist, "an empty allowlist: retire this guard together with the last entry"
    for entry in allowlist:
        assert entry.file.split("/")[0] in lane.GUARD_ROOTS, f"{entry.file} is outside the lane's roots"
        text = (_ROOT / entry.file).read_text(encoding="utf-8")
        assert entry.source_marker in text, f"{entry.file} no longer holds {entry.source_marker!r}: delete the entry"
        assert entry.reason_prefix and entry.skip_class in lane.report.SKIP_CLASSES, entry
        if entry.skip_class == lane.report.COVERED_BY_SUITE_ONLY:
            assert entry.follow_up == "#21360", f"{entry.file}: a covered-by-suite-only skip is removed by #21360"
        assert re.fullmatch(r"#\d+", entry.follow_up), entry


# ------------------------------------------------------------------ the documented contract


def _header() -> str:
    return _LANE_WORKFLOW.read_text(encoding="utf-8").split("\nname: ", 1)[0]


def test_the_artifact_fields_and_verdicts_are_documented_in_the_workflow_header(lane, tmp_path) -> None:
    header = _header()
    rows = support.passing("repo_tests/m_test.py", 3) + [support.skipped("repo_tests/m_test.py", "test_s", "r")]
    result = support.verdict(lane, tmp_path, [support.shard(1, 1, 0, rows)])
    skip = result["skipped_tests"][0]
    names = list(result) + list(result["checks"]["guards"]) + list(skip) + ["status", "nodeid", "kind", "message"]
    verdicts = ["green", "green_with_skips", "red", "cancelled"]
    missing = [n for n in names + verdicts if not re.search(rf"(?<!\w){re.escape(n)}(?!\w)", header)]
    assert not missing, f"fields undocumented in the workflow header: {missing}"
    assert f"schema {lane.report.SCHEMA_VERSION}" in header and lane.report.SCHEMA_VERSION == 2
    assert result["schema"] == lane.report.SCHEMA_VERSION


def test_the_header_states_what_the_lane_does_not_cover() -> None:
    header = _header()
    for phrase in ("product test trees", "dependency-floor", "promtool", "interaction of two members", "#21360"):
        assert phrase in header, f"the header no longer says the lane does not cover: {phrase}"
