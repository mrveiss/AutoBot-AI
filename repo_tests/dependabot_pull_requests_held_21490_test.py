# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A dependabot pull request must not start the full suite on its own (#21490).

After a dependency-manifest change landed, dependabot rebased ~15 pull requests and opened 5
more within minutes; each started every expensive workflow, 60+ runs were cancelled by hand and
the queue head's guard run sat queued 10-20 minutes for a runner.

The rule: every `pull_request` workflow is either on `CHEAP` (named, with its job count, so a
cheap workflow that grows a job is looked at again) or each of its expensive jobs is held --
its `if:` names the dependabot author / `changes` outputs `ready` or `held`, or it `needs` a
job that is. "Expensive" is a property of the job (a reusable-workflow call, a timeout of
`_EXPENSIVE_MINUTES` or more, or an end-to-end / smoke / matrix / docker name), not a list.
"""

from __future__ import annotations

import re

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflows")

WORKFLOW_DIR = repo_root() / ".github" / "workflows"

#: Floor on the pull_request workflows examined (35 today); a glob or parse that stops
#: matching must not turn the guard into a pass over nothing.
_MIN_WORKFLOWS = 25
_EXPENSIVE_MINUTES = 20
_EXPENSIVE_NAME = re.compile(r"e2e|end-to-end|smoke|matrix|docker", re.IGNORECASE)
_HOLD_MARKER = re.compile(r"dependabot\[bot\]|needs\.changes\.outputs\.(?:ready|held)")

#: Workflows with no expensive job, by name -> job count. A new job makes the count differ and
#: forces a look at whether the workflow is still cheap.
CHEAP: dict[str, int] = {
    "actionlint.yml": 1,
    "ansible-file-references.yml": 1,
    "ansible-free-form-args.yml": 1,
    "ansible-role-facts-test.yml": 1,
    "ci-dispatch-watchdog.yml": 1,
    "constraint-drift.yml": 1,
    "docs-liquid-tags.yml": 1,
    "duplication-guard.yml": 2,
    "frontend-codegen-drift.yml": 1,
    "frontend-typecheck-regression.yml": 1,
    "issue-landing-notes.yml": 2,
    "no-commit-trailers.yml": 1,
    "phase_validation.yml": 2,
    "pr-blocking-findings.yml": 1,
    "pr-issue-validation.yml": 2,
    "pr-merge-conflict-gate.yml": 1,
    "pr-queue-gate.yml": 1,
    "pr-structure.yml": 1,
    "pr-template-check.yml": 2,
    "ssot-coverage.yml": 1,
    "stylelint-tokens.yml": 1,
    "train-content-gate.yml": 1,
    "trajectory-eval.yml": 1,  # non-blocking and cheap; held anyway
    "wiki.yml": 1,
}

#: (workflow, job) -> why an expensive-looking job is not held.
EXEMPT_JOBS: dict[tuple[str, str], str] = {
    (
        "ci.yml",
        "run-precommit",
    ): "the config check carries the SPDX and symlink checks and runs on every PR, drafts included (#17957)",
}


def _triggers(doc: dict) -> dict:
    """The `on:` block; PyYAML reads the bare key `on` as the boolean True."""
    return doc.get(True) or doc.get("on") or {}


def pull_request_workflows(directory=WORKFLOW_DIR) -> dict[str, dict]:
    found = {}
    for path in sorted(directory.glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if "pull_request" in _triggers(doc):
            found[path.name] = doc
    return found


def _is_expensive(job_id: str, job: dict) -> bool:
    timeout = job.get("timeout-minutes")
    return bool(
        "uses" in job
        or (isinstance(timeout, int) and timeout >= _EXPENSIVE_MINUTES)
        or _EXPENSIVE_NAME.search(job_id)
        or _EXPENSIVE_NAME.search(str(job.get("name", "")))
    )


def _held_jobs(jobs: dict) -> set[str]:
    held = {j for j, spec in jobs.items() if _HOLD_MARKER.search(str(spec.get("if", "")))}
    while True:
        more = {j for j, spec in jobs.items() if j not in held and set(_needs(spec)) & held}
        if not more:
            return held
        held |= more


def _needs(spec: dict) -> list:
    needs = spec.get("needs") or []
    return [needs] if isinstance(needs, str) else list(needs)


def violations(workflows: dict[str, dict], cheap=CHEAP, exempt=EXEMPT_JOBS) -> list[str]:
    problems = []
    for name, doc in workflows.items():
        jobs = doc.get("jobs") or {}
        expensive = [j for j, spec in jobs.items() if _is_expensive(j, spec) and (name, j) not in exempt]
        if name in cheap:
            if len(jobs) != cheap[name]:
                problems.append(
                    f"{name}: allow-listed with {cheap[name]} job(s) but has {len(jobs)}; re-check it is still cheap"
                )
            if expensive:
                problems.append(f"{name}: allow-listed as cheap but has expensive job(s) {expensive}")
            continue
        if not expensive:
            problems.append(f"{name}: no expensive job -- add it to CHEAP with its job count")
        held = _held_jobs(jobs)
        problems.extend(
            f"{name}: expensive job {j!r} is not held for dependabot pull requests (#21490)"
            for j in expensive
            if j not in held
        )
    return problems


def test_the_scan_examines_the_pull_request_workflows():
    assert len(pull_request_workflows()) >= _MIN_WORKFLOWS


def test_every_allow_listed_workflow_still_exists_and_triggers_on_pull_request():
    found = pull_request_workflows()
    assert not sorted(set(CHEAP) - set(found)), "stale CHEAP entries"
    for wf, job in EXEMPT_JOBS:
        assert job in found[wf]["jobs"], f"stale exemption {wf}:{job}"


def test_every_pull_request_workflow_holds_its_expensive_jobs_for_dependabot():
    problems = violations(pull_request_workflows())
    assert not problems, "\n".join(problems)


def test_ci_defines_held_and_every_gate_passes_it_to_the_verdict():
    jobs = pull_request_workflows()["ci.yml"]["jobs"]
    assert "held" in jobs["changes"]["outputs"]
    gates = [
        step["with"]
        for spec in jobs.values()
        for step in spec.get("steps", [])
        if str(step.get("uses", "")).endswith("gate-verdict")
        and str(step["with"].get("draft-gated", "true")) != "false"
    ]
    assert len(gates) >= 8
    assert all("held" in w for w in gates), "a draft-gated verdict gate does not pass `held`"


# --- controls: the detector must flag what it is meant to flag -------------------------------
_UNGATED = {
    "x.yml": {
        "jobs": {
            "run-big": {"uses": "./.github/workflows/_gate-x.yml"},
            "slow": {"timeout-minutes": 45, "if": "${{ true }}"},
        }
    }
}
_GATED = {
    "x.yml": {
        "jobs": {
            "run-big": {"uses": "./a.yml", "if": "${{ needs.changes.outputs.held != 'true' }}"},
            "slow": {"timeout-minutes": 45, "if": "${{ github.event.pull_request.user.login != 'dependabot[bot]' }}"},
            "after": {"uses": "./b.yml", "needs": ["slow"]},
        }
    }
}


def test_control_an_ungated_expensive_job_is_flagged():
    problems = violations(_UNGATED, cheap={})
    assert len(problems) == 2, problems


def test_control_held_jobs_and_their_dependants_pass():
    assert violations(_GATED, cheap={}) == []


def test_control_a_cheap_workflow_that_grew_a_job_is_flagged():
    wf = {"c.yml": {"jobs": {"a": {}, "b": {}}}}
    assert violations(wf, cheap={"c.yml": 1})
    assert violations(wf, cheap={"c.yml": 2}) == []


def test_a_held_gate_fails_and_says_held_never_passes():
    from repo_tests._gate_verdict_driver import run_verdict

    code, out = run_verdict(GATE_HELD="true", GATE_APPLIES="false", GATE_WORK_OK="false")
    assert code == 1 and "held" in out
    # not held, same inputs: "not affected" passes -- the contrast the held branch must not share
    assert run_verdict(GATE_APPLIES="false", GATE_WORK_OK="false")[0] == 0
    # a held flag on a push event is inert
    assert run_verdict(GATE_HELD="true", GATE_EVENT="push")[0] == 0
