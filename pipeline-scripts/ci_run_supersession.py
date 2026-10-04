# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Concurrency-group supersession for workflow runs (#13439).

``concurrency.cancel-in-progress: true`` reaps an *in-progress* predecessor and
never a *queued* one. When no runner picks a run up, that predecessor never
reaches in-progress, keeps holding ``${{ github.workflow }}-${{ github.ref }}``,
and every successor sits ``pending`` with an empty ``jobs`` array until a human
runs ``force-cancel`` — ``cancel`` demonstrably does not clear the state.

**This module reports; it does not cancel, and that is a decision rather than an
omission.** Three reasons, in order of weight:

1. The only workflow that runs this selection — ``self-hosted-runner-health.yml``
   — holds ``permissions: actions: read``. A ``force-cancel`` POST from it would
   fail with 403, so an "acting" implementation shipped today would be a
   destructive code path that has never once executed.
2. #13439's own acceptance list requires the self-modifying-PR guard in the
   workflow to drop the cancelling pass to ``--dry-run``. A cancel path landed
   without that guard is exactly the failure the issue warns about: a wrong
   supersession predicate cancelling a live required check repo-wide.
3. Repository rule: an agent proposes a destructive action and a human approves
   it. Naming the run ids and the exact remediation is the proposal.

What the selection buys even without cancelling is a distinction the starvation
probe could not previously draw. "Runs are queued and nothing is executing" is
produced by two conditions that want *opposite* actions — a saturated pool, where
the answer is wait, and a wedged concurrency group, where waiting is forever —
and the probe reported them with the same sentence
(``docs/developer/MEASUREMENT_DISCIPLINE.md``, family D).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Tuple

# Deliberately narrower than the watchdog's ``UNSTARTED_RUN_STATUSES``. A run
# holding a concurrency group while a newer one waits is ``queued`` or
# ``pending``. ``waiting`` and ``requested`` are approval gates — a human or a
# policy has yet to release them — and force-cancelling those would destroy work
# nobody has decided about rather than clearing a stuck queue.
STUCK_QUEUE_STATUSES = frozenset({"queued", "pending"})

# The statuses fetched to JUDGE supersession, which is a wider set than the ones
# eligible to BE superseded, and the difference is load-bearing. "Superseded"
# is a claim that something newer exists, so a population of ``queued`` alone
# would make the newest queued run look like the newest run in its group and
# silently under-report. ``completed`` is excluded on purpose: a finished run has
# released the group, and the hundreds of parked completed runs this repository
# carries would dominate the page and hide the live ones.
SUPERSESSION_POPULATION_STATUSES: Tuple[str, ...] = ("queued", "pending", "in_progress")

# How many superseded runs one report names. A cap on the OUTPUT, not on the
# finding: the count reported is the count found, and only the per-run lines are
# truncated — see :func:`superseded_report_lines`.
DEFAULT_SUPERSEDED_REPORTED = 20


class RunLister(Protocol):
    """The one method :func:`collect_supersession_population` needs of an API."""

    def recent_runs(self, per_page: int = 100, run_status: str = "") -> List[Dict[str, Any]]: ...


def parse_ts(value: Optional[str]) -> Optional[datetime]:
    """Parse a GitHub ISO-8601 timestamp into an aware UTC datetime."""
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_minutes(value: Optional[str], now: datetime) -> Optional[float]:
    """Minutes elapsed between the timestamp *value* and *now*."""
    parsed = parse_ts(value)
    if parsed is None:
        return None
    return (now - parsed).total_seconds() / 60.0


def run_is_same_repo(run: Dict[str, Any], repository: str) -> bool:
    """True when the run's head branch lives in *repository* rather than a fork."""
    head_repository = run.get("head_repository") or {}
    return str(head_repository.get("full_name") or "") == repository


def concurrency_group_key(run: Dict[str, Any]) -> Tuple[Any, Any, Any]:
    """The identity a concurrency group actually has (#13439).

    Grouped by ``(workflow_id, head_branch, event)``, **not** by workflow and
    branch alone. The group expression is ``${{ github.workflow }}-${{ github.ref }}``
    and ``github.ref`` differs between a ``push`` run (``refs/heads/...``) and a
    ``pull_request`` run (``refs/pull/N/merge``) on the same branch. Grouping
    across that boundary would treat a PR run as superseding a push run and
    cancel work that is not superseded at all.
    """
    return (run.get("workflow_id"), run.get("head_branch"), run.get("event"))


def _run_ordering_key(run: Dict[str, Any]) -> Tuple[Any, Any]:
    """Newest-last ordering: ``run_number`` first, ``created_at`` as tiebreak."""
    return (run.get("run_number") or 0, run.get("created_at") or "")


