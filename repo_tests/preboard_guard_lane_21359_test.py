# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-board guard lane cannot report green while having run nothing (#21359, #18499 AC4).

``dispatch-preboard-guards.yml`` runs the suite's guard trees on a branch head so a merge-train
operator learns, before boarding, every guard the head would fail. A lane that is green because it
ran an empty or different set is worse than no lane: the operator boards on its word. Two layers:

* the workflow is read statically: dispatch-only, its own concurrency group, no stop-on-first-failure,
  the suite's own options, no test root written in it, the result artifact uploaded, the types job
  reusing the composite action;
* the module behind it (roots, floor, verdict) is exercised on synthetic reports, each verdict beside
  the control that proves it can turn the other way.

What this does not cover: no run is dispatched here. It cannot be before the workflow is on the
default branch, so the first dispatched run is the end-to-end evidence.
"""

from __future__ import annotations

import importlib.util
import json
import shlex
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from repo_tests._paths import repo_root

from tools.lint._comment_syntax import code_text

_ROOT = repo_root()
_WORKFLOWS = _ROOT / ".github" / "workflows"
_LANE_WORKFLOW = _WORKFLOWS / "dispatch-preboard-guards.yml"
_SUITE_WORKFLOW = _WORKFLOWS / "ci.yml"
_LANE_MODULE = _ROOT / "pipeline-scripts" / "preboard_guard_lane.py"
_TYPES_ACTION = "./.github/actions/generated-types-autofix"
_STOP_EARLY = ("-x", "--exitfirst", "--maxfail")
_SHARED_OPTIONS = ("-n", "--dist", "-p", "--shard-durations", "-m")


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


@pytest.fixture(scope="module")
def lane():
    """The module behind the lane, loaded once and removed again (it registers itself nowhere)."""
    spec = importlib.util.spec_from_file_location("preboard_guard_lane_under_test", _LANE_MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


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
    names = [
        (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("name") for p in sorted(_WORKFLOWS.glob("*.yml"))
    ]
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


def test_it_runs_the_suites_own_options(workflow) -> None:
    lane_options = _options([t for s in _scripts(workflow) for t in _invocation(s)])
    assert lane_options == _options(_suite_invocation())
    assert set(lane_options) == set(_SHARED_OPTIONS), "an option was dropped from one side or both"
    suite_env = _doc(_SUITE_WORKFLOW)["jobs"]["python-shard"]["env"]["PYTEST_FAULTHANDLER_TIMEOUT_S"]
    assert workflow["jobs"]["guards"]["env"]["PYTEST_FAULTHANDLER_TIMEOUT_S"] == suite_env


def test_it_restates_no_test_root(workflow, lane) -> None:
    roots = set(lane.testpaths(_ROOT))
    scripts = _scripts(workflow)
    tokens = {t.rstrip("/") for script in scripts for t in _tokens(script)}
    assert len(tokens) > 20 and roots, "the sweep read nothing, so finding no root proves nothing"
    assert not (tokens & roots), f"test roots written in the workflow: {sorted(tokens & roots)}"
    assert any("preboard_guard_lane.py roots" in s for s in scripts) and any("${ROOTS[@]}" in s for s in scripts)


def test_the_guard_roots_are_roots_the_suite_collects_and_names(lane) -> None:
    assert lane.guard_roots(_ROOT) == list(lane.GUARD_ROOTS)
    declared, suite = set(lane.testpaths(_ROOT)), set(_suite_invocation())
    for root in lane.GUARD_ROOTS:
        assert root in declared, f"{root} is not a pytest.ini root"
        assert root in suite, f"{root} is not named by the suite's backend shard invocation"


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
        for path in _WORKFLOWS.glob("*.yml")
        if path != _LANE_WORKFLOW
        for job in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("jobs", {}).values()
        for step in job.get("steps", [])
        if "uses" in step
    }
    assert external and external <= known, f"pins no other workflow uses: {sorted(external - known)}"


def test_the_artifact_fields_are_documented_in_the_workflow_header(workflow, lane, tmp_path) -> None:
    text = _LANE_WORKFLOW.read_text(encoding="utf-8")
    result = lane.build_result(_env(), _write_shards(tmp_path, [_shard(1, 1, 0, 3)]), 1, ["a"])
    names = list(result) + list(result["checks"]["guards"]) + ["status", "nodeid", "kind", "message", "reason"]
    missing = [n for n in names if n not in text]
    assert not missing, f"fields undocumented in the workflow header: {missing}"


# ------------------------------------------------------------------ the module, on synthetic reports


def _env(**over: str) -> dict[str, str]:
    needs = {"guards": {"result": "success"}, "types": {"result": "success"}}
    base = {"NEEDS_JSON": json.dumps(needs), "RUN_ID": "1", "REF": "b", "SHA": "s", "BASE_REF": "main"}
    return {**base, **over}


def _shard(number: int, splits: int, rc: int, cases: int, failing: tuple[str, ...] = ()) -> dict[str, Any]:
    rows = [
        f'<testcase classname="repo_tests.m_test" name="test_{i}" file="repo_tests/m_test.py"/>' for i in range(cases)
    ]
    for name in failing:
        rows.append(
            f'<testcase classname="repo_tests.m_test.TestK" name="{name}" file="repo_tests/m_test.py">'
            '<failure message="AssertionError: too big&#10;second line">trace</failure></testcase>'
        )
    rows.append(
        '<testcase classname="pipeline-scripts.p_test" name="test_s" file="pipeline-scripts/p_test.py">'
        '<skipped message="no promtool"/></testcase>'
    )
    meta = {"shard": number, "splits": splits, "rc": rc}
    return {"meta": meta, "junit": f'<testsuites><testsuite name="x">{"".join(rows)}</testsuite></testsuites>'}


def _write_shards(tmp_path: Path, shards: list[dict[str, Any]]) -> Path:
    for shard in shards:
        folder = tmp_path / f"preboard-shard-{shard['meta']['shard']}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "shard-meta.json").write_text(json.dumps(shard["meta"]), encoding="utf-8")
        (folder / "junit.xml").write_text(shard["junit"], encoding="utf-8")
    return tmp_path


def _verdict(tmp_path: Path, shards: list[dict[str, Any]], floor: int, lane, **env: str) -> dict[str, Any]:
    return lane.build_result(_env(**env), _write_shards(tmp_path, shards), floor, ["repo_tests"])


def test_a_complete_clean_run_is_green(lane, tmp_path) -> None:
    result = _verdict(tmp_path, [_shard(1, 2, 0, 5), _shard(2, 2, 0, 5)], 10, lane)
    assert result["overall"] == "green" and result["checks"]["guards"]["collected"] == 12
    assert result["failed_tests"] == [] and result["skipped_tests"][0]["reason"] == "no promtool"


def test_every_failure_is_listed_with_its_node_id_and_first_line(lane, tmp_path) -> None:
    shards = [_shard(1, 2, 1, 4, ("test_a[x]",)), _shard(2, 2, 1, 4, ("test_b",))]
    result = _verdict(tmp_path, shards, 8, lane)
    assert result["overall"] == "red"
    assert [t["nodeid"] for t in result["failed_tests"]] == [
        "repo_tests/m_test.py::TestK::test_a[x]",
        "repo_tests/m_test.py::TestK::test_b",
    ]
    assert {t["message"] for t in result["failed_tests"]} == {"AssertionError: too big"}


def test_a_run_below_the_floor_is_red_and_one_at_it_is_not(lane, tmp_path) -> None:
    assert _verdict(tmp_path / "a", [_shard(1, 1, 0, 4)], 6, lane)["overall"] == "red"
    assert _verdict(tmp_path / "b", [_shard(1, 1, 0, 4)], 5, lane)["overall"] == "green"


def test_a_missing_shard_is_red_not_a_smaller_green(lane, tmp_path) -> None:
    result = _verdict(tmp_path, [_shard(1, 2, 0, 50)], 1, lane)
    assert result["overall"] == "red" and "shards reported" in result["checks"]["guards"]["problems"][0]


def test_no_report_at_all_is_red(lane, tmp_path) -> None:
    result = _verdict(tmp_path, [], 1, lane)
    assert result["overall"] == "red" and result["checks"]["guards"]["problems"] == ["no shard reported"]


def test_an_empty_shard_or_an_unexplained_exit_is_red(lane, tmp_path) -> None:
    empty = _shard(1, 1, 5, 0)
    empty["junit"] = '<testsuites><testsuite name="x"/></testsuites>'
    assert _verdict(tmp_path / "a", [empty], 1, lane)["overall"] == "red"
    assert _verdict(tmp_path / "b", [_shard(1, 1, 1, 9)], 1, lane)["overall"] == "red"  # exit 1, no failure on record


def test_a_cancelled_job_is_cancelled_never_green(lane, tmp_path) -> None:
    needs = json.dumps({"guards": {"result": "cancelled"}, "types": {"result": "success"}})
    assert _verdict(tmp_path, [_shard(1, 1, 0, 9)], 1, lane, NEEDS_JSON=needs)["overall"] == "cancelled"


def test_a_failed_types_check_alone_makes_the_lane_red(lane, tmp_path) -> None:
    needs = json.dumps({"guards": {"result": "success"}, "types": {"result": "failure"}})
    assert _verdict(tmp_path, [_shard(1, 1, 0, 9)], 1, lane, NEEDS_JSON=needs)["overall"] == "red"


def test_the_floor_follows_the_suites_record(lane) -> None:
    recorded = lane.recorded_count(_ROOT, lane.guard_roots(_ROOT))
    assert recorded > 1000, "the record says little about the guard roots, so a floor from it means little"
    assert 1 <= lane.floor_for(_ROOT) <= recorded
    assert lane.floor_for(_ROOT) == int(recorded * lane.FLOOR_RATIO)


@pytest.mark.parametrize("name", ["main", "release/1.2", "issue-1-x"])
def test_a_plain_branch_name_is_accepted_as_the_base(lane, name) -> None:
    assert lane.BASE_REF_PATTERN.fullmatch(name)


@pytest.mark.parametrize("name", ["", "-x", "a b", "a;b", "$(x)", "../x"])
def test_a_base_that_is_not_a_branch_name_is_refused(lane, name) -> None:
    with pytest.raises(SystemExit):
        lane.lane_base_commit(name)
