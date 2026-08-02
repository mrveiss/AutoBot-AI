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
  threshold while no self-hosted job is executing. The ``/actions/runners``
  administration endpoint returns ``403 Resource not accessible by
  integration`` for ``GITHUB_TOKEN``, so runner liveness is inferred from
  ``GET /actions/runs/{id}/jobs`` labels instead.

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
    WATCHDOG_MAX_APPROVALS           per-sweep approval cap (blast-radius guard)
    WATCHDOG_POLL_ATTEMPTS           re-list attempts while runs appear
    WATCHDOG_POLL_INTERVAL_SECONDS   delay between those attempts
    WATCHDOG_STATUS_CONTEXT          commit status context name
    WATCHDOG_MAX_JOB_LOOKUPS         runs inspected for runner liveness per check

Exit codes:
    0  nothing wrong, or everything wrong was repaired
    1  parked runs exist that this token is not permitted to approve
       (owner action required — see the printed remediation)
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

# Transport failure — no HTTP status was ever received.
NO_RESPONSE_STATUS = 0

DEFAULT_API_ROOT = "https://api.github.com"
DEFAULT_BASE_BRANCH = "Dev_new_gui"
DEFAULT_GRACE_MINUTES = 10
DEFAULT_STALL_MINUTES = 45
DEFAULT_MAX_APPROVALS = 30
DEFAULT_POLL_ATTEMPTS = 3
DEFAULT_POLL_INTERVAL_SECONDS = 20
DEFAULT_STATUS_CONTEXT = "ci-dispatch-watchdog"
DEFAULT_MAX_JOB_LOOKUPS = 10
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30


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


def starved_runs(runs: Sequence[Dict[str, Any]], now: datetime, stall_minutes: int) -> List[Dict[str, Any]]:
    """Runs queued longer than *stall_minutes* without allocating a job."""
    starved = []
    for run in runs:
        if not is_unstarted(run):
            continue
        waited = age_minutes(run.get("created_at"), now)
        if waited is not None and waited >= stall_minutes:
            starved.append(run)
    return starved


def job_is_self_hosted(job: Dict[str, Any]) -> bool:
    """True when this job was dispatched to the self-hosted pool."""
    labels = [str(label).lower() for label in (job.get("labels") or [])]
    return SELF_HOSTED_LABEL in labels


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
) -> Tuple[str, str]:
    """
    Decide the commit-status state for one PR head.

    Returns ``(state, description)`` where *state* is a GitHub commit-status
    state. The watchdog never reports ``success`` for a head whose CI has not
    demonstrably dispatched, so "no failures" can never be mistaken for
    "verified" (#12823 option 3, #13045 property 1).
    """
    parked = [run for run in runs if is_parked(run)]
    if parked:
        names = ", ".join(sorted({str(run.get("name", "?")) for run in parked})[:3])
        return (
            "failure",
            _truncate(f"{len(parked)} run(s) parked awaiting approval and never started: {names}"),
        )

    starved = starved_runs(runs, now, stall_minutes)
    if starved:
        names = ", ".join(sorted({str(run.get("name", "?")) for run in starved})[:3])
        if pool_serving:
            # Contention, not an outage — still never green, because the head is
            # demonstrably not verified yet.
            return (
                "pending",
                _truncate(f"{len(starved)} run(s) queued over {stall_minutes}m behind a busy runner pool: {names}"),
            )
        return (
            "failure",
            _truncate(f"{len(starved)} run(s) queued over {stall_minutes}m with no runner available: {names}"),
        )

    if not runs:
        waited = age_minutes(head_pushed_at, now)
        if waited is None or waited >= grace_minutes:
            return (
                "failure",
                _truncate(f"no workflow runs exist for this commit after {grace_minutes}m — CI never dispatched"),
            )
        return ("pending", _truncate("no workflow runs yet — still inside the dispatch grace window"))

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

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[int, Any]:
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
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - fixed api host
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
        status, body = self.request("GET", f"/repos/{self.repository}/actions/runs/{run_id}/jobs?{query}")
        if status != 200 or not isinstance(body, dict):
            raise WatchdogApiError(f"cannot list jobs for run {run_id} (HTTP {status}): {body}")
        return list(body.get("jobs") or [])

    def approve_run(self, run_id: int) -> Tuple[int, str]:
        status, body = self.request("POST", f"/repos/{self.repository}/actions/runs/{run_id}/approve")
        message = ""
        if isinstance(body, dict):
            message = str(body.get("message", ""))
        return status, message

    def set_status(self, sha: str, state: str, context: str, description: str, target_url: str) -> int:
        payload: Dict[str, Any] = {
            "state": state,
            "context": context,
            "description": description,
        }
        if target_url:
            payload["target_url"] = target_url
        status, _ = self.request("POST", f"/repos/{self.repository}/statuses/{sha}", payload)
        return status


