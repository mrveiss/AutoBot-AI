# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pure decisions for the PR merge-conflict gate (#19769): no network, no clock.

``pr_conflict_gate.py`` reads each open PR's ``mergeable`` state and publishes the
``no-merge-conflicts`` commit status. Every judgement lives here so it is pinned by a
fixture test: what a PR's mergeable fields mean, what status to publish, which runs
to cancel (never the gate's own).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

STATUS_CONTEXT = "no-merge-conflicts"

#: Verdicts.
CONFLICTING = "conflicting"
MERGEABLE = "mergeable"
UNKNOWN = "unknown"

#: Run states worth cancelling: not yet finished.
CANCELLABLE_STATUSES = frozenset({"queued", "in_progress", "waiting", "pending", "requested"})

DESC_CONFLICT = "merge conflict with main: merge main and push"
DESC_MERGEABLE = "no merge conflict with main"
DESC_UNKNOWN = "mergeability still unknown or not yet current after retries; not treated as clean"


@dataclass(frozen=True)
class Verdict:
    """What to publish on a PR head: a status state, its description, and whether to cancel."""

    kind: str
    state: str
    description: str
    cancel_runs: bool


def classify(pull: Mapping[str, Any]) -> str:
    """CONFLICTING / MERGEABLE / UNKNOWN from one ``GET /pulls/{n}`` body.

    ``mergeable_state == "dirty"`` is GitHub's conflict state. ``mergeable`` is null
    while GitHub computes it; anything not affirmatively mergeable or dirty is UNKNOWN,
    so a malformed body can never read as clean.
    """
    if pull.get("mergeable_state") == "dirty" or pull.get("mergeable") is False:
        return CONFLICTING
    if pull.get("mergeable") is True:
        return MERGEABLE
    return UNKNOWN


def is_current(test_merge_parents: Sequence[str], base_tip: str, head_sha: str) -> bool:
    """Whether GitHub's test merge was built from this base tip and this head (#20573).

    A push to the base leaves ``mergeable: true`` standing until GitHub rebuilds the test
    merge, with no null in between; only its parents show which trees the answer is about.
    """
    return list(test_merge_parents) == [base_tip, head_sha]


def decide(kind: str) -> Verdict:
    """The status and side effect for a classification."""
    if kind == CONFLICTING:
        return Verdict(kind, "failure", DESC_CONFLICT, True)
    if kind == MERGEABLE:
        return Verdict(kind, "success", DESC_MERGEABLE, False)
    return Verdict(UNKNOWN, "pending", DESC_UNKNOWN, False)


def runs_to_cancel(runs: Iterable[Mapping[str, Any]], own_run_id: Optional[int]) -> List[int]:
    """Ids of queued or in-progress runs, excluding the gate's own run."""
    ids: List[int] = []
    for run in runs:
        run_id = run.get("id")
        if not isinstance(run_id, int) or run_id == own_run_id:
            continue
        if run.get("status") in CANCELLABLE_STATUSES:
            ids.append(run_id)
    return ids


def is_checkable(pull: Dict[str, Any], repository: str) -> bool:
    """A same-repo PR: a fork head SHA is not reachable by this repository's status API."""
    head_repo = ((pull.get("head") or {}).get("repo") or {}).get("full_name")
    return head_repo == repository
