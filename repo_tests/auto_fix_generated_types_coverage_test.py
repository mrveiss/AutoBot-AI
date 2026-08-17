# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Auto-fix must cover every artifact the verify gate checks (#14368).

`verify-generated-types.yml` runs TWO independent freshness checks:
`verify-types-run` diffs the backend's `autobot-frontend/src/types/generated/api.ts`,
and `verify-generated-types-slm` diffs the SLM backend's
`autobot-slm-frontend/openapi.json` + `.../src/types/generated/api.ts`. Before
#14368, `auto-fix-generated-types.yml` only regenerated and committed the
first of those three files — an SLM schema change turned
`verify-generated-types-slm` red with no self-heal, and the author had to
regenerate by hand against a locally-running SLM app (something contributors
and agents cannot do in this repo).

Asserting the STRING `autobot-slm-frontend` appears somewhere in the workflow
would pass on a comment, a trigger path with no matching commit step, or a
commit step that stages the wrong file. This file instead derives the
artifact set straight from the verify gate's own `git diff --exit-code`
invocations -- the actual thing that goes red -- and asserts the auto-fix
workflow's commit step stages every one of them, plus that the trigger paths
can actually fire it for the SLM source tree.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"
_VERIFY = _WORKFLOWS_DIR / "verify-generated-types.yml"
_AUTOFIX = _WORKFLOWS_DIR / "auto-fix-generated-types.yml"

# `git diff --exit-code <path> [<path> ...]` inside a `run:` block -- the exact
# invocation that decides whether a verify job goes red. Stops at `;`/newline
# so the trailing `; then` from the enclosing `if ! git diff ... ; then` is not
# swept into the path list.
_DIFF_INVOCATION = re.compile(r"git diff --exit-code ([^\n;]+)")


def _verify_checked_artifacts() -> set[str]:
    """Every file path any `verify-generated-types.yml` job diffs for drift."""
    text = _VERIFY.read_text(encoding="utf-8")
    artifacts: set[str] = set()
    for match in _DIFF_INVOCATION.finditer(text):
        artifacts.update(match.group(1).split())
    return artifacts


def _autofix_committed_artifacts() -> set[str]:
    """Every file path `auto-fix-generated-types.yml` stages in its commit step."""
    document = yaml.safe_load(_AUTOFIX.read_text(encoding="utf-8"))
    commit_step = next(
        step
        for step in document["jobs"]["autofix-types"]["steps"]
        if step.get("name") == "Commit regenerated types if drifted"
    )
    run = commit_step["run"]
    match = re.search(r"git add ([^\n]+(?:\n\s+[^\n]+)*)", run)
    assert match, "commit step has no `git add` -- nothing would ever be pushed back"
    # `git add a b \\\n  c` across a YAML block scalar -- collapse the
    # continuation whitespace the same way the shell would.
    return set(match.group(1).replace("\\", " ").split())


def _autofix_trigger_paths() -> list[str]:
    document = yaml.safe_load(_AUTOFIX.read_text(encoding="utf-8"))
    return document[True]["pull_request"]["paths"]


def test_the_scan_actually_found_artifacts_on_both_sides():
    """Empty sets would make every assertion below vacuously true."""
    assert len(_verify_checked_artifacts()) >= 3
    assert len(_autofix_committed_artifacts()) >= 3


def test_every_artifact_the_verify_gate_checks_is_committed_by_the_autofix():
    """The invariant: nothing verify diffs can go stale with no self-heal path."""
    checked = _verify_checked_artifacts()
    committed = _autofix_committed_artifacts()

    missing = checked - committed
    assert missing == set(), (
        f"verify-generated-types.yml diffs {missing} for freshness, but "
        "auto-fix-generated-types.yml never stages it -- a drift there goes "
        "red with no auto-fix, the exact #14368 gap for the SLM frontend"
    )


def test_the_slm_backend_source_tree_can_actually_trigger_the_autofix():
    """A commit step that stages the right file is still dead code if nothing
    in `on.pull_request.paths` ever fires the job for an SLM schema change."""
    paths = _autofix_trigger_paths()
    assert "autobot-slm-backend/**/*.py" in paths, (
        "auto-fix-generated-types.yml's pull_request.paths does not watch "
        "autobot-slm-backend sources -- an SLM schema change would never "
        "trigger this workflow at all"
    )


def test_dropping_the_slm_commit_paths_is_caught_by_the_invariant():
    """The mutation this file exists to catch, applied to the extracted data
    rather than the file on disk: reproduce the pre-#14368 auto-fix (which
    committed only the backend api.ts) and confirm the coverage assertion
    above would have failed against it.

    Statically traced, not executed as a second pytest run against a mutated
    workflow file -- this repo's task rules forbid running the test suite
    locally; CI is what executes this file for real.
    """
    checked = _verify_checked_artifacts()
    pre_14368_committed = {"autobot-frontend/src/types/generated/api.ts"}

    missing = checked - pre_14368_committed
    assert missing == {
        "autobot-slm-frontend/openapi.json",
        "autobot-slm-frontend/src/types/generated/api.ts",
    }, (
        "the pre-#14368 auto-fix commit-step artifact set should be reported "
        f"as missing exactly the two SLM files; got {missing}"
    )