def self_hosted_pool_is_serving(api: GitHubApi, max_lookups: int) -> Optional[bool]:
    """
    True when a job is executing on the SELF-HOSTED pool right now.

    Any in-progress run used to count, which made this near-permanently true:
    ``code-quality``, ``ci.yml`` and this very watchdog's own quarter-hourly
    cron all run on GitHub-hosted runners, so "something is executing" says
    nothing about the singleton machine that #13045 is about. Runner liveness is
    therefore established from job labels — the closest signal to
    ``/actions/runners`` that a workflow token is allowed to read.

    Returns ``None`` when the answer could not be established, so the caller can
    say "unknown" instead of inventing a verdict.
    """
    try:
        running = api.recent_runs(per_page=max_lookups, run_status="in_progress")
    except WatchdogApiError as exc:
        print(f"  runner liveness unknown: {exc}")
        return None
    for run in running[:max_lookups]:
        try:
            jobs = api.run_jobs(int(run["id"]))
        except WatchdogApiError as exc:
            print(f"  runner liveness partial: {exc}")
            continue
        for job in jobs:
            if job.get("status") == "in_progress" and job_is_self_hosted(job):
                return True
    return False


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
        return None, "unresolved — the probe run was not found (404); the token may lack read access"
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
) -> Tuple[int, int, int]:
    """Approve the eligible parked runs of one head. Returns (approved, refused, budget)."""
    approved = 0
    refused = 0
    for run in runs:
        eligible, reason = is_approvable(run, api.repository)
        if not eligible:
            if is_parked(run):
                print(f"  PR #{number}: leaving '{run.get('name')}' parked — {reason}")
            continue
        if budget <= 0:
            print(f"  PR #{number}: approval budget exhausted, deferring to the next sweep")
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
        else:
            refused += 1
            print(f"  PR #{number}: could NOT approve '{run.get('name')}' — HTTP {status}: {message}")
    return approved, refused, budget


def _sweep_once(
    api: GitHubApi, heads: Sequence[PullHead], budget: int, dry_run: bool
) -> Tuple[int, int, int, bool, Set[str]]:
    """One pass over every head. Returns (approved, refused, budget, unsettled, touched)."""
    approved = 0
    refused = 0
    unsettled = False
    touched: Set[str] = set()
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
                print(f"  PR #{head.number}: fork pull request — parked runs left for a human to approve")
            continue
        head_approved, head_refused, budget = _approve_head(api, head.number, runs, budget, dry_run)
        if head_approved:
            touched.add(head.sha)
        approved += head_approved
        refused += head_refused
    return approved, refused, budget, unsettled, touched


def sweep_parked_runs(
    api: GitHubApi, heads: Sequence[PullHead], config: Dict[str, Any], dry_run: bool
) -> Tuple[int, int, Set[str]]:
    """
    Approve parked runs across every head, re-listing while any head is unsettled.

    The wait is per attempt, not per head, so total added latency is bounded by
    ``poll_attempts * poll_interval_seconds`` however many PRs are open.
    """
    approved = 0
    refused = 0
    touched: Set[str] = set()
    budget = config["max_approvals"]
    for attempt in range(config["poll_attempts"]):
        pass_approved, pass_refused, budget, unsettled, pass_touched = _sweep_once(api, heads, budget, dry_run)
        approved += pass_approved
        refused += pass_refused
        touched |= pass_touched
        last_attempt = attempt + 1 >= config["poll_attempts"]
        # Stop once nothing is outstanding, on a dry run (which changes nothing,
        # so a second look is pointless), or once approval was refused —
        # retrying a permission failure only delays the report.
        if not unsettled or dry_run or refused or last_attempt:
            break
        time.sleep(config["poll_interval_seconds"])
    return approved, refused, touched


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


