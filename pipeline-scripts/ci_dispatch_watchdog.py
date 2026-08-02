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
  head commit of each open PR (bounded), and then publishes a commit status
  on every open PR head describing the dispatch state. A PR whose CI never
  dispatched therefore carries a visible, named, non-green context instead of
  silently reading as ready.
* ``--check runner-starvation`` — reports runs that have been queued past a
  threshold without ever creating a job, i.e. an empty runner pool. This uses
  only ``GET /actions/runs``; the ``/actions/runners`` administration
  endpoint returns ``403 Resource not accessible by integration`` for
  ``GITHUB_TOKEN`` and cannot be used from a workflow.

Usage:
    pipeline-scripts/ci_dispatch_watchdog.py --check dispatch
    pipeline-scripts/ci_dispatch_watchdog.py --check dispatch --dry-run
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

Exit codes:
    0  nothing wrong, or everything wrong was repaired
    1  parked runs exist that this token is not permitted to approve
       (owner action required — see the printed remediation)
    2  internal error (missing configuration, unusable API response)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

# GitHub returns this message when the *token* lacks `actions: write`.
PERMISSION_DENIED_MARKER = "resource not accessible"
# ...and this one when the token is fine but the run is in the wrong state.
# Seeing it proves the credential may approve runs.
NOT_WAITING_MARKER = "not waiting for approval"

# GitHub truncates commit-status descriptions beyond this length.
MAX_STATUS_DESCRIPTION = 140

# Run states that mean "created but no job has started yet".
UNSTARTED_RUN_STATUSES = frozenset({"queued", "waiting", "pending", "requested"})

DEFAULT_API_ROOT = "https://api.github.com"
DEFAULT_BASE_BRANCH = "Dev_new_gui"
DEFAULT_GRACE_MINUTES = 10
DEFAULT_STALL_MINUTES = 30
DEFAULT_MAX_APPROVALS = 30
DEFAULT_POLL_ATTEMPTS = 3
DEFAULT_POLL_INTERVAL_SECONDS = 20
DEFAULT_STATUS_CONTEXT = "ci-dispatch-watchdog"


class WatchdogConfigError(RuntimeError):
    """Raised when required environment configuration is absent."""


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


def starved_runs(runs: Sequence[Dict[str, Any]], now: datetime, stall_minutes: int) -> List[Dict[str, Any]]:
    """Runs queued longer than *stall_minutes* — an empty runner pool."""
    starved = []
    for run in runs:
        if not is_unstarted(run):
            continue
        waited = age_minutes(run.get("created_at"), now)
        if waited is not None and waited >= stall_minutes:
            starved.append(run)
    return starved


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
        return (
            "failure",
            _truncate(f"{len(starved)} run(s) queued over {stall_minutes}m with no runner: {names}"),
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

    def __init__(self, token: str, repository: str, api_root: str = DEFAULT_API_ROOT) -> None:
        self.token = token
        self.repository = repository
        self.api_root = api_root.rstrip("/")

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[int, Any]:
        """Issue a request and return ``(status_code, decoded_body)``."""
        url = path if path.startswith("http") else f"{self.api_root}/{path.lstrip('/')}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url=url, method=method, data=data)
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request) as response:  # noqa: S310 - fixed api host
                body = response.read().decode("utf-8")
                return response.status, (json.loads(body) if body else None)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                decoded: Any = json.loads(body) if body else None
            except json.JSONDecodeError:
                decoded = {"message": body}
            return exc.code, decoded

    def open_pull_requests(self, base: str) -> List[Dict[str, Any]]:
        query = urllib.parse.urlencode({"state": "open", "base": base, "per_page": "100"})
        status, body = self.request("GET", f"/repos/{self.repository}/pulls?{query}")
        if status != 200 or not isinstance(body, list):
            raise WatchdogConfigError(f"cannot list open PRs (HTTP {status}): {body}")
        return body

    def runs_for_sha(self, sha: str) -> List[Dict[str, Any]]:
        query = urllib.parse.urlencode({"head_sha": sha, "per_page": "100"})
        status, body = self.request("GET", f"/repos/{self.repository}/actions/runs?{query}")
        if status != 200 or not isinstance(body, dict):
            return []
        return list(body.get("workflow_runs") or [])

    def recent_runs(self, per_page: int = 100) -> List[Dict[str, Any]]:
        query = urllib.parse.urlencode({"per_page": str(per_page)})
        status, body = self.request("GET", f"/repos/{self.repository}/actions/runs?{query}")
        if status != 200 or not isinstance(body, dict):
            raise WatchdogConfigError(f"cannot list workflow runs (HTTP {status}): {body}")
        return list(body.get("workflow_runs") or [])

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


