# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The auto-fix bot's own push must not leave its PR parked (#14311).

``auto-fix-generated-types.yml`` pushes a
commit back to the PR branch as ``github-actions[bot]``. This repository's
fork-PR approval policy (``all_external_contributors``) treats that bot as an
external contributor, so every ``pull_request`` run the push triggers is
created with ``conclusion=action_required`` and never starts (#12823's shape,
reported against these two workflows specifically in #14311). The PR then
shows zero failing checks and simply stops moving.

Each workflow now carries an ``approve-parked-runs`` job that repairs this
immediately, in the SAME run that did the push (which was triggered by a
human action and so is not itself parked), by invoking the SAME script
``ci-dispatch-watchdog.yml`` already relies on
(``pipeline-scripts/ci_dispatch_watchdog.py --check dispatch``) rather than
reimplementing its approval logic. That script owns the actual behaviour and
its own tests (``repo_tests/ci_dispatch_watchdog_test.py``); what is pinned
here is the WIRING invariant a review can't eyeball reliably from two
similar-looking YAML files: the approval job exists, runs right after the
push job, is scoped to this PR only, and carries the identical same-repo
fork guard as the push job it follows -- so it can never be the path a fork
PR's run gets approved through.
"""

from __future__ import annotations


import yaml
from repo_tests._paths import repo_root

_WORKFLOWS_DIR = repo_root() / ".github" / "workflows"

# (workflow filename, id of the job that pushes as github-actions[bot])
_PUSH_WORKFLOWS = [
    ("auto-fix-generated-types.yml", "autofix-types"),
]

_APPROVAL_JOB_ID = "approve-parked-runs"
_SAME_REPO_GUARD = "github.event.pull_request.head.repo.full_name == github.repository"


def _jobs(filename: str) -> dict:
    document = yaml.safe_load((_WORKFLOWS_DIR / filename).read_text(encoding="utf-8"))
    return document["jobs"]


def test_there_is_a_bot_push_workflow_to_check():
    """Runs first: every assertion below is inside a `for … in _PUSH_WORKFLOWS`.

    An empty list makes all three pass by having nothing to iterate, which is a
    clean result reporting on nothing — the exact shape those tests exist to
    prevent in the workflows they guard.

    This is not hypothetical. The list held two entries until #15934 deleted
    `auto-fix-formatting.yml`; it holds one now, and the codegen half is
    already announced for deletion once *fail-with-the-recipe* replaces
    *fix-and-push*. **The commit that empties this list will turn three passing
    tests into three vacuous ones, and nobody will look, because they will be
    passing.**

    So the floor is here rather than in the reviewer's memory. If the last bot
    push workflow genuinely goes away, delete this file — do not let it stand
    as three green assertions over an empty list.
    """
    assert _PUSH_WORKFLOWS, (
        "no bot-push workflows declared, so every assertion in this file "
        "iterates nothing and passes.\n"
        "If the last one was deliberately removed, delete this file; if one was "
        "missed, add it to _PUSH_WORKFLOWS."
    )
    for filename, _ in _PUSH_WORKFLOWS:
        assert (_WORKFLOWS_DIR / filename).is_file(), (
            f"{filename} is declared here but absent from {_WORKFLOWS_DIR} — "
            "the entry outlived the workflow it names."
        )


def test_every_bot_push_job_has_a_same_repo_fork_guard():
    """Precondition for the rest of this file: if the push job itself were
    unguarded, scoping only the approval job would still leave a fork path."""
    for filename, push_job_id in _PUSH_WORKFLOWS:
        jobs = _jobs(filename)
        assert jobs[push_job_id]["if"].strip() == _SAME_REPO_GUARD, filename


def test_an_approval_job_exists_and_runs_right_after_the_push():
    for filename, push_job_id in _PUSH_WORKFLOWS:
        jobs = _jobs(filename)
        assert _APPROVAL_JOB_ID in jobs, f"{filename} has no {_APPROVAL_JOB_ID} job"
        approval_job = jobs[_APPROVAL_JOB_ID]
        assert approval_job["needs"] == push_job_id, filename


def test_the_approval_job_never_widens_scope_to_fork_prs():
    """Same exact guard as the push job -- not `always()`, which would run the
    approval job even when the push job was skipped for a fork PR."""
    for filename, _ in _PUSH_WORKFLOWS:
        jobs = _jobs(filename)
        approval_if = jobs[_APPROVAL_JOB_ID]["if"].strip()
        assert approval_if == _SAME_REPO_GUARD, filename
        assert "always()" not in approval_if, filename


def test_the_approval_job_scopes_to_only_this_pr():
    """WATCHDOG_ONLY_PR must be set -- an unscoped sweep would still repair
    the parking eventually, but only this PR's run needs releasing right now,
    and a full sweep from every push-triggered run multiplies API cost."""
    for filename, _ in _PUSH_WORKFLOWS:
        jobs = _jobs(filename)
        step = jobs[_APPROVAL_JOB_ID]["steps"][-1]
        env = step.get("env", {})
        assert env.get("WATCHDOG_ONLY_PR") == "${{ github.event.pull_request.number }}", filename


def test_the_approval_job_reuses_the_watchdog_script_rather_than_reimplementing_it():
    for filename, _ in _PUSH_WORKFLOWS:
        jobs = _jobs(filename)
        step = jobs[_APPROVAL_JOB_ID]["steps"][-1]
        run = step["run"]
        assert "pipeline-scripts/ci_dispatch_watchdog.py" in run, filename
        assert "--check dispatch" in run, filename


def test_the_approval_job_holds_only_the_permissions_it_needs():
    """actions:write is what lets it call POST .../runs/{id}/approve; nothing
    here needs contents:write, even though the workflow-level default (used
    by the push job) grants it."""
    for filename, _ in _PUSH_WORKFLOWS:
        jobs = _jobs(filename)
        permissions = jobs[_APPROVAL_JOB_ID]["permissions"]
        assert permissions.get("actions") == "write", filename
        assert permissions.get("contents") == "read", filename
