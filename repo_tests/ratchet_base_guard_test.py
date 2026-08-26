# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15102 — the down-only ratchet must be asserted on the BASE, and be heard.

The forensic record this file exists for
----------------------------------------
On 2026-08-26 ``autobot-backend/api/terminal_websocket_route_test.py`` reached
613 lines on ``Dev_new_gui`` with no ``KNOWN_LARGE`` entry. Neither side of the
merge that produced it was in violation:

* the pull request's own head (``1eeaa912f01``) held it at **598** lines, and
  ``code-quality`` ran there at 10:47:33Z and passed — truthfully;
* the base (``e1bf21cf4``) held it at **599**;
* the "Update branch" merge commit (``5646344859f``, 11:20:16Z) combined the
  two disjoint additions and reached **613**; the pull request was merged five
  seconds later, before any workflow could be dispatched against that head.

So the violation was *born in a merge*, in a tree that had never existed before
and against which no check had ever run. A ratchet evaluated only against a
pull request cannot see that class of violation, by construction — however
correctly it is gated.

``code-quality`` did in fact catch it afterwards: its ``push`` run on
``Dev_new_gui@16c104be5`` failed at the step "Audit the python-file-size
ceilings for drift". Nobody was told. The failure was found days later by
someone running the audit by hand, which is the actual defect — a red base that
reaches no reader is indistinguishable from a green one.

What this module pins
---------------------
``.github/workflows/ratchet-base-guard.yml``, the guard that closes the two
gaps the existing invocation leaves open:

* it is **unskippable** — ``code-quality`` filters both its ``on.push.paths``
  and its ``changes`` job on the backend-Python set, so a push touching no
  Python leaves the tree-wide invariant unexamined; a whole-tree invariant must
  not be gated on the diff that happened to arrive;
* a failure becomes a **tracked issue**, and the run goes red.

Every assertion below is phrased so that an absent result fails. The lookups
are helper functions, not inline expressions, precisely so the same helpers can
be driven over a *mutated* copy of the workflow: a checker that never proves it
can reject a broken input has not been shown to check anything.

This guard is not, and cannot be, a required status check — see the workflow's
own header. The pre-merge half (all ten required contexts were green on
``1eeaa912f01`` and *none at all* reported on ``5646344859f``, the head that
merged) is a branch-protection setting only the repo owner can change, tracked
in #15107.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflow")

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ratchet-base-guard.yml"
AUDIT_SCRIPT = "scripts/check_python_file_size.py"
AUDIT_FLAG = "--audit-ceilings"

#: The branch the whole project merges into. The guard is worthless on any
#: other one.
INTEGRATION_BRANCH = "Dev_new_gui"


# ---------------------------------------------------------------------------
# Lookups. Each proves its target exists rather than returning a falsy default,
# because "absent" reading as "fine" is the failure mode this family repeats.
# ---------------------------------------------------------------------------


def load_workflow(path: Path = WORKFLOW) -> dict[str, Any]:
    """Parse the workflow, or fail. A file that will not parse is not a pass."""
    assert path.is_file(), f"{path} does not exist — the base guard is not wired at all"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), f"{path} did not parse to a mapping"
    return doc


def triggers(doc: dict[str, Any]) -> dict[str, Any]:
    """The ``on:`` block.

    YAML 1.1 resolves the bare key ``on`` to the boolean ``True``, so a plain
    ``doc["on"]`` returns nothing and every check downstream would pass over an
    unread file.
    """
    block = doc.get(True, doc.get("on"))
    assert isinstance(block, dict), "the workflow declares no usable `on:` mapping"
    return block


