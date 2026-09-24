# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A skipped `smoke-test` must never satisfy the required context (#17126).

Owner rule, 2026-09-19: nothing lands on `main` without passing the Docker smoke
test. `smoke-test` is a required status check, and two jobs publish that one
context -- the real build in `docker-smoke-test.yml` and the path-filtered shim
in `docker-smoke-required-context.yml`, on complementary conditions.

**GitHub counts a SKIPPED check run as satisfying a required status check.** Both
jobs `needs: changes`, so a `changes` job that failed or was cancelled skipped
both of them, and the requirement was met with no smoke test run at all. Both
files carried a comment asserting the opposite ("`needs` skips this job rather
than reporting green ... which blocks the pull request") -- correct about the
skip, wrong about what a skip means, and unfalsifiable where it was written.

This test is that claim moved somewhere it can fail. It asserts the three
mutually exclusive cases the design now rests on:

    changes ok, docker != true   shim runs, succeeds        (legitimate green)
    changes ok, docker == true   shim skips, real build reports
    changes NOT ok               shim runs and FAILS; the real workflow builds
                                 rather than skipping, because when nothing can
                                 say whether an image could have changed, the
                                 honest answer is to build it

**Stated boundary.** This reads the workflow YAML. It cannot prove GitHub's own
required-context resolution, and it does not try: the platform behaviour is the
premise, not the assertion. What it holds is that neither job can reach a state
where a skip is the only thing reported. The merge tooling's `MUST_RUN` list
(`ci-gate`) independently refuses an all-skipped `smoke-test`, and that belt
stays -- a guard on the workflow text and a guard at merge time fail for
different reasons.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

_WORKFLOWS = Path(".github/workflows")
_REAL = "docker-smoke-test.yml"
_SHIM = "docker-smoke-required-context.yml"

#: The context both jobs publish. The whole design depends on it being one name.
_CONTEXT = "smoke-test"


def _workflow(name: str) -> dict:
    path = repo_root() / _WORKFLOWS / name
    assert path.exists(), f"{name} is missing -- this guard's subject is gone, not clean"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _job(name: str, job_id: str = _CONTEXT) -> dict:
    jobs = _workflow(name).get("jobs", {})
    assert job_id in jobs, f"{name} has no `{job_id}` job; jobs are {sorted(jobs)}"
    return jobs[job_id]


def _condition(job: dict) -> str:
    """The job's `if:` with newlines and runs of spaces collapsed."""
    return " ".join(str(job.get("if", "")).split())


def _context_name(job: dict, job_id: str = _CONTEXT) -> str:
    """A job publishes its `name:` when it has one, else its id."""
    return str(job.get("name", job_id))


# --- The context is one name, published by both -------------------------------


def test_both_jobs_publish_the_same_required_context() -> None:
    """If these ever diverge, every assertion below guards a context nobody requires."""
    assert _context_name(_job(_REAL)) == _CONTEXT
    assert _context_name(_job(_SHIM)) == _CONTEXT


def test_both_jobs_depend_on_their_own_detector() -> None:
    """The premise of the whole hole: `needs` is what turns a detector failure
    into a skip, so a design that stopped using `needs` would need re-reading."""
    for name in (_REAL, _SHIM):
        needs = _job(name).get("needs")
        needs = [needs] if isinstance(needs, str) else list(needs or [])
        assert "changes" in needs, f"{name}'s {_CONTEXT} no longer needs `changes`"


# --- The shim: runs on always(), refuses when its detector did not answer ------


def test_the_shim_runs_even_when_its_detector_failed() -> None:
    """#17126 AC1: without `always()` the job is skipped, and a skip satisfies."""
    condition = _condition(_job(_SHIM))

    assert "always()" in condition, (
        "the shim's `if:` no longer starts from always(), so a failed or cancelled "
        f"`changes` skips it again and a skipped run satisfies the required {_CONTEXT} "
        f"context with no smoke test: {condition!r}"
    )


def test_the_shim_still_stands_down_for_the_real_build() -> None:
    """It must not report on the path where the real job owns the context."""
    condition = _condition(_job(_SHIM))

    assert "needs.changes.outputs.docker != 'true'" in condition, (
        "the shim must remain the exact complement of the real job on the " f"detector-succeeded path: {condition!r}"
    )


def test_the_shim_runs_on_the_detector_failure_path() -> None:
    condition = _condition(_job(_SHIM))

    assert "needs.changes.result != 'success'" in condition, (
        "the shim must run when its detector did not succeed -- that is the case it " f"exists to refuse: {condition!r}"
    )


def test_the_shim_refuses_rather_than_reporting_green() -> None:
    """#17126 AC1's second half: it FAILS when `changes.result` is anything else.

    Asserted on the script's own order, not merely on the presence of `exit 1`:
    an `exit 1` after the success echo would report green first.
    """
    steps = _job(_SHIM).get("steps", [])
    scripts = [str(step.get("run", "")) for step in steps if step.get("run")]
    assert scripts, "the shim has no run step, so it cannot refuse anything"
    script = "\n".join(scripts)

    assert "CHANGES_RESULT" in script, "the shim's script does not read its detector's result"
    assert "exit 1" in script, "the shim's script has no failure path"
    assert script.index("exit 1") < script.index("No Docker-related paths changed"), (
        "the refusal must come before the success message, or the job reports the "
        "required context green and then exits non-zero"
    )


def test_the_shim_passes_the_result_in_through_the_environment() -> None:
    """A `${{ }}` expression interpolated into a shell body is an injection seam;
    the repo's own convention is to pass it as `env:` and quote it."""
    steps = _job(_SHIM).get("steps", [])
    env_keys = {key for step in steps for key in (step.get("env") or {})}

    assert "CHANGES_RESULT" in env_keys, "the detector result must arrive as an env var, not inline"


# --- The real build: builds when it cannot know ------------------------------


def test_the_real_build_runs_when_its_own_detection_failed() -> None:
    """#17126 AC2: when path detection fails, neither job can produce a pass.

    The shim refusing covers its own detector. This covers the other one: the
    real workflow has a separate `changes` run, and if THAT fails while the
    shim's succeeds with docker == 'true', the shim stands down and only this
    condition prevents an all-skipped context.
    """
    condition = _condition(_job(_REAL))

    assert "always()" in condition, f"the real build's `if:` no longer starts from always(): {condition!r}"
    assert "needs.changes.result != 'success'" in condition, (
        "the real build must run when its own detector did not succeed; otherwise a "
        f"failed `changes` skips it and a skip satisfies the requirement: {condition!r}"
    )


def test_the_real_build_still_runs_unconditionally_off_pull_requests() -> None:
    """`push` and `schedule` have no meaningful diff, so they always build."""
    condition = _condition(_job(_REAL))

    assert "github.event_name != 'pull_request'" in condition


def test_the_real_build_still_runs_when_docker_paths_changed() -> None:
    condition = _condition(_job(_REAL))

    assert "needs.changes.outputs.docker == 'true'" in condition


#: The whole condition, normalised. Pinned in full rather than clause by clause
#: because a substring check cannot see the CONNECTIVE (review finding): swapping
#: `||` for `&&` between the disjuncts makes each job's `if` false in exactly the
#: case it must run -- silently reopening #17126 -- while every `in` assertion
#: keeps passing, since each token is still present verbatim.
_EXPECTED_CONDITIONS = {
    _SHIM: "always() && ( needs.changes.result != 'success' || needs.changes.outputs.docker != 'true' )",
    _REAL: (
        "always() && ( github.event_name != 'pull_request' "
        "|| needs.changes.result != 'success' || needs.changes.outputs.docker == 'true' )"
    ),
}


@pytest.mark.parametrize("workflow", sorted(_EXPECTED_CONDITIONS))
def test_the_condition_is_pinned_whole_not_clause_by_clause(workflow: str) -> None:
    """The disjuncts must be joined by OR, and that is not a substring property."""
    assert _condition(_job(workflow)) == _EXPECTED_CONDITIONS[workflow], (
        "this job's `if` no longer matches the pinned expression. If the change is deliberate, "
        "re-derive the three cases before updating this string -- an `&&` where an `||` belongs "
        "keeps every clause present and inverts when the job runs (#17126)."
    )


def test_swapping_the_connective_would_be_caught() -> None:
    """The control for the pin: an `&&` variant must not equal the pinned form,
    even though it contains every clause the older assertions look for."""
    inverted = _EXPECTED_CONDITIONS[_SHIM].replace("||", "&&")

    assert "needs.changes.result != 'success'" in inverted, "premise: the clauses survive the swap"
    assert "needs.changes.outputs.docker != 'true'" in inverted, "premise: so a substring check passes"
    assert inverted != _EXPECTED_CONDITIONS[_SHIM], "but the whole-condition pin catches it"


# --- Positive controls -------------------------------------------------------
#
# Every assertion above is a substring check against a live file, which passes
# for two different reasons: the property holds, or the reader is looking at
# something that cannot fail. These fixtures make the difference visible.

_WITHOUT_ALWAYS = "needs.changes.outputs.docker != 'true'"
_WITH_ALWAYS = "always() && ( needs.changes.result != 'success' || needs.changes.outputs.docker != 'true' )"


def test_the_always_check_rejects_the_shape_that_caused_17126() -> None:
    """The pre-#17126 condition against the predicate -- and the LIVE file too.

    The first version asserted only against the two local literals below, so it
    could not fail whatever the workflows said (review finding): a control that
    never reads its subject reads as coverage and is not.
    """
    assert "always()" not in _WITHOUT_ALWAYS
    assert "always()" in _WITH_ALWAYS
    assert "always()" in _condition(_job(_SHIM)), "the live shim must carry what this control describes"
    assert _condition(_job(_SHIM)) != _WITHOUT_ALWAYS, "the live shim must not be the pre-#17126 shape"


def test_the_order_check_rejects_a_refusal_that_reports_first() -> None:
    """A script that echoes success before exiting must not pass the order test."""
    wrong = 'echo "No Docker-related paths changed in this pull request."\nexit 1\n'

    assert wrong.index("exit 1") > wrong.index("No Docker-related paths changed")


@pytest.mark.parametrize("name", [_REAL, _SHIM])
def test_the_workflow_files_parse(name: str) -> None:
    """A YAML error would make every `_job` lookup above raise rather than fail,
    which reads as an error and not as a verdict -- worth its own assertion."""
    assert _workflow(name).get("jobs"), f"{name} declares no jobs"


def test_the_shim_cannot_report_green_without_its_own_detector_saying_so() -> None:
    """The invariant that actually holds, asserted because the comment used to
    claim a stronger one that does not (review finding on this PR).

    There are two `changes` jobs, one per workflow, and the shim can only see
    its own -- so when both detectors fail, both workflows report the
    `smoke-test` context and may disagree. What is NOT possible, and what
    #17126 needs, is the shim reporting green without its own detector having
    said no Docker paths changed. That is a property of the script's order:
    the refusal is checked and exits before any success message.
    """
    steps = _job(_SHIM).get("steps", [])
    script = "\n".join(str(step.get("run", "")) for step in steps if step.get("run"))

    refusal = script.index("exit 1")
    success = script.index("No Docker-related paths changed")
    assert refusal < success, "the shim must refuse before it can report, or a failed detector reports green"
    assert 'CHANGES_RESULT" != "success"' in script, (
        "the refusal must be conditioned on the shim's OWN detector result; a refusal conditioned on "
        "anything else would let a failed detection reach the success message"
    )


def test_the_real_build_also_runs_on_its_own_detector_failure() -> None:
    """The other half of the two-detector picture: neither workflow's failure is
    silent, and the real build is what makes a green mean a smoke test ran."""
    condition = _condition(_job(_REAL))

    assert "needs.changes.result != 'success'" in condition
    assert "always()" in condition
