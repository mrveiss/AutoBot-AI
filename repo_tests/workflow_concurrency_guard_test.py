# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every pull-request-triggered workflow must cancel its superseded runs (#14434).

Without a ``concurrency`` group, a push leaves its predecessors queued. They can
never affect anything - nothing reads the result of a run for a commit that is no
longer the branch tip - but each one still checks out and fetches its actions.

Measured before the fix: 260 queued runs, of which 42 of a 271-run sample were for
superseded commits. During GitHub's 2026-08-17 archive-download degradation that
wasted load stopped being merely slow and became *failures* on unrelated pull
requests (#14444), because each redundant job made its own attempt against an
endpoint returning errors.

Two workflows are deliberately exempt, and the exemption is by name with its reason
attached rather than a silent allowlist - a bare list of filenames is how an
exemption outlives the thing that justified it.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflows")

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# The required-context shims publish a context branch protection demands, from a
# job that is SKIPPED by its own `if:` whenever the real suite runs instead. Put
# them in a concurrency group and a superseded run takes the shim down with it -
# the context is then never reported at all, and the pull request blocks forever
# on "Expected - Waiting for status". Both files say so inline (#13405, #14353).
DELIBERATELY_EXEMPT = {
    "frontend-required-context.yml": (
        "publishes the required 'Unit & Integration Tests' context; cancelling a "
        "superseded run would leave it unreported and deadlock the pull request"
    ),
    "python-required-context.yml": ("publishes the required 'python-suite' context; same deadlock (#14353)"),
    # Landed by #15300 with the rationale spelled out inline and the exemption
    # never added here, so the guard has failed on every pull request since.
    "docker-smoke-required-context.yml": (
        "publishes the required 'docker-smoke-required-context' context; same deadlock (#15300)"
    ),
}


def _triggers(doc: dict) -> dict:
    """Return the workflow's ``on:`` block.

    YAML 1.1 resolves the bare key ``on`` to the boolean ``True``, so ``doc["on"]``
    raises and ``doc.get("on", {})`` silently returns nothing - which would make
    every assertion below vacuous while the test still passed.
    """
    return doc.get(True) or doc.get("on") or {}


def _pull_request_workflows():
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:  # a malformed workflow is a different test's problem
            continue
        if "pull_request" in _triggers(doc):
            yield path, doc


def test_the_scan_actually_finds_workflows():
    """A glob that matched nothing would make the guard below assert nothing."""
    found = list(_pull_request_workflows())

    assert len(found) >= 20, (
        f"only {len(found)} pull_request-triggered workflow(s) matched - the scan is "
        "no longer bound to the workflows it is meant to guard"
    )


def test_every_exemption_still_names_a_real_workflow():
    """An allowlist entry naming a moved or renamed file exempts nothing, silently."""
    for name in DELIBERATELY_EXEMPT:
        assert (WORKFLOW_DIR / name).is_file(), (
            f"{name} is exempt from the concurrency requirement but no longer exists. "
            "A stale exemption is invisible: it stops applying without failing."
        )


@pytest.mark.parametrize(
    "path",
    [pytest.param(p, id=p.name) for p, _ in _pull_request_workflows()],
)
def test_a_pull_request_workflow_cancels_superseded_runs(path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    concurrency = doc.get("concurrency")

    if path.name in DELIBERATELY_EXEMPT:
        assert concurrency is None, (
            f"{path.name} is exempt because it {DELIBERATELY_EXEMPT[path.name]}. "
            "It now declares a concurrency group, which reintroduces that deadlock."
        )
        return

    assert concurrency, (
        f"{path.name} triggers on pull_request with no `concurrency:` group, so every "
        "push leaves its predecessors queued. Each redundant run still fetches its "
        "actions (#14434, #14444)."
    )
    assert concurrency.get("group"), f"{path.name}: concurrency group is empty"


# Workflows that trigger on pull_request AND push, and cancel unconditionally, so
# a merge to the base branch cancels the previous merge's verification (#13432).
#
# #14434 found and fixed twelve workflows with no concurrency group at all, and
# along the way flagged sixteen more that DID have one but cancelled unconditionally
# - a RATCHET (`UNGUARDED_BASE_BRANCH_CANCEL`) recorded all sixteen because they
# could not all be fixed in one change. #14450 fixed the last of them: every one now
# guards `cancel-in-progress` on `github.event_name == 'pull_request'`, so a
# base-branch push run is never cancelled by the next one - PR-run superseding,
# which is correct and saves the singleton runner, is unaffected. With zero
# offenders left, the ratchet's allowlist has nothing left to name, so this is now
# a permanent zero-tolerance guard instead: any workflow reintroducing the
# unconditional idiom fails here immediately, rather than accumulating until the
# next audit finds it.
#
# SCOPED BY DESIGN, and the scope is narrower than the defect. Everything below
# filters through `_pull_request_workflows()` first, so a workflow with the same
# collision shape but NO pull_request trigger is structurally invisible to this
# guard - `coverage.yml` (push + schedule) is exactly that, and its own comment
# claims the figure "tracks what actually landed" while two merges inside its ~35
# minute window cancel each other. Stating the scope because a guard narrower than
# its subject otherwise reads as coverage of the whole subject. That case is
# tracked on #14450 rather than silently absent.
#
# It was not a style nit. Seven of the ten required contexts were produced by the
# sixteen - api-wiring, code-quality, smoke-test (docker-smoke-test), migration-gate,
# startup-import-smoke, verify-generated-types, and "Unit & Integration Tests"
# (frontend-test) - so on a busy day the base branch was verified by whichever merge
# happened not to be superseded. #13432 measured exactly that for ci.yml: of 39
# completed base runs, 26 were cancelled and NONE succeeded. ci.yml was fixed first;
# the sixteen followed under #14434 and #14450.
def _cancels_base_branch_runs_unguarded(path: Path, doc: dict) -> bool:
    if "push" not in _triggers(doc):
        return False
    return (doc.get("concurrency") or {}).get("cancel-in-progress") is True


def test_base_branch_cancellation_does_not_spread():
    """Zero-tolerance: no pull_request workflow may cancel base-branch runs.

    #14450 fixed the last of sixteen workflows that cancelled unconditionally.
    A new offender - e.g. copying `cancel-in-progress: true` from a neighbour -
    must fail here, not accumulate until the next audit finds it.
    """
    offenders = {path.name for path, doc in _pull_request_workflows() if _cancels_base_branch_runs_unguarded(path, doc)}

    assert not offenders, (
        f"{sorted(offenders)} trigger on push and cancel unconditionally, so a merge "
        "cancels the previous merge's verification (#13432). Guard cancel-in-progress "
        "on github.event_name == 'pull_request'."
    )
