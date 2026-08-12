#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
CI dispatch watchdog for AutoBot.

Two distinct failure modes leave a pull request reading as "waiting for CI"
forever while nothing is actually queued. Both surface identically to any
tooling that summarises check conclusions (``statusCheckRollup == null``,
"19 success / 0 failures"), and neither produces a signal of its own:

1. **Parked runs (#12823).** ``auto-update-pr-branches`` refreshes stale PR
   branches through ``PUT /pulls/{n}/update-branch``. With the default
   ``GITHUB_TOKEN`` the resulting merge commit is authored and pushed by
   ``github-actions[bot]``. The repository's fork-PR approval policy
   (``all_external_contributors``) treats that bot as an external
   contributor, so every ``pull_request`` run it triggers is created with
   ``conclusion=action_required`` and never starts. The PR then carries a
   head commit with *no executed checks at all*.

2. **Undispatched / starved runs (#13045).** When the singleton self-hosted
   runner pool is empty, runs are created but never allocate a job. They sit
   at ``status=queued`` with ``jobs: []`` indefinitely, so a required context
   never reports and ``commits/{sha}/status`` stays ``pending`` forever.
   ``POST /actions/runs/{id}/approve`` cannot help these — they are not
   waiting for approval, they are waiting for hardware.

This module handles both:

* ``--check dispatch`` — probes whether the caller's token may approve
  workflow runs at all, approves the parked runs belonging to the current
  head commit of each open *same-repository* PR (bounded), and then publishes
  a commit status on every open PR head describing the dispatch state. A PR
  whose CI never dispatched therefore carries a visible, named, non-green
  context instead of silently reading as ready.
* ``--check probe`` — prints nothing but the credential verdict. It POSTs
  ``approve`` against a run that already succeeded, which GitHub rejects on
  state grounds, so it changes nothing and is safe to run from an unreviewed
  branch. This exists because ``--dry-run`` deliberately issues no approve
  request and therefore cannot answer the question at all.
* ``--check runner-starvation`` — reports runs that have been queued past a
  threshold while no self-hosted job is executing, and separately reports
  self-hosted jobs still executing well past the longest timeout any job in
  this repository declares. The ``/actions/runners`` administration endpoint
  returns ``403 Resource not accessible by integration`` for ``GITHUB_TOKEN``,
  so runner liveness is inferred from ``GET /actions/runs/{id}/jobs`` labels
  instead.

A third failure mode joins those two, and it is the reason the second one is
not sufficient on its own (#13341). A job can WEDGE rather than end: the
required ``Unit & Integration Tests`` context ran for over three hours against
a declared ``timeout-minutes: 30``, because GitHub enforces that timeout from
the runner side and a runner that has stopped making progress never receives
the cancellation. The consequences compound — the job holds a required context
that no merge can proceed without, and it holds the singleton self-hosted
runner that every other job needs.

It is also INVISIBLE. An in-progress check is rendered exactly like a healthy
one, so nothing distinguishes "running" from "wedged" but elapsed time. Worse,
a wedged job makes the starvation probe read the pool as ALIVE: a hung job is
``status=in_progress`` on a ``self-hosted`` label, which is precisely the
signal ``self_hosted_pool_is_serving`` treats as proof of health. Queued work
piling up behind it is then reported as "contention, not an outage" — a false
negative in exactly the scenario the probe exists for. Overdue jobs are
therefore excluded from the liveness verdict AND reported in their own right.

**Fork safety.** ``POST /actions/runs/{id}/approve`` is GitHub's
*approve-a-fork-pull-request-run* endpoint: releasing gated fork runs is its
entire purpose. This repository is public, receives fork pull requests, sets
``all_external_contributors`` deliberately, and runs several
``pull_request`` jobs on a self-hosted runner. Auto-approving a fork run would
therefore execute contributor-controlled code — ``npm ci`` and its lifecycle
scripts among it — on the owner's own machine, which is exactly what the
approval policy exists to prevent. Approval is consequently restricted to runs
whose head repository is this repository AND whose triggering actor is the
branch-update bot. Fork pull requests still receive a published *status*; they
never receive an approval.

Usage:
    pipeline-scripts/ci_dispatch_watchdog.py --check dispatch
    pipeline-scripts/ci_dispatch_watchdog.py --check dispatch --dry-run
    pipeline-scripts/ci_dispatch_watchdog.py --check probe
    pipeline-scripts/ci_dispatch_watchdog.py --check runner-starvation

Environment:
    GITHUB_TOKEN                     required — API credential
    GITHUB_REPOSITORY                required — "owner/repo"
    GITHUB_API_URL                   API root (default https://api.github.com)
    WATCHDOG_BASE_BRANCH             PR base to watch (default Dev_new_gui)
    WATCHDOG_GRACE_MINUTES           age before "no runs at all" is a failure
    WATCHDOG_STALL_MINUTES           age before a job-less queued run is a failure
    WATCHDOG_MAX_APPROVALS           per-sweep approval cap (blast-radius guard; exceeding it fails)
    WATCHDOG_POLL_ATTEMPTS           re-list attempts while runs appear
    WATCHDOG_POLL_INTERVAL_SECONDS   delay between those attempts
    WATCHDOG_STATUS_CONTEXT          commit status context name
    WATCHDOG_MAX_JOB_LOOKUPS         runs inspected for runner liveness per check
    WATCHDOG_JOB_OVERDUE_MINUTES     runtime after which a self-hosted job is wedged
    WATCHDOG_ONLY_PR                 sweep just this PR number (default: every open PR)

Exit codes:
    0  nothing wrong, or everything wrong was repaired
    1  the sweep finished with parked runs still outstanding. Two distinct
       causes, reported separately because they need different fixes:

       * an approval was REFUSED on permission grounds — the credential cannot
         release parked runs (see ``REMEDIATION``); or
       * the per-sweep approval cap was EXHAUSTED before the queue was clear
         (see ``budget_exhausted_message``). Nothing was refused and the
         credential is fine; there were simply more parked runs than one sweep
         is allowed to release.

       A third case is deliberately NOT a failure: an approve attempt that
       comes back "not waiting for approval" means a concurrent sweep already
       released the run. That is the outcome this tool wants, and it is the
       exact message ``interpret_probe`` reads as proof the credential is
       permitted, so counting it as a refusal used to make a benign race print
       a demand to relax repository security settings. See
       ``is_already_released``.
    2  internal error: configuration missing, or the API could not be reached
       at all. Never used for "the API answered and the answer was bad news".
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

# GitHub returns this message when the *token* lacks `actions: write`.
PERMISSION_DENIED_MARKER = "resource not accessible"
# ...and this one when the token is fine but the run is in the wrong state.
# Seeing it proves the credential may approve runs.
NOT_WAITING_MARKER = "not waiting for approval"

# The only actor whose parked runs this tool releases. Runs parked for any other
# reason are reported, never approved — see the fork-safety note above.
UPDATE_BOT_LOGIN = "github-actions[bot]"

# A job carrying this label ran on the self-hosted pool.
SELF_HOSTED_LABEL = "self-hosted"

# GitHub truncates commit-status descriptions beyond this length.
MAX_STATUS_DESCRIPTION = 140

# Run states that mean "created but no job has started yet".
UNSTARTED_RUN_STATUSES = frozenset({"queued", "waiting", "pending", "requested"})

# Deliberately narrower than UNSTARTED_RUN_STATUSES (#13439). A run holding a
# concurrency group while a newer one waits is ``queued`` or ``pending``.
# ``waiting`` and ``requested`` are approval gates — a human or a policy has yet
# to release them — and force-cancelling those would destroy work nobody has
# decided about rather than clearing a stuck queue.
STUCK_QUEUE_STATUSES = frozenset({"queued", "pending"})

# Transport failure — no HTTP status was ever received.
NO_RESPONSE_STATUS = 0

DEFAULT_API_ROOT = "https://api.github.com"
DEFAULT_BASE_BRANCH = "Dev_new_gui"
DEFAULT_GRACE_MINUTES = 10
DEFAULT_STALL_MINUTES = 45
# Sized from measurement, not preference. A single base merge parks every run
# on every open PR, and the run count carried by one head in this repository was
# measured at 20, 22, 24 and 27 across four PRs on 2026-08-02 — call it 27, the
# worst observed. Ten open PRs is comfortably above the working queue seen since
# the PR queue limit was removed and well below the 25 that pr-queue-gate treats
# as a runaway, so 27 x 10 clears a realistic queue in ONE pass.
#
# The old value of 30 was below the cost of a SINGLE merge with two PRs open, so
# every sweep on a real queue stopped part-way and promised a "next sweep" that
# the never-firing schedule could not provide. Observed: 30 approved, 0 refused,
# 4 PRs left parked.
#
# It remains a blast-radius guard, and exhausting it is now a hard error rather
# than a line of log. Worst case it spends 270 of the 1,000/hour GITHUB_TOKEN
# budget, which is only reached when ten PRs were genuinely just parked — the
# one moment that spend is worth making.
DEFAULT_MAX_APPROVALS = 270
DEFAULT_POLL_ATTEMPTS = 3
DEFAULT_POLL_INTERVAL_SECONDS = 20
DEFAULT_STATUS_CONTEXT = "ci-dispatch-watchdog"
# Runs inspected per check. Raised from 10 (#13341): the repository was measured
# carrying 12 concurrently in-progress runs, so a budget of 10 could not reach
# the whole set — and the run that matters is the one it dropped. See
# `inspect_self_hosted_pool` for why the ORDER of that budget is the real fix.
DEFAULT_MAX_JOB_LOOKUPS = 25
# A self-hosted job still executing after this long is wedged, not slow (#13341).
#
# Derived, not chosen: every self-hosted job in .github/workflows declares
# `timeout-minutes` of 30 or less (frontend-test's unit-tests and build-test at
# 30, security-scan at 20, test-summary at 15, auto-update-pr-branches at 15).
# 45 is therefore the largest declared ceiling in the repository plus a 50%
# margin, so no job that is merely slow can reach it while still inside its own
# declared limit. The case this catches is the one GitHub's own enforcement
# missed: 3h05m against a declared 30m.
DEFAULT_JOB_OVERDUE_MINUTES = 45
# 0 means "every open PR"; a PR number narrows the sweep to that one head.
DEFAULT_ONLY_PR = 0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30
# GitHub's maximum page size. Listing runs is one call whatever the size, so the
# full page is taken and the expensive per-run job lookups are budgeted instead.
MAX_RUNS_PER_PAGE = 100


class WatchdogError(RuntimeError):
    """Base for every error this module raises deliberately."""


class WatchdogConfigError(WatchdogError):
    """Raised when required environment configuration is absent or unusable."""


class WatchdogApiError(WatchdogError):
    """
    Raised when the API answered with something unusable.

    This is deliberately distinct from "the API answered and said there are no
    runs". Conflating the two is how a single rate-limit window turns into
    "CI never dispatched" printed against every open pull request.
    """


class PullHead(NamedTuple):
    """The properties of an open pull request this tool acts on."""

    number: int
    sha: str
    updated_at: Optional[str]
    url: str
    # False for a pull request opened from a fork. Such heads are reported but
    # never approved — see the fork-safety note in the module docstring.
    same_repo: bool


def _env_int(name: str, default: int) -> int:
    """Read a positive integer from the environment, falling back to *default*."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise WatchdogConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise WatchdogConfigError(f"{name} must be positive, got {value}")
    return value


class ApprovalOutcome(NamedTuple):
    """What one head's approval pass did. ``raced`` is benign, ``refused`` is not."""

    approved: int = 0
    refused: int = 0
    raced: int = 0
    budget: int = 0
    exhausted: bool = False


class OverdueJob(NamedTuple):
    """A self-hosted job still executing long past any declared timeout."""

    head_sha: str
    workflow: str
    job: str
    elapsed_minutes: float
    url: str

    def describe(self) -> str:
        return f"{self.workflow} / {self.job} running {self.elapsed_minutes:.0f}m"


class PoolState(NamedTuple):
    """
    What one inspection of the self-hosted pool established.

    ``serving`` is ``None`` when the answer could not be established at all, so
    the caller can say "unknown" rather than inventing a verdict. It is ``True``
    only when a self-hosted job is executing *within* a plausible runtime —
    a wedged job is deliberately not evidence of health (#13341).
    """

    serving: Optional[bool]
    overdue: List[OverdueJob]


class SweepOutcome(NamedTuple):
    """Totals for one pass over every head, plus the PRs the budget could not reach."""

    approved: int = 0
    refused: int = 0
    raced: int = 0
    budget: int = 0
    unsettled: bool = False
    touched: Set[str] = frozenset()  # type: ignore[assignment]
    deferred: Set[int] = frozenset()  # type: ignore[assignment]


def _env_non_negative_int(name: str, default: int) -> int:
    """
    Read a non-negative integer from the environment.

    Separate from :func:`_env_int` because zero is meaningful here — it is how
    ``WATCHDOG_ONLY_PR`` says "every open PR" — while every threshold read by
    ``_env_int`` would be nonsense at zero.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise WatchdogConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 0:
        raise WatchdogConfigError(f"{name} must not be negative, got {value}")
    return value


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


def is_parked(run: Dict[str, Any]) -> bool:
    """True when the run was created but requires manual approval to start."""
    return run.get("conclusion") == "action_required"


def is_unstarted(run: Dict[str, Any]) -> bool:
    """True when the run exists but has not allocated a job yet."""
    return run.get("status") in UNSTARTED_RUN_STATUSES


def run_is_same_repo(run: Dict[str, Any], repository: str) -> bool:
    """True when the run's head branch lives in *repository* rather than a fork."""
    head_repository = run.get("head_repository") or {}
    return str(head_repository.get("full_name") or "") == repository


def is_approvable(run: Dict[str, Any], repository: str) -> Tuple[bool, str]:
    """
    Decide whether this tool may release *run*, and say why not when it may not.

    Two conditions, both required. The head must live in this repository:
    ``approve`` exists to release gated FORK runs, and this repository is
    public, takes fork pull requests, and executes ``pull_request`` jobs on a
    self-hosted runner, so approving a fork run would run contributor-supplied
    code on the owner's machine. And the run must have been parked because the
    branch-update bot pushed it — a run parked for any other reason was parked
    by a policy decision this tool has no business overriding.
    """
    if not is_parked(run):
        return False, "not parked"
    if not run_is_same_repo(run, repository):
        origin = (run.get("head_repository") or {}).get("full_name") or "unknown"
        return False, f"fork pull request from {origin} — gated on purpose, never auto-approved"
    actor = (run.get("triggering_actor") or {}).get("login") or ""
    if actor != UPDATE_BOT_LOGIN:
        return False, f"parked for actor {actor or 'unknown'}, not the branch-update bot"
    return True, ""


def is_already_released(message: str) -> bool:
    """
    True when an approve attempt failed only because the run was already released.

    ``interpret_probe`` treats this exact message as PROOF the credential may
    approve — a token without permission is rejected on permission grounds
    instead. Counting it as a refusal therefore contradicts the probe in the
    same log, and refusals drive the credential remediation, so a benign race
    printed an instruction to relax repository security settings.

    The race is routine, not exceptional: two base pushes seconds apart each
    chain a sweep, and the second one POSTs approve against runs the first has
    already released.
    """
    return NOT_WAITING_MARKER in message.lower()


def starved_runs(
    runs: Sequence[Dict[str, Any]], now: datetime, stall_minutes: int
) -> List[Dict[str, Any]]:
    """Runs queued longer than *stall_minutes* without allocating a job."""
    starved = []
    for run in runs:
        if not is_unstarted(run):
            continue
        waited = age_minutes(run.get("created_at"), now)
        if waited is not None and waited >= stall_minutes:
            starved.append(run)
    return starved


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

    ``concurrency.cancel-in-progress: true`` reaps an *in-progress* predecessor
    and never a *queued* one. While the singleton self-hosted runner is offline a
    predecessor never reaches in-progress, so it keeps holding the group and its
    successors sit ``pending`` with an empty ``jobs`` array until a human runs
    ``force-cancel``. This selects exactly the runs where that is provably safe.

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


def job_is_self_hosted(job: Dict[str, Any]) -> bool:
    """True when this job was dispatched to the self-hosted pool."""
    labels = [str(label).lower() for label in (job.get("labels") or [])]
    return SELF_HOSTED_LABEL in labels


def job_is_overdue(job: Dict[str, Any], now: datetime, overdue_minutes: int) -> bool:
    """
    True when a self-hosted job has been executing past the point of plausibility.

    Only self-hosted jobs qualify. A GitHub-hosted job that overruns costs
    billable minutes and nothing else; a self-hosted one holds the singleton
    machine that every other job in the repository is waiting for, which is what
    turns one wedged frontend check into a repository-wide merge freeze.
    """
    if job.get("status") != "in_progress" or not job_is_self_hosted(job):
        return False
    elapsed = age_minutes(job.get("started_at"), now)
    return elapsed is not None and elapsed >= overdue_minutes


def _truncate(text: str) -> str:
    if len(text) <= MAX_STATUS_DESCRIPTION:
        return text
    return text[: MAX_STATUS_DESCRIPTION - 1] + "…"


def classify_dispatch(
    runs: Sequence[Dict[str, Any]],
    head_pushed_at: Optional[str],
    now: datetime,
    grace_minutes: int,
    stall_minutes: int,
    pool_serving: bool = True,
    overdue: Sequence[OverdueJob] = (),
) -> Tuple[str, str]:
    """
    Decide the commit-status state for one PR head.

    Returns ``(state, description)`` where *state* is a GitHub commit-status
    state. The watchdog never reports ``success`` for a head whose CI has not
    demonstrably dispatched, so "no failures" can never be mistaken for
    "verified" (#12823 option 3, #13045 property 1).

    A wedged job is reported as a failure for the same reason (#13341). Until
    now an in-progress required check was rendered identically whether it was
    working or hung, so the only way to tell was for a human to notice the clock
    — which on 2026-08-03 took three hours. Naming it in a commit status makes
    the difference visible on the pull request itself.
    """
    parked = [run for run in runs if is_parked(run)]
    if parked:
        names = ", ".join(sorted({str(run.get("name", "?")) for run in parked})[:3])
        return (
            "failure",
            _truncate(f"{len(parked)} run(s) parked awaiting approval and never started: {names}"),
        )

    if overdue:
        names = ", ".join(sorted(entry.describe() for entry in overdue)[:2])
        return (
            "failure",
            _truncate(f"{len(overdue)} job(s) wedged far past their declared timeout: {names}"),
        )

    starved = starved_runs(runs, now, stall_minutes)
    if starved:
        names = ", ".join(sorted({str(run.get("name", "?")) for run in starved})[:3])
        if pool_serving:
            # Contention, not an outage — still never green, because the head is
            # demonstrably not verified yet.
            return (
                "pending",
                _truncate(
                    f"{len(starved)} run(s) queued over {stall_minutes}m behind a busy runner pool: {names}"
                ),
            )
        return (
            "failure",
            _truncate(
                f"{len(starved)} run(s) queued over {stall_minutes}m with no runner available: {names}"
            ),
        )

    if not runs:
        waited = age_minutes(head_pushed_at, now)
        if waited is None or waited >= grace_minutes:
            return (
                "failure",
                _truncate(
                    f"no workflow runs exist for this commit after {grace_minutes}m — CI never dispatched"
                ),
            )
        return (
            "pending",
            _truncate("no workflow runs yet — still inside the dispatch grace window"),
        )

    return ("success", _truncate(f"{len(runs)} workflow run(s) dispatched for this commit"))


class GitHubApi:
    """Minimal GitHub REST client — stdlib only, no extra CI dependency."""

    def __init__(
        self,
        token: str,
        repository: str,
        api_root: str = DEFAULT_API_ROOT,
        timeout: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.token = token
        self.repository = repository
        self.api_root = api_root.rstrip("/")
        self.timeout = timeout

    def request(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, Any]:
        """
        Issue a request and return ``(status_code, decoded_body)``.

        A transport failure (DNS, TLS, connection reset, timeout) returns status
        ``NO_RESPONSE_STATUS`` rather than escaping as a traceback. An uncaught
        ``URLError`` would exit the process with code 1, which this module
        documents as "parked runs could not be approved" — a completely
        different condition, reported with no remediation text.
        """
        url = path if path.startswith("http") else f"{self.api_root}/{path.lstrip('/')}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url=url, method=method, data=data)
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout
            ) as response:  # noqa: S310 - fixed api host
                body = response.read().decode("utf-8")
                return response.status, (json.loads(body) if body else None)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                decoded: Any = json.loads(body) if body else None
            except json.JSONDecodeError:
                decoded = {"message": body}
            return exc.code, decoded
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            return NO_RESPONSE_STATUS, {"message": f"transport failure: {exc}"}

    def _list_runs(self, params: Dict[str, str], context: str) -> List[Dict[str, Any]]:
        query = urllib.parse.urlencode(params)
        status, body = self.request("GET", f"/repos/{self.repository}/actions/runs?{query}")
        if status != 200 or not isinstance(body, dict):
            raise WatchdogApiError(f"cannot list {context} (HTTP {status}): {body}")
        return list(body.get("workflow_runs") or [])

    def open_pull_requests(self, base: str) -> List[Dict[str, Any]]:
        query = urllib.parse.urlencode({"state": "open", "base": base, "per_page": "100"})
        status, body = self.request("GET", f"/repos/{self.repository}/pulls?{query}")
        if status != 200 or not isinstance(body, list):
            raise WatchdogApiError(f"cannot list open PRs (HTTP {status}): {body}")
        return body

    def runs_for_sha(self, sha: str) -> List[Dict[str, Any]]:
        """
        Runs attached to one head commit.

        Raises rather than returning ``[]`` on an API error: an empty list is
        interpreted downstream as "CI never dispatched", which is a specific and
        alarming claim that must never be made on the strength of a rate-limit
        response.
        """
        return self._list_runs({"head_sha": sha, "per_page": "100"}, f"runs for {sha[:12]}")

    def recent_runs(self, per_page: int = 100, run_status: str = "") -> List[Dict[str, Any]]:
        params = {"per_page": str(per_page)}
        if run_status:
            params["status"] = run_status
        return self._list_runs(params, f"recent runs (status={run_status or 'any'})")

    def run_jobs(self, run_id: int) -> List[Dict[str, Any]]:
        query = urllib.parse.urlencode({"per_page": "100"})
        status, body = self.request(
            "GET", f"/repos/{self.repository}/actions/runs/{run_id}/jobs?{query}"
        )
        if status != 200 or not isinstance(body, dict):
            raise WatchdogApiError(f"cannot list jobs for run {run_id} (HTTP {status}): {body}")
        return list(body.get("jobs") or [])

    def approve_run(self, run_id: int) -> Tuple[int, str]:
        status, body = self.request(
            "POST", f"/repos/{self.repository}/actions/runs/{run_id}/approve"
        )
        message = ""
        if isinstance(body, dict):
            message = str(body.get("message", ""))
        return status, message

    def set_status(
        self, sha: str, state: str, context: str, description: str, target_url: str
    ) -> int:
        payload: Dict[str, Any] = {
            "state": state,
            "context": context,
            "description": description,
        }
        if target_url:
            payload["target_url"] = target_url
        status, _ = self.request("POST", f"/repos/{self.repository}/statuses/{sha}", payload)
        return status


def inspect_self_hosted_pool(
    api: GitHubApi,
    max_lookups: int,
    overdue_minutes: int = DEFAULT_JOB_OVERDUE_MINUTES,
    now: Optional[datetime] = None,
) -> PoolState:
    """
    Establish whether the SELF-HOSTED pool is healthy, and name what is wedged.

    Any in-progress run used to count as liveness, which made the verdict
    near-permanently true: ``code-quality``, ``ci.yml`` and this very watchdog's
    own quarter-hourly cron all run on GitHub-hosted runners, so "something is
    executing" says nothing about the singleton machine that #13045 is about.
    Liveness is therefore established from job labels — the closest signal to
    ``/actions/runners`` that a workflow token is allowed to read.

    A second false reading is corrected here (#13341). A job that has WEDGED is
    still ``in_progress`` on a ``self-hosted`` label, so on the old rule the
    hung job that was blocking every merge would itself have been read as proof
    the pool was healthy, and the queue stacking up behind it dismissed as
    "contention, not an outage". An overdue job is consequently excluded from
    the liveness verdict and returned separately so it can be reported as the
    fault it is. This costs no extra API call: the job listing that establishes
    liveness is the same listing that finds the overdue jobs.

    ``serving`` is ``None`` when the answer could not be established at all.
    """
    now = now or datetime.now(timezone.utc)
    overdue: List[OverdueJob] = []
    try:
        # Ask for a full page and choose which runs to spend the job-lookup
        # budget on here, rather than letting the API's ordering choose.
        running = api.recent_runs(per_page=MAX_RUNS_PER_PAGE, run_status="in_progress")
    except WatchdogApiError as exc:
        print(f"  runner liveness unknown: {exc}")
        return PoolState(None, overdue)
    # OLDEST FIRST — the correction that makes this detector able to fire at all
    # (#13341). `GET /actions/runs` returns newest-first, and a wedged run is by
    # definition the OLDEST in-progress run, so truncating the newest N to the
    # lookup budget drops precisely the run being looked for. Measured on this
    # repository: 12 runs in progress, and the wedging `Frontend Testing Suite`
    # run was the oldest of the 12 — outside a budget of 10. The unit tests
    # passed throughout, because a synthetic listing has nothing to truncate.
    # Sorting costs nothing: it is the same single listing call.
    running.sort(key=lambda run: str(run.get("run_started_at") or run.get("created_at") or ""))
    serving = False
    for run in running[:max_lookups]:
        try:
            jobs = api.run_jobs(int(run["id"]))
        except WatchdogApiError as exc:
            print(f"  runner liveness partial: {exc}")
            continue
        for job in jobs:
            if job.get("status") != "in_progress" or not job_is_self_hosted(job):
                continue
            if job_is_overdue(job, now, overdue_minutes):
                elapsed = age_minutes(job.get("started_at"), now) or 0.0
                overdue.append(
                    OverdueJob(
                        head_sha=str(run.get("head_sha") or ""),
                        workflow=str(run.get("name") or "?"),
                        job=str(job.get("name") or "?"),
                        elapsed_minutes=elapsed,
                        url=str(job.get("html_url") or _run_url(api.repository, run)),
                    )
                )
                continue
            serving = True
    return PoolState(serving, overdue)


def self_hosted_pool_is_serving(api: GitHubApi, max_lookups: int) -> Optional[bool]:
    """Liveness alone, for callers that do not need the overdue detail."""
    return inspect_self_hosted_pool(api, max_lookups).serving


def overdue_by_head(overdue: Sequence[OverdueJob]) -> Dict[str, List[OverdueJob]]:
    """Group wedged jobs by the head commit whose PR they are blocking."""
    grouped: Dict[str, List[OverdueJob]] = {}
    for entry in overdue:
        if entry.head_sha:
            grouped.setdefault(entry.head_sha, []).append(entry)
    return grouped


def interpret_probe(status: int, message: str) -> Tuple[Optional[bool], str]:
    """
    Turn an ``approve`` response for a run that is NOT awaiting approval into a
    verdict about the *credential*.

    A token that holds ``actions: write`` is rejected on state grounds
    ("This workflow run is not waiting for approval"); a token that does not is
    rejected on permission grounds ("Resource not accessible by integration").

    Anything else returns ``None`` — unresolved. Returning ``True`` for an
    unrecognised response would mean a bad credential, a 404, a rate-limit
    window or an HTML error page all read as "permitted", which is precisely
    the fail-open this module exists to argue against. The caller must treat
    ``None`` as "no verdict", never as "fine".
    """
    lowered = message.lower()
    if PERMISSION_DENIED_MARKER in lowered:
        return False, "token lacks permission to approve workflow runs"
    if NOT_WAITING_MARKER in lowered:
        return True, "token may approve workflow runs (rejected on run state, not permission)"
    if status in (200, 201, 204):
        return True, "token may approve workflow runs (approval accepted)"
    if status == NO_RESPONSE_STATUS:
        return None, f"unresolved — the API could not be reached ({message or 'no detail'})"
    if status == 401:
        return None, "unresolved — the credential was rejected (401 Bad credentials)"
    if status == 404:
        return (
            None,
            "unresolved — the probe run was not found (404); the token may lack read access",
        )
    if status == 429:
        return None, "unresolved — rate limited (429); retry on the next sweep"
    return None, f"unresolved — unrecognised response (HTTP {status}: {message or 'no message'})"


def probe_approval_capability(api: GitHubApi, dry_run: bool = False) -> Tuple[Optional[bool], str]:
    """
    Establish whether this credential may approve runs, without side effects.

    Two details that both silently defeated earlier versions:

    * The candidate listing must select ``status=success``, not
      ``status=completed``. A parked run IS ``status=completed`` (with
      ``conclusion=action_required``), so on a repository carrying hundreds of
      parked runs every entry on the "recent completed" page is parked, every
      candidate is filtered out, and the probe reports nothing at all.
    * A dry run performs no approval call, so it cannot probe either. It says so
      rather than pretending the question was answered.
    """
    if dry_run:
        return None, "probe skipped: --dry-run issues no approve request"
    try:
        runs = api.recent_runs(per_page=20, run_status="success")
    except WatchdogApiError as exc:
        return None, f"probe unresolved: {exc}"
    candidates = [run for run in runs if not is_parked(run)]
    if not candidates:
        return None, "probe unresolved: no successful run available to probe against"
    status, message = api.approve_run(int(candidates[0]["id"]))
    return interpret_probe(status, message)


REMEDIATION = (
    "Parked runs cannot be approved with this credential. Every merge to the base branch will keep "
    "freezing open PRs until one of the following is chosen:\n"
    "  (a) relax the repository Actions setting 'Require approval for all external contributors' to "
    "'Require approval for first-time contributors', so pushes attributed to the update bot dispatch "
    "normally; or\n"
    "  (b) run auto-update-pr-branches with a credential that is a repository collaborator "
    "(a GitHub App installation token or PAT stored as a secret); or\n"
    "  (c) retire the automatic branch update and refresh PR branches from the PR page instead.\n"
    "Until then this watchdog marks affected PRs with a failing commit status so none of them can "
    "read as ready."
)


def budget_exhausted_message(deferred: Set[int], cap: int) -> str:
    """Explain a partial sweep in terms of the cap, not the credential."""
    return (
        f"The per-sweep approval cap ({cap}) was reached with parked runs still outstanding on "
        f"{len(deferred)} pull request(s). Those runs are STILL PARKED and their PRs still carry no "
        "executed checks.\n"
        "This is not a permissions problem — nothing was refused. Either raise WATCHDOG_MAX_APPROVALS, "
        "or approve the remainder from the Actions tab.\n"
        "Do not rely on 'the next sweep': the only triggers are a push to the base branch and a "
        "schedule that does not dispatch while this workflow is absent from the default branch."
    )


def _run_url(repository: str, run: Dict[str, Any]) -> str:
    return str(run.get("html_url") or f"https://github.com/{repository}/actions")


def needs_another_look(runs: Sequence[Dict[str, Any]]) -> bool:
    """
    True when this head warrants re-listing after a short wait.

    A head with NO runs at all is the interesting case: immediately after
    ``update-branch`` returns, the runs it triggers have not materialised yet,
    so an empty result means "too early", not "nothing to approve". A head that
    already has runs and no parked ones is genuinely settled.
    """
    if not runs:
        return True
    return any(is_parked(run) for run in runs)


def _approve_head(
    api: GitHubApi, number: int, runs: Sequence[Dict[str, Any]], budget: int, dry_run: bool
) -> ApprovalOutcome:
    """Approve the eligible parked runs of one head."""
    approved = 0
    refused = 0
    raced = 0
    exhausted = False
    for run in runs:
        eligible, reason = is_approvable(run, api.repository)
        if not eligible:
            if is_parked(run):
                print(f"  PR #{number}: leaving '{run.get('name')}' parked — {reason}")
            continue
        if budget <= 0:
            # Named, counted and escalated by the caller. "Deferring to the next
            # sweep" is only true if a next sweep happens, and the schedule that
            # was supposed to guarantee one has never fired.
            print(f"  PR #{number}: approval budget exhausted, deferring to the next sweep")
            exhausted = True
            break
        # Decremented on a dry run too, so the preview reflects the cap a real
        # sweep would hit rather than promising more than it would do.
        budget -= 1
        if dry_run:
            print(f"  PR #{number}: would approve '{run.get('name')}' ({run['id']})")
            continue
        status, message = api.approve_run(int(run["id"]))
        if status in (200, 201, 204):
            approved += 1
            print(f"  PR #{number}: approved '{run.get('name')}' ({run['id']})")
        elif is_already_released(message):
            # A concurrent sweep got there first. The run is released, which is
            # the outcome this tool wanted — not a failure, and emphatically not
            # evidence that the credential is inadequate.
            raced += 1
            print(
                f"  PR #{number}: '{run.get('name')}' already released by a concurrent sweep — no action needed"
            )
        else:
            refused += 1
            print(
                f"  PR #{number}: could NOT approve '{run.get('name')}' — HTTP {status}: {message}"
            )
    return ApprovalOutcome(approved, refused, raced, budget, exhausted)


def _sweep_once(
    api: GitHubApi, heads: Sequence[PullHead], budget: int, dry_run: bool
) -> SweepOutcome:
    """One pass over every head."""
    approved = 0
    refused = 0
    raced = 0
    unsettled = False
    touched: Set[str] = set()
    deferred: Set[int] = set()
    for head in heads:
        try:
            runs = api.runs_for_sha(head.sha)
        except WatchdogApiError as exc:
            print(f"  PR #{head.number}: cannot inspect runs — {exc}")
            unsettled = True
            continue
        if needs_another_look(runs):
            unsettled = True
        if not head.same_repo:
            if any(is_parked(run) for run in runs):
                print(
                    f"  PR #{head.number}: fork pull request — parked runs left for a human to approve"
                )
            continue
        outcome = _approve_head(api, head.number, runs, budget, dry_run)
        budget = outcome.budget
        if outcome.approved:
            touched.add(head.sha)
        if outcome.exhausted:
            deferred.add(head.number)
        approved += outcome.approved
        refused += outcome.refused
        raced += outcome.raced
    return SweepOutcome(approved, refused, raced, budget, unsettled, touched, deferred)


def sweep_parked_runs(
    api: GitHubApi, heads: Sequence[PullHead], config: Dict[str, Any], dry_run: bool
) -> Tuple[int, int, int, Set[str], Set[int]]:
    """
    Approve parked runs across every head, re-listing while any head is unsettled.

    The wait is per attempt, not per head, so total added latency is bounded by
    ``poll_attempts * poll_interval_seconds`` however many PRs are open.
    """
    approved = 0
    refused = 0
    raced = 0
    touched: Set[str] = set()
    deferred: Set[int] = set()
    budget = config["max_approvals"]
    for attempt in range(config["poll_attempts"]):
        outcome = _sweep_once(api, heads, budget, dry_run)
        budget = outcome.budget
        approved += outcome.approved
        refused += outcome.refused
        raced += outcome.raced
        touched |= outcome.touched
        # Only the LAST pass decides what was left behind: an earlier pass may
        # have deferred a PR that a later one, with budget freed by nothing
        # needing approval, went on to clear.
        deferred = set(outcome.deferred)
        last_attempt = attempt + 1 >= config["poll_attempts"]
        # Stop once nothing is outstanding, on a dry run (which changes nothing,
        # so a second look is pointless), once approval was refused (retrying a
        # permission failure only delays the report), or once the budget is
        # gone (further passes cannot approve anything).
        if not outcome.unsettled or dry_run or refused or budget <= 0 or last_attempt:
            break
        time.sleep(config["poll_interval_seconds"])
    return approved, refused, raced, touched, deferred


def collect_heads(pulls: Sequence[Dict[str, Any]], repository: str) -> List[PullHead]:
    """Reduce the PR listing to the heads this tool acts on, flagging fork origins."""
    heads: List[PullHead] = []
    for pull in pulls:
        head = pull.get("head") or {}
        sha = str(head.get("sha") or "")
        if not sha:
            continue
        head_repo = str((head.get("repo") or {}).get("full_name") or "")
        heads.append(
            PullHead(
                number=int(pull["number"]),
                sha=sha,
                updated_at=pull.get("updated_at"),
                url=str(pull.get("html_url") or ""),
                same_repo=head_repo == repository,
            )
        )
    return heads


def select_heads(heads: Sequence[PullHead], only_pr: int) -> List[PullHead]:
    """
    Narrow the sweep to a single pull request when one fired the workflow.

    A sweep costs roughly ``poll_attempts + 2`` API calls per head, so sweeping
    every open PR on every pull-request event multiplies the per-event cost by
    the size of the queue against the shared 1,000/hour ``GITHUB_TOKEN`` budget.
    The scheduled and base-push sweeps keep covering every head; an event-driven
    sweep only needs the head that moved.

    Selecting nothing is returned as an empty list rather than silently falling
    back to "all heads": the fallback would turn a closed or renumbered PR into
    a full-queue sweep, which is the cost this exists to avoid.
    """
    if only_pr <= 0:
        return list(heads)
    return [head for head in heads if head.number == only_pr]


def publish_dispatch_states(
    api: GitHubApi,
    heads: Sequence[PullHead],
    config: Dict[str, Any],
    dry_run: bool,
    pool_serving: Optional[bool],
    overdue: Sequence[OverdueJob] = (),
) -> int:
    """Write the dispatch commit status for each head. Returns the not-dispatched count."""
    now = datetime.now(timezone.utc)
    wedged = overdue_by_head(overdue)
    blocked = 0
    for head in heads:
        try:
            runs = api.runs_for_sha(head.sha)
        except WatchdogApiError as exc:
            # Never assert "CI never dispatched" on the strength of an API
            # failure — say the state is unknown, and say why.
            state, description = "pending", _truncate(f"dispatch state unknown (API error: {exc})")
            runs = []
        else:
            state, description = classify_dispatch(
                runs,
                head.updated_at,
                now,
                config["grace_minutes"],
                config["stall_minutes"],
                pool_serving is not False,
                wedged.get(head.sha, ()),
            )
        target = _run_url(api.repository, runs[0]) if runs else head.url
        if dry_run:
            print(f"  PR #{head.number}: would set {state} — {description}")
        else:
            code = api.set_status(head.sha, state, config["status_context"], description, target)
            print(f"  PR #{head.number}: {state} — {description} (status API HTTP {code})")
        if state != "success":
            blocked += 1
    return blocked


def report_overdue_jobs(overdue: Sequence[OverdueJob], overdue_minutes: int) -> None:
    """
    Print a named annotation for every wedged self-hosted job.

    Deliberately an annotation rather than an exit code in the dispatch sweep:
    the actionable signal is the FAILING COMMIT STATUS published on the head the
    wedged job belongs to, and failing every other PR's sweep because one PR is
    stuck would spread a precise fault into indiscriminate noise. The starvation
    probe, which is a dedicated repository-wide health check rather than a
    per-PR one, does exit non-zero — see :func:`check_runner_starvation`.
    """
    if not overdue:
        return
    print(
        f"::error::{len(overdue)} self-hosted job(s) still executing after {overdue_minutes}m. "
        "Every job in this repository declares a shorter timeout, so these are wedged, not slow. "
        "They hold the singleton runner and any required context they carry."
    )
    for entry in overdue:
        print(f"  {entry.describe()} on {entry.head_sha[:12] or 'unknown head'} ({entry.url})")


def check_dispatch(api: GitHubApi, config: Dict[str, Any], dry_run: bool = False) -> int:
    """Approve what can be approved, then publish dispatch state on every open PR."""
    if dry_run:
        print("DRY RUN: nothing is approved, no commit status is written, and no probe is issued.")
    pulls = api.open_pull_requests(config["base_branch"])
    heads = collect_heads(pulls, api.repository)
    forks = sum(1 for head in heads if not head.same_repo)
    print(
        f"Open PRs targeting {config['base_branch']}: {len(pulls)} ({forks} from forks, never auto-approved)"
    )

    only_pr = config.get("only_pr", 0)
    if only_pr:
        heads = select_heads(heads, only_pr)
        print(f"Scoped to PR #{only_pr}: {len(heads)} head(s) selected")
        if not heads:
            print(
                f"PR #{only_pr} is not an open PR targeting {config['base_branch']} — nothing to sweep."
            )
            return 0

    permitted, explanation = probe_approval_capability(api, dry_run)
    print(f"Approval capability probe: {explanation}")

    approved, refused, raced, _touched, deferred = sweep_parked_runs(api, heads, config, dry_run)
    pool = inspect_self_hosted_pool(api, config["max_job_lookups"], config["job_overdue_minutes"])
    report_overdue_jobs(pool.overdue, config["job_overdue_minutes"])
    blocked = publish_dispatch_states(api, heads, config, dry_run, pool.serving, pool.overdue)

    print(
        f"Sweep complete: {approved} approved, {raced} already released, "
        f"{refused} refused, {blocked} PR(s) not dispatched."
    )
    if raced:
        print(
            f"{raced} run(s) had already been released by a concurrent sweep — routine, not a failure."
        )

    failed = False
    if deferred and not dry_run:
        # Silent deferral is the failure this tool exists to remove. Saying
        # "next sweep" is not enough when the schedule that would provide one
        # has never fired, so the run goes red and names what was left.
        left = ", ".join(f"#{number}" for number in sorted(deferred))
        print(
            "::error::"
            + budget_exhausted_message(deferred, config["max_approvals"]).replace("\n", "%0A")
        )
        print(budget_exhausted_message(deferred, config["max_approvals"]))
        print(f"PR(s) left with parked runs: {left}")
        failed = True

    if refused or permitted is False:
        print("::error::" + REMEDIATION.replace("\n", "%0A"))
        print(REMEDIATION)
        failed = True
    if failed:
        return 1
    if permitted is None and not dry_run:
        # Unresolved is not benign: the repair path is unproven until a probe
        # returns a verdict, and saying nothing here is the exact failure mode
        # this module was written to remove. A dry run is the one exception —
        # it skips the probe deliberately, and `--check probe` answers the
        # question on its own, so warning here would be noise that trains
        # readers to ignore the warning that matters.
        print(
            f"::warning::Approval capability is UNRESOLVED — {explanation}. Do not treat #12823 as proven fixed."
        )
    return 0


def check_probe(api: GitHubApi) -> int:
    """
    Print the credential verdict and nothing else.

    Separate from ``dispatch`` so the question can be answered from a pull
    request without approving anything or writing any status, and separate from
    ``--dry-run`` because a dry run issues no approve request and therefore
    cannot answer it.
    """
    permitted, explanation = probe_approval_capability(api)
    print(f"Approval capability probe: {explanation}")
    if permitted is False:
        print("::error::" + REMEDIATION.replace("\n", "%0A"))
        print(REMEDIATION)
        return 1
    if permitted is None:
        print(f"::warning::Approval capability is UNRESOLVED — {explanation}")
        return 0
    print("This credential may approve parked runs; no owner action is required for #12823.")
    return 0


def check_runner_starvation(api: GitHubApi, config: Dict[str, Any]) -> int:
    """
    Report a self-hosted pool that is not serving the work it has been given.

    Two distinct faults produce the same user-visible symptom — a required
    context that never reaches a conclusion — and both are reported here:

    * **Starvation (#13045).** Runs are created but never allocate a job because
      no runner is serving the pool. They sit ``queued`` with ``jobs: []``.
    * **A wedged job (#13341).** A job DID start and then stopped making
      progress, so GitHub's runner-side ``timeout-minutes`` enforcement never
      fires and the job holds the singleton indefinitely.

    The wedged case is checked unconditionally, not only when something is
    queued behind it. It is a fault the moment it happens — it is holding a
    required status check — and waiting for a queue to build before saying so
    would reproduce the three-hour silence that #13341 records.
    """
    now = datetime.now(timezone.utc)
    # Filtered server-side: an unfiltered page is dominated by the hundreds of
    # parked runs this repository carries, which can hide every queued run.
    #
    # KNOWN LIMIT, stated rather than papered over: this listing cannot tell the
    # two runner pools apart. Labels live on JOBS, and a starved run has no jobs
    # — that absence IS the condition being detected — so a run queued past the
    # threshold cannot be attributed to the self-hosted pool from the API alone,
    # and a GitHub-hosted capacity backlog would read the same way. The verdict
    # below is therefore never taken from the queue on its own; it is qualified
    # by the pool inspection, which IS label-attributed. Whether a starved queue
    # can be attributed to a pool by any means the workflow token can read
    # remains open.
    queued = api.recent_runs(run_status="queued")
    starved = starved_runs(queued, now, config["stall_minutes"])
    pool = inspect_self_hosted_pool(
        api, config["max_job_lookups"], config["job_overdue_minutes"], now
    )
    report_overdue_jobs(pool.overdue, config["job_overdue_minutes"])

    if not starved:
        if pool.overdue:
            return 1
        print(
            f"No run has been queued longer than {config['stall_minutes']}m — runner pool is keeping up."
        )
        return 0

    if pool.serving is None:
        print(
            f"::warning::{len(starved)} run(s) queued over {config['stall_minutes']}m; runner liveness UNKNOWN"
        )
        return 1 if pool.overdue else 0
    if pool.serving:
        # `pool.serving` excludes wedged jobs, so this really is healthy work in
        # flight rather than the hung job that used to masquerade as liveness.
        print(
            f"{len(starved)} run(s) queued over {config['stall_minutes']}m, but a self-hosted job is executing — "
            "contention, not an outage."
        )
        return 1 if pool.overdue else 0

    reason = (
        "while a self-hosted job is wedged"
        if pool.overdue
        else "while no self-hosted job is executing"
    )
    print(
        f"::error::{len(starved)} workflow run(s) queued over {config['stall_minutes']}m {reason}"
    )
    for run in starved:
        waited = age_minutes(run.get("created_at"), now)
        waited_text = f"{waited:.0f}m" if waited is not None else "unknown"
        print(
            f"  {run.get('name')} on {run.get('head_branch')} — queued {waited_text} ({_run_url(api.repository, run)})"
        )
    return 1


def load_config() -> Dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token:
        raise WatchdogConfigError("GITHUB_TOKEN is required")
    if "/" not in repository:
        raise WatchdogConfigError("GITHUB_REPOSITORY must be set to 'owner/repo'")
    return {
        "token": token,
        "repository": repository,
        "api_root": os.environ.get("GITHUB_API_URL", DEFAULT_API_ROOT),
        "base_branch": os.environ.get("WATCHDOG_BASE_BRANCH", DEFAULT_BASE_BRANCH),
        "grace_minutes": _env_int("WATCHDOG_GRACE_MINUTES", DEFAULT_GRACE_MINUTES),
        "stall_minutes": _env_int("WATCHDOG_STALL_MINUTES", DEFAULT_STALL_MINUTES),
        "max_approvals": _env_int("WATCHDOG_MAX_APPROVALS", DEFAULT_MAX_APPROVALS),
        "poll_attempts": _env_int("WATCHDOG_POLL_ATTEMPTS", DEFAULT_POLL_ATTEMPTS),
        "poll_interval_seconds": _env_int(
            "WATCHDOG_POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS
        ),
        "status_context": os.environ.get("WATCHDOG_STATUS_CONTEXT", DEFAULT_STATUS_CONTEXT),
        "max_job_lookups": _env_int("WATCHDOG_MAX_JOB_LOOKUPS", DEFAULT_MAX_JOB_LOOKUPS),
        "job_overdue_minutes": _env_int(
            "WATCHDOG_JOB_OVERDUE_MINUTES", DEFAULT_JOB_OVERDUE_MINUTES
        ),
        "only_pr": _env_non_negative_int("WATCHDOG_ONLY_PR", DEFAULT_ONLY_PR),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check",
        choices=("dispatch", "probe", "runner-starvation"),
        default="dispatch",
        help="dispatch: approve parked runs and publish PR dispatch state; "
        "probe: print only whether this credential may approve runs; "
        "runner-starvation: report runs queued while the self-hosted pool is idle",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be approved and which statuses would be published, changing nothing "
        "(issues no approve request, so the capability probe is skipped)",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config()
    except WatchdogConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    api = GitHubApi(config["token"], config["repository"], config["api_root"])
    try:
        if args.check == "dispatch":
            return check_dispatch(api, config, dry_run=args.dry_run)
        if args.check == "probe":
            return check_probe(api)
        return check_runner_starvation(api, config)
    except WatchdogError as exc:
        print(f"::error::watchdog could not complete: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