def interpret_probe(status: int, message: str) -> Tuple[bool, str]:
    """
    Turn an ``approve`` response for a run that is NOT awaiting approval into a
    verdict about the *credential*.

    A token that holds ``actions: write`` is rejected on state grounds
    ("This workflow run is not waiting for approval"); a token that does not is
    rejected on permission grounds ("Resource not accessible by integration").
    The two are distinguishable, so capability can be established without
    approving anything and without any side effect.
    """
    lowered = message.lower()
    if PERMISSION_DENIED_MARKER in lowered:
        return False, "token lacks permission to approve workflow runs"
    if NOT_WAITING_MARKER in lowered:
        return True, "token may approve workflow runs (rejected on run state, not permission)"
    if status in (200, 201, 204):
        return True, "token may approve workflow runs (approval accepted)"
    return True, f"inconclusive probe (HTTP {status}: {message or 'no message'}) — assuming permitted"


def probe_approval_capability(api: GitHubApi) -> Tuple[Optional[bool], str]:
    """Establish whether this credential may approve runs, without side effects."""
    try:
        runs = api.recent_runs(per_page=20)
    except WatchdogConfigError as exc:
        return None, f"probe skipped: {exc}"
    candidates = [run for run in runs if run.get("status") == "completed" and not is_parked(run)]
    if not candidates:
        return None, "probe skipped: no completed run available to probe against"
    status, message = api.approve_run(int(candidates[0]["id"]))
    permitted, explanation = interpret_probe(status, message)
    return permitted, explanation


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
    so an empty result means "too early", not "nothing to approve". Treating it
    as final was the whole bug — the sweep would look once, find nothing, and
    leave the parked runs that appeared a second later untouched until the next
    scheduled tick. A head that already has runs and no parked ones is genuinely
    settled.
    """
    if not runs:
        return True
    return any(is_parked(run) for run in runs)


def _approve_head(
    api: GitHubApi, number: int, runs: Sequence[Dict[str, Any]], budget: int, dry_run: bool
) -> Tuple[int, int, int]:
    """Approve the parked runs of one head. Returns (approved, refused, budget)."""
    approved = 0
    refused = 0
    for run in runs:
        if not is_parked(run):
            continue
        if dry_run:
            print(f"  PR #{number}: would approve '{run.get('name')}' ({run['id']})")
            continue
        if budget <= 0:
            print(f"  PR #{number}: approval budget exhausted, deferring to the next sweep")
            break
        budget -= 1
        status, message = api.approve_run(int(run["id"]))
        if status in (200, 201, 204):
            approved += 1
            print(f"  PR #{number}: approved '{run.get('name')}' ({run['id']})")
        else:
            refused += 1
            print(f"  PR #{number}: could NOT approve '{run.get('name')}' — HTTP {status}: {message}")
    return approved, refused, budget


def sweep_parked_runs(
    api: GitHubApi,
    heads: Sequence[Tuple[int, str, Optional[str], str]],
    config: Dict[str, Any],
    dry_run: bool,
) -> Tuple[int, int]:
    """
    Approve parked runs across every head, re-listing while any head is unsettled.

    The wait is per attempt, not per head, so total added latency is bounded by
    ``poll_attempts * poll_interval_seconds`` however many PRs are open.
    """
    approved = 0
    refused = 0
    budget = config["max_approvals"]
    for attempt in range(config["poll_attempts"]):
        unsettled = False
        for number, sha, _updated_at, _url in heads:
            runs = api.runs_for_sha(sha)
            if needs_another_look(runs):
                unsettled = True
            head_approved, head_refused, budget = _approve_head(api, number, runs, budget, dry_run)
            approved += head_approved
            refused += head_refused
        last_attempt = attempt + 1 >= config["poll_attempts"]
        # Stop early once nothing is outstanding, on a dry run (which changes
        # nothing, so a second look is pointless), or once approval was refused
        # — retrying a permission failure only delays the report.
        if not unsettled or dry_run or refused or last_attempt:
            break
        time.sleep(config["poll_interval_seconds"])
    return approved, refused


def collect_heads(pulls: Sequence[Dict[str, Any]]) -> List[Tuple[int, str, Optional[str], str]]:
    """Reduce the PR listing to ``(number, head_sha, updated_at, html_url)`` tuples."""
    heads: List[Tuple[int, str, Optional[str], str]] = []
    for pull in pulls:
        head = pull.get("head") or {}
        sha = str(head.get("sha") or "")
        if not sha:
            continue
        heads.append((int(pull["number"]), sha, pull.get("updated_at"), str(pull.get("html_url") or "")))
    return heads


def publish_dispatch_states(
    api: GitHubApi,
    heads: Sequence[Tuple[int, str, Optional[str], str]],
    config: Dict[str, Any],
    dry_run: bool,
) -> int:
    """Write the dispatch commit status for each head. Returns the not-dispatched count."""
    now = datetime.now(timezone.utc)
    blocked = 0
    for number, sha, updated_at, url in heads:
        runs = api.runs_for_sha(sha)
        state, description = classify_dispatch(runs, updated_at, now, config["grace_minutes"], config["stall_minutes"])
        target = _run_url(api.repository, runs[0]) if runs else url
        if dry_run:
            print(f"  PR #{number}: would set {state} — {description}")
        else:
            code = api.set_status(sha, state, config["status_context"], description, target)
            print(f"  PR #{number}: {state} — {description} (status API HTTP {code})")
        if state != "success":
            blocked += 1
    return blocked


def check_dispatch(api: GitHubApi, config: Dict[str, Any], dry_run: bool = False) -> int:
    """Approve what can be approved, then publish dispatch state on every open PR."""
    if dry_run:
        print("DRY RUN: no run will be approved and no commit status will be written.")
    pulls = api.open_pull_requests(config["base_branch"])
    print(f"Open PRs targeting {config['base_branch']}: {len(pulls)}")

    permitted, explanation = probe_approval_capability(api)
    print(f"Approval capability probe: {explanation}")

    heads = collect_heads(pulls)
    approved, refused = sweep_parked_runs(api, heads, config, dry_run)
    blocked = publish_dispatch_states(api, heads, config, dry_run)

    print(f"Sweep complete: {approved} approved, {refused} refused, {blocked} PR(s) not dispatched.")

    if refused or permitted is False:
        print("::error::" + REMEDIATION.replace("\n", "%0A"))
        print(REMEDIATION)
        return 1
    return 0


def check_runner_starvation(api: GitHubApi, config: Dict[str, Any]) -> int:
    """Report runs that were created but never allocated a job (#13045)."""
    runs = api.recent_runs()
    now = datetime.now(timezone.utc)
    starved = starved_runs(runs, now, config["stall_minutes"])
    if not starved:
        print(f"No run has been queued longer than {config['stall_minutes']}m — runner pool is serving work.")
        return 0
    print(f"::error::{len(starved)} workflow run(s) queued over {config['stall_minutes']}m with no runner available")
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
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--check",
        choices=("dispatch", "runner-starvation"),
        default="dispatch",
        help="dispatch: approve parked runs and publish PR dispatch state; "
        "runner-starvation: report runs queued with no runner",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be approved and which statuses would be published, changing nothing",
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
        return check_runner_starvation(api, config)
    except WatchdogConfigError as exc:
        print(f"API error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
