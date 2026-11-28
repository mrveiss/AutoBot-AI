# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A dependabot or release promotion pull request must not start the full suite on its own (#21490, #21519).

After a dependency-manifest change landed, dependabot rebased ~15 pull requests and opened 5 more within
minutes; each started every expensive workflow and 60+ runs were cancelled by hand.

Since #20825 no workflow subscribes to `pull_request`, so the hold has ONE home instead of a copy in every
workflow's job conditions: ci.yml's `changes` job (`hold` step) decides `held` from the pull request's facts as
`pr-context` looked them up, and `ready` is false for a held pull request. Everything that does work for a pull
request is behind `ready`: the work jobs of ci.yml, and `fan-out`, the only way an advisory workflow is started.
The two kinds held: a dependabot pull request that is not a `train-*` head, and the release promotion pull
request (same-repository head on the default branch, base `release`). `ci:full` releases either.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest
from repo_tests._gate_if import gate_always_runs
from repo_tests._paths import repo_root
from repo_tests._pr_dispatch import load, workflow_files

WORKFLOW_DIR = repo_root() / ".github" / "workflows"

#: The ci.yml gate jobs that run on purpose when held and report "held" (verdict.sh step 2b).
REPORTING_GATES = frozenset(
    {
        "python-suite",
        "code-quality",
        "startup-import-smoke",
        "unit-tests",
        "smoke-test",
        "api-wiring",
        "migration-matrix",
        "verify-generated-types",
    }
)


def _ci_jobs() -> dict:
    return load(WORKFLOW_DIR / "ci.yml")["jobs"]


def _gate_withs(jobs: dict) -> list[dict]:
    return [
        step["with"]
        for spec in jobs.values()
        for step in spec.get("steps", [])
        if str(step.get("uses", "")).endswith("gate-verdict") and str(step["with"].get("draft-gated", "true")) != "false"
    ]


def test_ci_defines_held_and_every_gate_passes_it_to_the_verdict():
    jobs = _ci_jobs()
    assert "held" in jobs["changes"]["outputs"]
    gates = _gate_withs(jobs)
    assert len(gates) >= 8
    assert all("held" in w for w in gates), "a draft-gated verdict gate does not pass `held`"


def test_ready_requires_not_held_and_the_work_waits_for_ready():
    jobs = _ci_jobs()
    ready = "".join(str(jobs["changes"]["outputs"]["ready"]).split())
    assert "steps.hold.outputs.held!='true'" in ready, "a held pull request must not be ready"
    work = [name for name, spec in jobs.items() if name.startswith("run-") and "outputs.ready == 'true'" in str(spec.get("if"))]
    assert len(work) >= 12, f"only {len(work)} work jobs wait for `ready`"


def test_fan_out_starts_no_advisory_workflow_for_a_held_draft_or_unready_pull_request():
    cond = str(_ci_jobs()["fan-out"]["if"])
    for clause in ("needs.changes.outputs.is_pr == 'true'", "outputs.ready == 'true'", "outputs.draft != 'true'"):
        assert clause in cond, f"fan-out no longer requires {clause}"


def test_the_hold_lives_in_ci_only_no_other_workflow_copies_it():
    """The dependabot / promotion tests used to be inlined in every workflow's job `if:`; a copy is a drift."""
    checked, copies = 0, []
    for path in workflow_files():
        for name, spec in (load(path).get("jobs") or {}).items():
            checked += 1
            if "dependabot" in str(spec.get("if", "")):
                copies.append(f"{path.name}:{name}")
    assert checked > 100 and copies == [], copies


def test_the_reporting_gates_are_real_ci_jobs_that_always_run():
    jobs = _ci_jobs()
    assert all(g in jobs and gate_always_runs(jobs[g].get("if")) for g in REPORTING_GATES)


def test_control_a_gate_that_drops_held_is_seen():
    jobs = _ci_jobs()
    gates = _gate_withs(jobs)
    stripped = [{k: v for k, v in w.items() if k != "held"} for w in gates]
    assert not all("held" in w for w in stripped), "control: the check must be able to fail"


def test_a_held_gate_fails_and_says_held_never_passes():
    from repo_tests._gate_verdict_driver import run_verdict

    code, out = run_verdict(GATE_HELD="true", GATE_APPLIES="false", GATE_WORK_OK="false")
    assert code == 1 and "held" in out
    # not held, same inputs: "not affected" passes -- the contrast the held branch must not share
    assert run_verdict(GATE_APPLIES="false", GATE_WORK_OK="false")[0] == 0
    # a held flag on a push event is inert
    assert run_verdict(GATE_HELD="true", GATE_EVENT="push")[0] == 0


_HOLD_BASE = {
    "IS_PR": "true",
    "AUTHOR": "maintainer",
    "HEAD_REF": "issue-1-work",
    "HEAD_REPO": "owner/repo",
    "BASE_REF": "main",
    "DEFAULT_BRANCH": "main",
    "REPO": "owner/repo",
    "LABELS": "[]",
}
_PROMOTION_ENV = {"HEAD_REF": "main", "BASE_REF": "release"}


def _hold_step() -> dict:
    return next(step for step in _ci_jobs()["changes"]["steps"] if step.get("id") == "hold")


def _run_hold(tmp_path, **override) -> str:
    """The `held` output of the hold step's own script, run with exactly the step's environment names."""
    assert set(_hold_step()["env"]) == set(_HOLD_BASE), "the step reads an input this driver does not provide"
    out, summary = tmp_path / "output", tmp_path / "summary"
    env = {**os.environ, **_HOLD_BASE, **override, "GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(summary)}
    subprocess.run(["bash", "-c", _hold_step()["run"]], env=env, check=True, capture_output=True, text=True)
    return out.read_text(encoding="utf-8").strip()


def test_the_hold_step_reads_the_looked_up_facts_not_the_actor():
    env = _hold_step()["env"]
    assert env["AUTHOR"] == "${{ steps.pr.outputs.author }}" and env["IS_PR"] == "${{ steps.pr.outputs.is-pr }}"
    assert not any("github.actor" in str(v) for v in env.values()), "github.actor is the coordinator's token owner on a dispatch"


@pytest.mark.skipif(shutil.which("jq") is None, reason="the hold step needs jq, as the hosted runner has")
@pytest.mark.parametrize(
    "override, held",
    [
        (_PROMOTION_ENV, "held=true"),
        ({**_PROMOTION_ENV, "LABELS": '["ci:full"]'}, "held=false"),
        ({**_PROMOTION_ENV, "HEAD_REPO": "fork/repo"}, "held=false"),
        ({**_PROMOTION_ENV, "BASE_REF": "main"}, "held=false"),
        ({"HEAD_REF": "issue-1-work", "BASE_REF": "release"}, "held=false"),
        ({**_PROMOTION_ENV, "IS_PR": "false"}, "held=false"),
        ({**_PROMOTION_ENV, "LABELS": "not json"}, "held=false"),
        ({"AUTHOR": "dependabot[bot]"}, "held=true"),
        ({"AUTHOR": "dependabot[bot]", "HEAD_REF": "train-1"}, "held=false"),
    ],
)
def test_the_hold_step_holds_the_promotion_and_dependabot_and_nothing_else(tmp_path, override, held):
    assert _run_hold(tmp_path, **override) == held