def superseded_stuck_runs(
    runs: Sequence[Dict[str, Any]],
    now: datetime,
    repository: str,
    grace_minutes: int,
    budget: int,
) -> List[Dict[str, Any]]:
    """Runs safe to force-cancel because a newer run holds their group (#13439).

    A run qualifies only when **all** hold:

    * it is **not the newest** in its group — the newest is never touched, under
      any condition, because it is the run everything else is waiting for;
    * its status is in :data:`STUCK_QUEUE_STATUSES` — ``in_progress`` means real
      work is happening, and ``waiting``/``requested`` are approval gates;
    * it is older than *grace_minutes* — a legitimate brief queue must not be
      mistaken for a stuck one;
    * its head repository is *repository* — the same fork restriction the
      approval sweep uses, and for the same reason: never act on a run built
      from contributor-supplied code.

    The result is truncated to *budget* oldest-first, so one sweep cannot cancel
    the world if the grouping logic is ever wrong.

    *runs* must be the LIVE population, not just the queued one — see
    :data:`SUPERSESSION_POPULATION_STATUSES` for why.
    """
    groups: Dict[Tuple[Any, Any, Any], List[Dict[str, Any]]] = {}
    for run in runs:
        if not run_is_same_repo(run, repository):
            continue
        groups.setdefault(concurrency_group_key(run), []).append(run)

    stuck: List[Dict[str, Any]] = []
    for members in groups.values():
        if len(members) < 2:
            continue  # nothing supersedes it
        ordered = sorted(members, key=_run_ordering_key)
        for run in ordered[:-1]:  # every member except the newest
            if run.get("status") not in STUCK_QUEUE_STATUSES:
                continue
            waited = age_minutes(run.get("created_at"), now)
            if waited is None or waited < grace_minutes:
                continue
            stuck.append(run)

    stuck.sort(key=lambda r: r.get("created_at") or "")
    return stuck[:budget]


def collect_supersession_population(api: RunLister, queued: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every live run supersession can turn on, de-duplicated by run id.

    *queued* is the caller's existing ``status=queued`` page, reused rather than
    re-fetched. The remaining statuses in
    :data:`SUPERSESSION_POPULATION_STATUSES` are fetched here, one listing each.
    """
    by_id: Dict[Any, Dict[str, Any]] = {}
    for run in queued:
        by_id.setdefault(run.get("id"), run)
    for status in SUPERSESSION_POPULATION_STATUSES:
        if status == "queued":
            continue  # the caller already paid for this page
        for run in api.recent_runs(run_status=status):
            by_id.setdefault(run.get("id"), run)
    return list(by_id.values())


def _superseded_run_line(run: Dict[str, Any], now: datetime, run_url: Callable[[Dict[str, Any]], str]) -> str:
    waited = age_minutes(run.get("created_at"), now)
    waited_text = f"{waited:.0f}m" if waited is not None else "unknown"
    return (
        f"  {run.get('name')} on {run.get('head_branch')} ({run.get('event')}) — "
        f"run #{run.get('run_number')}, {run.get('status')} {waited_text} "
        f"({run_url(run)})"
    )


def superseded_report_lines(
    superseded: Sequence[Dict[str, Any]],
    population_size: int,
    repository: str,
    now: datetime,
    grace_minutes: int,
    run_url: Callable[[Dict[str, Any]], str],
    reported_cap: int = DEFAULT_SUPERSEDED_REPORTED,
) -> List[str]:
    """The human-readable report for a supersession scan, found or not found.

    The first line is emitted whether or not anything was found, and it names
    every selector that produced the number — statuses, grace window, fork
    restriction. A sweep that prints nothing when it finds nothing is
    indistinguishable from one that did not run
    (``docs/developer/MEASUREMENT_DISCIPLINE.md``).
    """
    selectors = (
        f"statuses {'/'.join(SUPERSESSION_POPULATION_STATUSES)}, "
        f"grace >={grace_minutes}m, heads in {repository} only, "
        f"group=(workflow, branch, event)"
    )
    lines = [
        f"Supersession scan: {len(superseded)} stuck predecessor(s) "
        f"among {population_size} live run(s) [{selectors}]."
    ]
    if not superseded:
        return lines
    lines.append(
        f"::error::{len(superseded)} workflow run(s) are superseded predecessors still holding a "
        "concurrency group (#13439). Each is older than the grace window, is NOT the newest run in "
        "its group, and is queued/pending — so cancel-in-progress will never reap it and the newest "
        "run in its group cannot start."
    )
    for run in superseded[:reported_cap]:
        lines.append(_superseded_run_line(run, now, run_url))
    if len(superseded) > reported_cap:
        lines.append(f"  ... and {len(superseded) - reported_cap} more (output capped at {reported_cap}).")
    lines.append(
        "  Clear each with: gh api -X POST "
        f"repos/{repository}/actions/runs/<run-id>/force-cancel — plain `cancel` does not clear "
        "this state. This watchdog reports rather than cancels; see ci_run_supersession.__doc__."
    )
    return lines
