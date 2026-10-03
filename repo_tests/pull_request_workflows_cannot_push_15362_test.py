# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No ``pull_request``-triggered workflow may hold the permission needed to push (#15362).

A bot push to a PR branch invalidates every check already in flight and restarts the whole pass.
Two of the last twelve merged PRs paid a full extra CI cycle for a formatting or codegen nit, and
because the resulting commit is authored by ``github-actions[bot]`` the new runs are also parked
behind the fork-PR approval policy -- 28 of 400 runs sat ``action_required``.

**This asserts the CAPABILITY, not the absence of a `git push` line.** Two reasons, both learned
from getting it wrong first:

1. A workflow without ``contents: write`` cannot push whatever its script says, so the property is
   enforced by the token rather than by review of shell text. Deleting a ``git push`` leaves the
   capability for the next person to re-reach for; removing the permission does not.
2. Grepping for ``git push`` cannot tell an executed push from a printed one.
   ``no-commit-trailers.yml`` *prints* ``git push --force-with-lease`` inside an ``echo`` as the
   remediation command it asks a developer to run. A text-matching guard flags it and is wrong --
   that workflow pushes nothing. #15934's own issue body makes this mistake, listing it among
   workflows that "push commits to PR branches".

This file replaces ``auto_fix_bot_push_approval_test.py``, which pinned the wiring of the
``approve-parked-runs`` job that existed to repair the parking the push caused. That file's own
floor test carried the instruction followed here: *"If the last bot push workflow genuinely goes
away, delete this file -- do not let it stand as three green assertions over an empty list."* The
protection is replaced rather than dropped, and by a stronger property: that file asserted the
workaround was wired correctly, this one asserts the cause cannot recur.
"""

from __future__ import annotations

import pytest
import yaml
from repo_tests._paths import repo_root

WORKFLOWS_DIR = repo_root() / ".github" / "workflows"

#: Jobs permitted to hold ``contents: write`` on a ``pull_request`` trigger, each with the reason
#: it is not the defect this guard exists for. A push to a branch that is NOT the PR under review
#: invalidates nothing, so it is outside the scope of #15362.
#:
#: Keyed ``(workflow filename, job id)``. ``None`` as the job id means workflow-level permissions.
#: Adding an entry is a deliberate act that has to carry its reason; the test below asserts the
#: reason is non-empty, so an entry cannot be added as a bare silencer.
ALLOWED: dict[tuple[str, str | None], str] = {
    ("test-durations.yml", "land"): (
        "pushes the refreshed split durations to its own `automation/test-durations` branch and "
        "opens a PR from it -- never to the branch under review, so no in-flight check is "
        "invalidated"
    ),
}

#: Reach floor. A discovery-based guard that finds no workflows reports a clean run having
#: asserted nothing -- the failure #15826 catalogues across this repo's tree scanners. Measured at
#: 45 when this landed; the floor is set well below that so ordinary additions and removals do not
#: trip it, while a glob that stops matching does.
MIN_PR_WORKFLOWS = 30


def _document(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _is_pull_request_triggered(document) -> bool:
    """``on:`` is parsed by PyYAML as the boolean ``True``, not the string ``"on"``.

    Reading ``document["on"]`` returns ``None`` for every workflow in this repo and the guard then
    finds zero ``pull_request`` workflows and passes. Checking both keys is not defensiveness; it
    is the difference between this file asserting something and asserting nothing.
    """
    if not isinstance(document, dict):
        return False
    triggers = document.get("on", document.get(True))
    if isinstance(triggers, dict):
        return "pull_request" in triggers
    if isinstance(triggers, list):
        return "pull_request" in triggers
    return triggers == "pull_request"


def grants_write(permissions) -> bool:
    """Does this ``permissions:`` value grant write access to repository contents?

    Handles the SCALAR forms as well as the mapping. ``permissions: write-all`` is a plain string
    to ``yaml.safe_load``, and the first version of this guard accepted only dicts -- so the
    broadest possible grant of the very capability this file exists to forbid was skipped at both
    scopes, and the guard passed while the token held ``contents: write`` (review on #17908).

    That blind spot was invisible in the tree: no workflow uses the spelling today, so "nothing
    uses write-all" and "the guard cannot see write-all" produced the same clean result. The
    contrast cases below are what separate them, which is why they exist rather than relying on the
    real tree staying clean.

    The design argument this guard rests on is that a workflow without the permission cannot push
    whatever its script says. ``write-all`` is exactly that permission, in a form the parser could
    not see -- the right design with the wrong coverage.
    """
    if isinstance(permissions, str):
        # `read-all` grants every READ scope and nothing writable; `write-all` grants everything.
        return permissions.strip() == "write-all"
    if isinstance(permissions, dict):
        return permissions.get("contents") == "write"
    return False


def writers(document) -> list[str | None]:
    """Scopes granting write access to contents: ``None`` for workflow-level, else each job id.

    Takes a parsed document rather than a path so the contrast tests below can drive it with a
    synthetic workflow -- a detector that can only be pointed at the real tree cannot be shown to
    fire, and then "no findings" and "cannot find anything" look identical.
    """
    found: list[str | None] = []
    if grants_write(document.get("permissions")):
        found.append(None)
    for job_id, spec in (document.get("jobs") or {}).items():
        if isinstance(spec, dict) and grants_write(spec.get("permissions")):
            found.append(job_id)
    return found


def _pull_request_workflows() -> list:
    return sorted(p for p in WORKFLOWS_DIR.glob("*.yml") if _is_pull_request_triggered(_document(p)))


def test_the_workflow_glob_still_reaches_the_pull_request_workflows() -> None:
    """Reach floor, before any assertion that iterates the set."""
    assert WORKFLOWS_DIR.is_dir(), f"{WORKFLOWS_DIR} is missing; this guard would assert nothing"
    found = _pull_request_workflows()
    assert len(found) >= MIN_PR_WORKFLOWS, (
        f"only {len(found)} pull_request-triggered workflows found, expected at least "
        f"{MIN_PR_WORKFLOWS} -- the glob or the trigger parsing has stopped reaching them, and "
        "every assertion below would pass over almost nothing"
    )


def test_no_pull_request_workflow_can_push_to_the_branch_under_review() -> None:
    offenders: list[str] = []
    for path in _pull_request_workflows():
        for scope in writers(_document(path)):
            if (path.name, scope) in ALLOWED:
                continue
            where = "workflow-level permissions" if scope is None else f"job `{scope}`"
            offenders.append(f"{path.name}: {where} grants contents: write")
    assert not offenders, (
        "a pull_request-triggered workflow can push to the branch under review, which invalidates "
        "every check already running and restarts the whole pass (#15362):\n  "
        + "\n  ".join(offenders)
        + "\n\nEither drop the permission and report the fix instead of applying it, or add the "
        "job to ALLOWED with the reason its push does not touch the PR branch."
    )


def test_every_allowance_carries_a_reason() -> None:
    """An entry in ALLOWED is an exemption, and an exemption without a stated reason is a silencer."""
    for key, reason in ALLOWED.items():
        assert reason and reason.strip(), f"{key} is allowed with no reason given"


def test_the_detector_fires_on_a_workflow_that_can_push() -> None:
    """Contrast case: the guard above is only evidence if this detector can report something.

    Both scopes, because workflow-level and job-level permissions are separate code paths and a
    detector covering one reads exactly like a detector covering both.
    """
    top_level = yaml.safe_load("""
        on:
          pull_request:
        permissions:
          contents: write
        jobs:
          build:
            steps:
              - run: echo hi
        """)
    job_level = yaml.safe_load("""
        on:
          pull_request:
        jobs:
          pusher:
            permissions:
              contents: write
            steps:
              - run: echo hi
        """)
    clean = yaml.safe_load("""
        on:
          pull_request:
        permissions:
          contents: read
        jobs:
          build:
            steps:
              - run: echo hi
        """)
    assert writers(top_level) == [None]
    assert writers(job_level) == ["pusher"]
    assert writers(clean) == []
    assert _is_pull_request_triggered(top_level), "the `on:`-parses-as-True case is not handled"


def test_an_allowance_naming_a_vanished_workflow_is_reported() -> None:
    """An exemption outliving the file it names is stale policy, not a passing condition."""
    for filename, _ in ALLOWED:
        assert (
            WORKFLOWS_DIR / filename
        ).is_file(), f"{filename} is in ALLOWED but absent from {WORKFLOWS_DIR} -- remove the entry"


@pytest.mark.parametrize(
    "value,grants",
    [
        ("write-all", True),
        ("read-all", False),
        ("  write-all  ", True),
        ({"contents": "write"}, True),
        ({"contents": "read"}, False),
        ({"actions": "write"}, False),
        (None, False),
        ({}, False),
    ],
    ids=lambda v: repr(v),
)
def test_grants_write_reads_every_permissions_spelling(value, grants: bool) -> None:
    """Including the two scalars, which the first version of this guard could not see at all."""
    assert grants_write(value) is grants


@pytest.mark.parametrize("scope", ["workflow", "job"])
def test_the_write_all_scalar_is_caught_at_either_scope(scope: str) -> None:
    """The contrast the real tree cannot provide: nothing uses `write-all` today.

    Without these, "no workflow grants write-all" and "this guard is blind to write-all" are the
    same passing result -- and the second is how a future violation lands unnoticed.
    """
    if scope == "workflow":
        document = yaml.safe_load(
            "on:\n  pull_request:\npermissions: write-all\njobs:\n  b:\n    steps:\n      - run: echo\n"
        )
        assert writers(document) == [None]
    else:
        document = yaml.safe_load(
            "on:\n  pull_request:\njobs:\n  b:\n    permissions: write-all\n    steps:\n      - run: echo\n"
        )
        assert writers(document) == ["b"]


@pytest.mark.parametrize("scope", ["workflow", "job"])
def test_the_read_all_scalar_is_not_treated_as_a_grant(scope: str) -> None:
    """The other half: a guard that flagged every scalar would be wrong about `read-all`."""
    if scope == "workflow":
        document = yaml.safe_load(
            "on:\n  pull_request:\npermissions: read-all\njobs:\n  b:\n    steps:\n      - run: echo\n"
        )
    else:
        document = yaml.safe_load(
            "on:\n  pull_request:\njobs:\n  b:\n    permissions: read-all\n    steps:\n      - run: echo\n"
        )
    assert writers(document) == []