def publish_dispatch_states(
    api: GitHubApi,
    heads: Sequence[PullHead],
    config: Dict[str, Any],
    dry_run: bool,
    pool_serving: Optional[bool],
) -> int:
    """Write the dispatch commit status for each head. Returns the not-dispatched count."""
    now = datetime.now(timezone.utc)
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


def check_dispatch(api: GitHubApi, config: Dict[str, Any], dry_run: bool = False) -> int:
    """Approve what can be approved, then publish dispatch state on every open PR."""
    if dry_run:
        print("DRY RUN: nothing is approved, no commit status is written, and no probe is issued.")
    pulls = api.open_pull_requests(config["base_branch"])
    heads = collect_heads(pulls, api.repository)
    forks = sum(1 for head in heads if not head.same_repo)
    print(f"Open PRs targeting {config['base_branch']}: {len(pulls)} ({forks} from forks, never auto-approved)")

    permitted, explanation = probe_approval_capability(api, dry_run)
    print(f"Approval capability probe: {explanation}")

    approved, refused, _touched = sweep_parked_runs(api, heads, config, dry_run)
    pool_serving = self_hosted_pool_is_serving(api, config["max_job_lookups"])
    blocked = publish_dispatch_states(api, heads, config, dry_run, pool_serving)

    print(f"Sweep complete: {approved} approved, {refused} refused, {blocked} PR(s) not dispatched.")

    if refused or permitted is False:
        print("::error::" + REMEDIATION.replace("\n", "%0A"))
        print(REMEDIATION)
        return 1
    if permitted is None and not dry_run:
        # Unresolved is not benign: the repair path is unproven until a probe
        # returns a verdict, and saying nothing here is the exact failure mode
        # this module was written to remove. A dry run is the one exception —
        # it skips the probe deliberately, and `--check probe` answers the
        # question on its own, so warning here would be noise that trains
        # readers to ignore the warning that matters.
        print(f"::warning::Approval capability is UNRESOLVED — {explanation}. Do not treat #12823 as proven fixed.")
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
    """Report runs queued past the threshold while the self-hosted pool is idle (#13045)."""
    now = datetime.now(timezone.utc)
    # Filtered server-side: an unfiltered page is dominated by the hundreds of
    # parked runs this repository carries, which can hide every queued run.
    queued = api.recent_runs(run_status="queued")
    starved = starved_runs(queued, now, config["stall_minutes"])
    if not starved:
        print(f"No run has been queued longer than {config['stall_minutes']}m — runner pool is keeping up.")
        return 0

    serving = self_hosted_pool_is_serving(api, config["max_job_lookups"])
    if serving is None:
        print(f"::warning::{len(starved)} run(s) queued over {config['stall_minutes']}m; runner liveness UNKNOWN")
        return 0
    if serving:
        print(
            f"{len(starved)} run(s) queued over {config['stall_minutes']}m, but a self-hosted job is executing — "
            "contention, not an outage."
        )
        return 0

    print(
        f"::error::{len(starved)} workflow run(s) queued over {config['stall_minutes']}m "
        "while no self-hosted job is executing"
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
        "poll_interval_seconds": _env_int("WATCHDOG_POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS),
        "status_context": os.environ.get("WATCHDOG_STATUS_CONTEXT", DEFAULT_STATUS_CONTEXT),
        "max_job_lookups": _env_int("WATCHDOG_MAX_JOB_LOOKUPS", DEFAULT_MAX_JOB_LOOKUPS),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
