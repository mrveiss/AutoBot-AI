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
    "python-required-context.yml": (
        "publishes the required 'python-suite' context; same deadlock (#14353)"
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


# Workflows that also run on push and cancel unconditionally, so a merge to the
# base branch cancels the previous merge's verification (#13432). Measured on
# Dev_new_gui at d68c09c88 while fixing #14434. This is a RATCHET: the number may
# only ever go DOWN. Fixing one means deleting its line.
#
# It is not a style nit. Seven of the ten required contexts are produced by
# workflows on this list - api-wiring, code-quality, smoke-test (docker-smoke-test),
# migration-gate, startup-import-smoke, verify-generated-types, and
# "Unit & Integration Tests" (frontend-test) - so on a busy day the base branch is
# verified by whichever merge happens not to be superseded. #13432 measured exactly
# that for ci.yml: of 39 completed base runs, 26 were cancelled and NONE succeeded.
# ci.yml was fixed; these were not. Tracked separately - see the issue referenced
# from #14434.
UNGUARDED_BASE_BRANCH_CANCEL = frozenset(
    {
        "actionlint.yml",
        "api-wiring.yml",
        "code-quality.yml",
        "docker-smoke-test.yml",
        "frontend-test.yml",
        "hardened-smoke-test.yml",
        "llc-contract.yml",
        "migration-gate.yml",
        "phase_validation.yml",
        "security.yml",
        "slm-frontend-check.yml",
        "slm-migration-gate.yml",
        "ssot-coverage.yml",
        "startup-import-smoke.yml",
        "trajectory-eval.yml",
        "verify-generated-types.yml",
    }
)


def _cancels_base_branch_runs_unguarded(path: Path, doc: dict) -> bool:
    if "push" not in _triggers(doc):
        return False
    return (doc.get("concurrency") or {}).get("cancel-in-progress") is True


def test_base_branch_cancellation_does_not_spread():
    """A ratchet, because the existing offenders cannot all be fixed in one change.

    Each entry cancels base-branch verification. The set may shrink, never grow -
    a new workflow copying the `cancel-in-progress: true` idiom from a neighbour is
    exactly how this reached sixteen.
    """
    offenders = {
        path.name
        for path, doc in _pull_request_workflows()
        if _cancels_base_branch_runs_unguarded(path, doc)
    }

    new = offenders - UNGUARDED_BASE_BRANCH_CANCEL
    assert not new, (
        f"{sorted(new)} also trigger on push and cancel unconditionally, so a merge "
        "cancels the previous merge's verification (#13432). Guard cancel-in-progress "
        "on github.event_name == 'pull_request'."
    )

    fixed = UNGUARDED_BASE_BRANCH_CANCEL - offenders
    assert not fixed, (
        f"{sorted(fixed)} no longer cancel base-branch runs - delete them from "
        "UNGUARDED_BASE_BRANCH_CANCEL so the ratchet keeps its grip. A list that "
        "still names a fixed file exempts nothing while looking like it does."
    )
