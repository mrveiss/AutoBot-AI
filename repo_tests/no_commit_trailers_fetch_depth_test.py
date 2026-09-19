# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The trailer gate's fetch-depth must see a release promotion whole (#16931 review).

`no-commit-trailers.yml` used to check out at a fixed `fetch-depth: 100`. #16801
(main -> release, 808 commits) exceeded it, and the gate refused to report a
truncated range as clean -- correctly, by design (#16207). #16931 replaced the
fixed depth with an expression: full history for `merge_group` or a PR over 90
commits, depth 100 otherwise.

Nothing exercised that expression before this file. The #16932 review flagged
it as the one part of that PR shipping with zero automated evidence: an
off-by-one (`>=` for `>`), a wrong field name, or a string-vs-number literal
would go unnoticed by every other guard on this workflow, and the only thing
that would ever notice is a live release run -- which is exactly the failure
mode #16931 exists to stop happening *again*.

This suite reads the live expression out of the workflow's YAML (`yaml.safe_load`,
not a duplicated string) and evaluates it with `repo_tests._github_expressions`,
a minimal GitHub-expression evaluator built for this purpose (no existing one was
found in `repo_tests/` -- see the #16932 review thread). Pinning the expression's
*text* would not catch a semantic regression, since the text changes along with
the bug; evaluating it does.
"""

from __future__ import annotations

from functools import lru_cache

import pytest
import yaml
from repo_tests._github_expressions import evaluate, strip_expression_braces
from repo_tests._paths import repo_root

WORKFLOW = repo_root() / ".github" / "workflows" / "no-commit-trailers.yml"
_CHECKOUT_STEP_NAME = "Checkout"


@lru_cache(maxsize=1)
def _fetch_depth_expr() -> str:
    """The live `fetch-depth` expression, read from the checkout step's `with:`.

    Reading through `yaml.safe_load` rather than a regex on the raw text means
    this survives any YAML-legal reformatting of the step (key order, quoting)
    that a text pin would not.
    """
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["check-trailers"]["steps"]
    checkout = next(
        (step for step in steps if step.get("name") == _CHECKOUT_STEP_NAME), None
    )
    assert checkout is not None, (
        f"no {_CHECKOUT_STEP_NAME!r} step found -- this test cannot see what it checks"
    )
    raw = checkout["with"]["fetch-depth"]
    return strip_expression_braces(raw)


def _github_context(*, event_name: str, event: dict) -> dict:
    """Wrap a fragment as `{"github": {...}}` -- the expression reads `github.*`."""
    return {"github": {"event_name": event_name, "event": event}}


def _merge_group_context() -> dict:
    return _github_context(event_name="merge_group", event={})


def _pull_request_context(*, commits: int) -> dict:
    """A `pull_request` event context carrying only the field the expression reads."""
    return _github_context(
        event_name="pull_request", event={"pull_request": {"commits": commits}}
    )


def _push_context() -> dict:
    """An event with no `pull_request` object at all.

    This workflow is not wired to `push` (#16931 did not change that), but the
    expression must not crash when `github.event.pull_request` is absent --
    GitHub's own null-comparison rule is what keeps this safe, and that rule is
    exactly what a naive reimplementation (e.g. raising on a missing key,
    or coercing null to 0 and comparing) would get wrong silently.
    """
    return _github_context(event_name="push", event={})


_FETCH_DEPTH_CASES = [
    pytest.param(_merge_group_context(), "0", id="merge_group"),
    pytest.param(
        _pull_request_context(commits=89), "100", id="pull_request-89-commits"
    ),
    pytest.param(
        _pull_request_context(commits=90), "100", id="pull_request-90-commits-boundary"
    ),
    pytest.param(
        _pull_request_context(commits=91), "0", id="pull_request-91-commits-boundary"
    ),
    pytest.param(
        _pull_request_context(commits=682),
        "0",
        id="pull_request-682-commits-release-sized",
    ),
    pytest.param(_push_context(), "100", id="push-no-pull-request-object"),
]


@pytest.mark.parametrize(("context", "expected"), _FETCH_DEPTH_CASES)
def test_fetch_depth_matches_expected_value(context: dict, expected: str) -> None:
    result = evaluate(_fetch_depth_expr(), context)
    assert result == expected, (
        f"context={context!r}: fetch-depth evaluated to {result!r}, expected {expected!r}"
    )


def test_mutated_operator_breaks_the_90_commit_boundary() -> None:
    """Negative control: MUTATION TARGET is `>` -> `>=` in the live expression.

    A 90-commit PR is the boundary #16931 drew: `> 90` keeps it at depth 100 (it
    fits), `>= 90` would silently drop it to depth 0. That is exactly the class
    of regression the #16932 review said nothing would catch. This constructs
    the mutant from the LIVE text (not a hand-written copy, so it tracks any
    wording change) and shows it produces a different, wrong value at the exact
    boundary the suite above pins -- i.e. that boundary assertion would fail
    against this mutant.
    """
    real = _fetch_depth_expr()
    mutant = real.replace("commits > 90", "commits >= 90", 1)
    assert mutant != real, (
        "mutation target 'commits > 90' not found in the live expression -- update this test"
    )
    boundary = _pull_request_context(commits=90)
    assert evaluate(real, boundary) == "100", (
        "sanity: the real expression at the boundary should be depth 100"
    )
    assert evaluate(mutant, boundary) == "0", (
        "a >= mutant silently drops a 90-commit PR to depth 0 -- undetected by "
        "anything except this comparison, since #16932's own CI never ran a "
        "90-commit PR through it"
    )


def test_mutated_field_name_breaks_the_91_commit_boundary() -> None:
    """Negative control: MUTATION TARGET is the `pull_request.commits` field name.

    A wrong field name (a typo, or a rename GitHub never ships) reads null from
    every real payload, and null compares false to anything -- so the PR-depth
    arm would never fire, and the mutant would ship as "always depth 100",
    silently reintroducing the truncation #16931 was filed to fix. This shows
    that at 91 commits, past the boundary, the mutant disagrees with the
    correct value.
    """
    real = _fetch_depth_expr()
    mutant = real.replace("pull_request.commits", "pull_request.changed_files", 1)
    assert mutant != real, (
        "mutation target 'pull_request.commits' not found in the live expression -- update this test"
    )
    past_boundary = _pull_request_context(commits=91)
    assert evaluate(real, past_boundary) == "0", (
        "sanity: the real expression past the boundary should be depth 0"
    )
    assert evaluate(mutant, past_boundary) == "100", (
        "a wrong field name reads null and silently keeps depth 100 for a "
        "91-commit PR -- the exact truncation #16931 was filed for, and the "
        "boundary assertion above would not have caught it"
    )