def steps(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Every step of every job, flattened."""
    found: list[dict[str, Any]] = []
    for job in (doc.get("jobs") or {}).values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict):
                found.append(step)
    return found


def audit_invocations(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Steps that actually run the shared ceiling audit."""
    return [step for step in steps(doc) if AUDIT_FLAG in str(step.get("run", ""))]


def failing_steps(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Steps that end the run non-zero when the audit reported a violation."""
    return [
        step
        for step in steps(doc)
        if "exit 1" in str(step.get("run", "")) and "rc != '0'" in str(step.get("if", ""))
    ]


def issue_filing_steps(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Steps that turn a violation into a tracked issue somebody will read."""
    return [
        step
        for step in steps(doc)
        if "github-script" in str(step.get("uses", ""))
        # `issues.create({`, not `issues.create` — the latter is also a prefix of
        # `issues.createComment`, which the *closing* step uses on the clean path.
        and "issues.create({" in str(step.get("with", {}).get("script", ""))
    ]


# ---------------------------------------------------------------------------
# Non-vacuity. These come first: every sweep below is a list comprehension over
# `steps()`, and a comprehension over an empty list agrees with everything.
# ---------------------------------------------------------------------------


def test_the_step_enumeration_is_not_empty():
    """An empty sweep would make every assertion in this module vacuously true.

    This is the same rule the audit script applies to itself with
    ``MIN_TRACKED_PY_FILES``: a walk that reached nothing has not earned a
    verdict. Asserting the enumeration before asserting *over* it is what stops
    a restructured workflow from silently exempting itself.
    """
    found = steps(load_workflow())
    assert len(found) >= 4, f"the base guard flattened to {len(found)} step(s) — the sweep below would assert nothing"


def test_every_step_the_sweep_returns_was_actually_read():
    """The flattener must return real step mappings, not placeholders."""
    found = steps(load_workflow())
    assert all(step.get("name") or step.get("uses") or step.get("run") for step in found), (
        "a step came back with no name, `uses` or `run` — the flattener is reading the wrong level of the document"
    )


def test_the_helpers_reject_a_workflow_that_lost_its_steps():
    """Contrast for the two tests above: with no steps, the sweeps go empty.

    Without this, "the enumeration is non-empty" is an assertion about today's
    file rather than a property of the helper.
    """
    stripped = copy.deepcopy(load_workflow())
    for job in stripped["jobs"].values():
        job["steps"] = []

    assert steps(stripped) == []
    assert audit_invocations(stripped) == []
    assert failing_steps(stripped) == []
    assert issue_filing_steps(stripped) == []


# ---------------------------------------------------------------------------
# The guard runs the audit, on the base, on every push
# ---------------------------------------------------------------------------


def test_the_guard_runs_on_a_push_to_the_integration_branch():
    branches = (triggers(load_workflow()).get("push") or {}).get("branches")
    assert isinstance(branches, list) and INTEGRATION_BRANCH in branches, (
        f"the base guard does not trigger on a push to {INTEGRATION_BRANCH}, which is the "
        "only branch a merge lands on — it would never see the tree it exists to check"
    )


def test_the_guard_invokes_the_shared_audit_rather_than_reimplementing_it():
    """One ratchet, called from three places — not three ratchets.

    ``.pre-commit-config.yaml``, ``code-quality`` and this guard must all reach
    the same script, or lowering a ceiling in the one source of truth stops
    being enough.
    """
    invocations = audit_invocations(load_workflow())
    assert len(invocations) == 1, f"expected exactly one ceiling-audit invocation, found {len(invocations)}"
    assert AUDIT_SCRIPT in str(invocations[0].get("run", "")), (
        f"the audit step does not call {AUDIT_SCRIPT} — a second copy of the ratchet "
        "would drift from the one the pre-commit hook enforces"
    )


def test_the_guard_carries_no_paths_filter():
    """A tree-wide invariant may not be gated on the diff that happened to arrive.

    This is the concrete gap over ``code-quality``, which filters its push
    trigger *and* its ``changes`` job on the backend-Python set: a merge that
    touches no Python leaves a violation already sitting on the base entirely
    unexamined. #14550/#14551 is the same lesson from the other direction — a
    skipped required check reads to branch protection as a satisfied one.
    """
    push = triggers(load_workflow()).get("push") or {}
    assert "paths" not in push and "paths-ignore" not in push, (
        "the base guard declares a path filter, so a push that touches no matching "
        "file skips it — and a skipped guard reports nothing, which is exactly what "
        "a red base already looked like (#15102)"
    )


def test_the_paths_filter_check_rejects_a_workflow_that_grows_one():
    """Contrast: prove the absence check can actually see a filter."""
    mutated = copy.deepcopy(load_workflow())
    push = mutated.get(True, mutated.get("on"))["push"]
    push["paths"] = ["**/*.py"]

    assert "paths" in (triggers(mutated).get("push") or {})


# ---------------------------------------------------------------------------
# A violation is heard: the run goes red AND an issue is filed
# ---------------------------------------------------------------------------


def test_a_violation_ends_the_run_non_zero():
    failing = failing_steps(load_workflow())
    assert failing, (
        "no step ends the run non-zero on a failing audit. The audit's own exit code is "
        "captured rather than allowed to abort the job, so without this the guard would "
        "report success while holding a violation in its log"
    )


def test_a_violation_is_filed_as_an_issue():
    """The part that is genuinely new.

    ``code-quality`` already failed on the base for this exact violation
    (``Dev_new_gui@16c104be5``, step "Audit the python-file-size ceilings for
    drift"). Its redness reached no reader, so the violation stood until
    someone ran the audit locally. A log line is not a report.
    """
    filing = issue_filing_steps(load_workflow())
    assert filing, "a failing audit files no issue — the failure would again reach nobody"
    guards = {str(step.get("if", "")) for step in filing}
    assert all("rc != '0'" in guard for guard in guards), (
        f"the issue-filing step(s) are not gated on the audit's exit code: {sorted(guards)}"
    )


def test_the_filing_step_is_granted_the_permission_it_needs():
    """A step that cannot write an issue fails at the moment it is needed."""
    doc = load_workflow()
    jobs = [job for job in doc["jobs"].values() if isinstance(job, dict) and job.get("steps")]
    assert jobs, "the workflow declares no job with steps"
    for job in jobs:
        perms = job.get("permissions") or doc.get("permissions") or {}
        assert perms.get("issues") == "write", (
            "the base guard's job cannot write issues, so the filing step would fail "
            "precisely on the run where it matters"
        )


def test_the_audit_output_is_passed_through_the_environment():
    """A filename is not JavaScript.

    The report is injected with ``env:`` rather than interpolated into the
    ``script:`` body, so a path containing a backtick or ``${`` cannot break the
    step whose whole job is to report the failure.
    """
    filing = issue_filing_steps(load_workflow())
    assert filing
    for step in filing:
        script = str(step.get("with", {}).get("script", ""))
        assert "steps.audit.outputs.report" not in script, (
            "the audit report is interpolated straight into the github-script body; "
            "pass it through `env:` and read `process.env` instead"
        )
        assert "process.env" in script


# ---------------------------------------------------------------------------
# The guard must survive its own scheduling
# ---------------------------------------------------------------------------


def test_the_guard_does_not_cancel_superseded_base_runs():
    """Two merges in quick succession is the case this guard was born from.

    ``5646344859f`` and the merge five seconds later are exactly that shape.
    With ``cancel-in-progress: true`` the second push would cancel the first
    run, and a cancelled guard reports nothing (#13432).
    """
    concurrency = load_workflow().get("concurrency") or {}
    assert concurrency.get("cancel-in-progress") is not True, (
        "the base guard cancels superseded runs, so a rapid second merge would "
        "discard the verification of the first"
    )


def test_the_workflow_declares_no_pull_request_trigger():
    """It is a *base* guard, and saying so is part of not overclaiming.

    A ``pull_request`` trigger here would publish a context that looks like a
    merge gate and is not one — the required contexts are configured in branch
    protection, and this workflow is not among them.
    """
    assert "pull_request" not in triggers(load_workflow())
