#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Classify WHY a check on a commit is red — #15139.

A red tile on a pull request is produced by at least four different conditions
that GitHub renders identically, and the repository's standing rule is that red
CI never merges. A rule that cannot tell those conditions apart is the reason
people override it, so this tool names the cause instead of leaving the reader
to guess:

* ``runner-starvation`` — the run never obtained a runner. Its job executed
  **zero** steps, or the run has no job at all (``jobs: []``). Nothing was
  tested. Re-queueable.
* ``provisioning-failure`` — the job got a runner and ran, but the first step
  that failed is toolchain provisioning (a local composite action, an
  ``actions/setup-*``, a checkout, a cache restore). The observed instance is
  ``apt-get`` returning exit 124 three times inside
  ``.github/actions/setup-python-suite``; a later test step then fails
  downstream, so the *last* failing step lies about the cause and only the
  *first* one tells the truth. No test result was produced. Re-queueable.
* ``test-failure`` — the first failing step is real work. **Never re-queue.**
* ``superseded`` — ``conclusion: cancelled``, normally a newer push retiring an
  obsolete run. Not a test result; a fresh run must report. ``gh pr checks``
  buckets this under ``fail``, which is why a superseded gate reads as a red
  one to anything parsing that output.
* ``undetermined`` — the cause could not be established. **Deliberately graded
  as a real failure.**

THE STRUCTURAL FACT THIS TOOL EXISTS FOR. ``GET /commits/{sha}/check-runs``
carries no ``steps`` array — only ``GET /actions/jobs/{id}`` does. Any gate that
reads ``steps`` off the listing finds nothing on every check, every time, and
then classifies by whatever its default is. Defaulting to "infrastructure"
turns the merge gate into a re-queue loop that retries genuine test failures
until they merge. Defaulting to "real failure" costs a needless investigation.
Only the second direction is survivable, so an absent ``steps`` array is
``undetermined`` and ``undetermined`` grades as a real failure.

THIS TOOL NEVER MAKES A RED CHECK GREEN. It publishes no commit status, writes
no check conclusion, and re-queues nothing. Every classified cause carries
``blocks_merge=True``; the classification says what to *do* about a red, never
that the red may be ignored. ``--exit-zero`` exists for report-only callers and
still refuses to hide an indeterminate result (see ``resolve_exit_code``).

Usage:
    pipeline-scripts/ci_red_cause.py --pr 15155
    pipeline-scripts/ci_red_cause.py --sha 8d3fa7d2...
    pipeline-scripts/ci_red_cause.py --pr 15155 --json

Environment:
    GITHUB_TOKEN                      required — API credential
    GITHUB_REPOSITORY                 required — "owner/repo"
    GITHUB_API_URL                    API root (default https://api.github.com)
    CI_RED_CAUSE_PROVISIONING_MARKERS comma-separated lowercase substrings that
                                      mark a step as toolchain provisioning
    CI_RED_CAUSE_TIMEOUT_SECONDS      per-request timeout

Exit codes:
    0  check runs were found for the commit and none of them is red.
    1  at least one red check run was found. ALWAYS 1 regardless of cause —
       an infrastructure red is still red.
    2  nothing could be classified: missing configuration, the API could not be
       reached, or the commit carries no check runs at all. Never conflated
       with 0, because "I classified nothing" must not read as "all clear".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

# `pipeline-scripts` is not an importable package name, so the sibling module
# is reached by path — the same idiom as check_gating_precommit_hooks.py. The
# HTTP client is REUSED rather than re-written: one transport, one place where
# a transport failure is turned into a status code instead of a traceback.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci_dispatch_watchdog import (  # noqa: E402
    NO_RESPONSE_STATUS,
    GitHubApi,
    WatchdogConfigError,
)

# Only the Actions app exposes a job with steps. A check run published by any
# other app has no step list to reason about, so its cause is not knowable here.
ACTIONS_APP_SLUG = "github-actions"

# Conclusions that render as a red/failed tile. `gh pr checks` buckets all of
# these under `fail`, which is precisely the conflation #15139 reports.
RED_CONCLUSIONS = frozenset({"failure", "cancelled", "timed_out", "startup_failure", "action_required", "stale"})

# A step with either of these has not run. `skipped` means a condition excluded
# it; `None` means it never got that far.
UNEXECUTED_STEP_CONCLUSIONS = frozenset({"skipped"})

CAUSE_STARVATION = "runner-starvation"
CAUSE_PROVISIONING = "provisioning-failure"
CAUSE_TEST = "test-failure"
CAUSE_SUPERSEDED = "superseded"
CAUSE_UNDETERMINED = "undetermined"

# Causes whose remedy is "run it again". Everything absent from this set must
# never be re-queued — and `undetermined` is absent on purpose.
REQUEUEABLE_CAUSES = frozenset({CAUSE_STARVATION, CAUSE_PROVISIONING})

# Causes that mean a defect in the diff. `undetermined` is graded here because
# mislabelling a real failure as a flake is the costly direction (#15139).
REAL_FAILURE_CAUSES = frozenset({CAUSE_TEST, CAUSE_UNDETERMINED})

# Substrings identifying a step as toolchain provisioning rather than work.
# Deliberately NARROW: a provisioning failure misread as a test failure costs a
# wasted investigation, while a test failure misread as provisioning gets
# re-queued until it merges. The default list matches the step names the runner
# generates for `uses:` steps that carry no `name:`.
DEFAULT_PROVISIONING_MARKERS = (
    "run ./.github/actions/",
    "run actions/setup-",
    "run actions/checkout",
    "run actions/cache",
    "run docker/setup-",
    "set up job",
    "initialize containers",
)

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_API_ROOT = "https://api.github.com"
MAX_CHECKS_PER_PAGE = 100


class RedCause(NamedTuple):
    """One red check run, with the cause that produced it."""

    check_name: str
    conclusion: str
    cause: str
    detail: str
    job_id: Optional[int]
    executed_steps: Optional[int]
    total_steps: Optional[int]
    url: str

    @property
    def requeueable(self) -> bool:
        return self.cause in REQUEUEABLE_CAUSES

    @property
    def real_failure(self) -> bool:
        return self.cause in REAL_FAILURE_CAUSES

    @property
    def blocks_merge(self) -> bool:
        """Always. A cause is information attached to a red, not a way past it."""
        return True

    def as_dict(self) -> Dict[str, Any]:
        payload = dict(self._asdict())
        payload["requeueable"] = self.requeueable
        payload["real_failure"] = self.real_failure
        payload["blocks_merge"] = self.blocks_merge
        return payload


class Report(NamedTuple):
    """The outcome of classifying every check run on one commit."""

    sha: str
    checks_seen: int
    reds: List[RedCause]
    indeterminate: bool
    message: str


def provisioning_markers() -> Tuple[str, ...]:
    """Marker substrings, overridable so a new setup step needs no code change."""
    raw = os.environ.get("CI_RED_CAUSE_PROVISIONING_MARKERS", "").strip()
    if not raw:
        return DEFAULT_PROVISIONING_MARKERS
    parsed = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    return parsed or DEFAULT_PROVISIONING_MARKERS


def request_timeout() -> int:
    raw = os.environ.get("CI_RED_CAUSE_TIMEOUT_SECONDS", "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        return DEFAULT_TIMEOUT_SECONDS
    return int(raw)


def is_red(check_run: Dict[str, Any]) -> bool:
    """A completed check whose conclusion renders as a failed tile."""
    if (check_run.get("status") or "") != "completed":
        return False
    return (check_run.get("conclusion") or "") in RED_CONCLUSIONS


def is_provisioning_step(name: Optional[str]) -> bool:
    lowered = (name or "").strip().lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in provisioning_markers())


def executed_steps(steps: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Steps that actually ran — a queued or skipped step is not evidence."""
    return [
        step
        for step in steps
        if step.get("conclusion") is not None and step.get("conclusion") not in UNEXECUTED_STEP_CONCLUSIONS
    ]


def first_failing_step(steps: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    The EARLIEST failing step, ordered by ``number``.

    Job 98783580325 failed at step 4 (the setup action) and again at step 9 (a
    test step) purely downstream of it. Reading the last failure would call that
    job a test failure when no test ever ran.
    """
    failed = [s for s in steps if (s.get("conclusion") or "") in {"failure", "timed_out"}]
    if not failed:
        return None
    return min(failed, key=lambda s: s.get("number") or 0)


def classify_steps(steps: Sequence[Dict[str, Any]]) -> Tuple[str, str]:
    """Cause and detail from a job's step list. Pure — no I/O."""
    ran = executed_steps(steps)
    if not ran:
        return (
            CAUSE_STARVATION,
            f"job executed 0 of {len(steps)} steps — it never obtained a runner",
        )
    failing = first_failing_step(ran)
    if failing is None:
        return (
            CAUSE_UNDETERMINED,
            f"{len(ran)} steps executed and none of them failed — cause not in the step list",
        )
    name = failing.get("name") or "?"
    number = failing.get("number")
    if is_provisioning_step(name):
        return (
            CAUSE_PROVISIONING,
            f"first failing step {number} ({name!r}) is toolchain provisioning — no test result",
        )
    return CAUSE_TEST, f"first failing step {number} ({name!r}) is a work step"


def classify_job_payload(
    check_run: Dict[str, Any], job: Optional[Dict[str, Any]], fetch_error: str = ""
) -> Tuple[str, str, Optional[int], Optional[int]]:
    """
    Cause, detail, executed-step count and total-step count for one red check.

    Every branch that cannot see a step list lands on ``undetermined``. That is
    the whole point: an unreachable jobs endpoint, a non-Actions app, and a
    payload taken from ``/check-runs`` (which has no ``steps``) all look like
    "zero steps" to a naive reader, and calling any of them starvation is how a
    real failure gets re-queued.
    """
    conclusion = check_run.get("conclusion") or ""
    if conclusion == "cancelled":
        return (
            CAUSE_SUPERSEDED,
            "conclusion is 'cancelled' — normally a newer push retiring this run; "
            "no test result, a fresh run must report",
            None,
            None,
        )
    if fetch_error:
        return CAUSE_UNDETERMINED, fetch_error, None, None
    if job is None:
        return (
            CAUSE_UNDETERMINED,
            "no Actions job could be resolved for this check run",
            None,
            None,
        )
    steps = job.get("steps")
    if not isinstance(steps, list):
        return (
            CAUSE_UNDETERMINED,
            "job payload carried no 'steps' array — /commits/{sha}/check-runs never "
            "has one; only GET /actions/jobs/{id} does",
            None,
            None,
        )
    cause, detail = classify_steps(steps)
    return cause, detail, len(executed_steps(steps)), len(steps)


def fetch_job(api: GitHubApi, job_id: int) -> Tuple[Optional[Dict[str, Any]], str]:
    """``GET /actions/jobs/{id}`` — the only endpoint carrying ``steps``."""
    status, body = api.request("GET", f"/repos/{api.repository}/actions/jobs/{job_id}")
    if status == NO_RESPONSE_STATUS:
        return None, f"jobs endpoint unreachable for job {job_id}: {body}"
    if status != 200 or not isinstance(body, dict):
        return None, f"jobs endpoint returned HTTP {status} for job {job_id}"
    return body, ""


def classify_check_run(api: GitHubApi, check_run: Dict[str, Any]) -> RedCause:
    """Resolve one red check run to its cause, fetching the job when it can."""
    app_slug = ((check_run.get("app") or {}).get("slug")) or ""
    job: Optional[Dict[str, Any]] = None
    fetch_error = ""
    job_id: Optional[int] = None
    if (check_run.get("conclusion") or "") != "cancelled":
        if app_slug != ACTIONS_APP_SLUG:
            fetch_error = f"check published by app {app_slug!r}, which exposes no job steps"
        else:
            # For the Actions app the check-run id IS the job id; details_url is
            # .../actions/runs/{run}/job/{id} with the same number.
            job_id = check_run.get("id")
            if not isinstance(job_id, int):
                fetch_error = "check run carried no usable id"
            else:
                job, fetch_error = fetch_job(api, job_id)
    cause, detail, ran, total = classify_job_payload(check_run, job, fetch_error)
    return RedCause(
        check_name=check_run.get("name") or "?",
        conclusion=check_run.get("conclusion") or "?",
        cause=cause,
        detail=detail,
        job_id=job_id,
        executed_steps=ran,
        total_steps=total,
        url=check_run.get("html_url") or check_run.get("details_url") or "",
    )


def list_check_runs(api: GitHubApi, sha: str) -> Tuple[List[Dict[str, Any]], str]:
    path = f"/repos/{api.repository}/commits/{sha}/check-runs?per_page={MAX_CHECKS_PER_PAGE}"
    status, body = api.request("GET", path)
    if status != 200 or not isinstance(body, dict):
        return [], f"cannot list check runs for {sha} (HTTP {status})"
    runs = body.get("check_runs")
    return (list(runs) if isinstance(runs, list) else []), ""


def head_sha_for_pr(api: GitHubApi, number: int) -> str:
    status, body = api.request("GET", f"/repos/{api.repository}/pulls/{number}")
    if status != 200 or not isinstance(body, dict):
        raise WatchdogConfigError(f"cannot read PR #{number} (HTTP {status})")
    sha = ((body.get("head") or {}).get("sha")) or ""
    if not sha:
        raise WatchdogConfigError(f"PR #{number} has no head sha")
    return sha


def classify_commit(api: GitHubApi, sha: str) -> Report:
    """
    Classify every red check on one commit.

    A commit with NO check runs is reported as indeterminate, not as clean.
    "I found nothing to classify" and "I classified everything and it is green"
    are different answers, and only one of them may exit 0.
    """
    checks, error = list_check_runs(api, sha)
    if error:
        return Report(sha, 0, [], True, error)
    if not checks:
        return Report(
            sha,
            0,
            [],
            True,
            f"{sha} carries no check runs at all — nothing was classified, so "
            "this is NOT a clean bill of health (see #12823 for parked runs)",
        )
    reds = [classify_check_run(api, check) for check in checks if is_red(check)]
    if not reds:
        return Report(sha, len(checks), [], False, f"{len(checks)} checks, none red")
    return Report(sha, len(checks), reds, False, f"{len(reds)} of {len(checks)} checks are red")


def _emit(text: str, *, err: bool = False) -> None:
    """
    The one place this module writes to a stream.

    A CI script's output IS its product — there is no logger a workflow step
    reads — so stdout is correct here. Funnelling it through a single call
    keeps that a deliberate, once-stated exception to the no-print rule
    (#1082) rather than eight scattered ones.
    """
    print(text, file=sys.stderr if err else sys.stdout)  # noqa: print


def render(report: Report) -> None:
    _emit(f"commit {report.sha}: {report.message}")
    for red in report.reds:
        steps = (
            f"{red.executed_steps}/{red.total_steps} steps executed"
            if red.executed_steps is not None
            else "steps unavailable"
        )
        verdict = "REAL FAILURE" if red.real_failure else "not a test result"
        requeue = "re-queueable" if red.requeueable else "DO NOT RE-QUEUE"
        _emit(f"  [{red.cause}] {red.check_name} ({red.conclusion}, {steps})")
        _emit(f"      {red.detail}")
        _emit(f"      verdict: {verdict} · {requeue} · blocks merge: yes")
        if red.url:
            _emit(f"      {red.url}")
    if report.indeterminate:
        _emit("INDETERMINATE — this run vouches for nothing.", err=True)


def _payload(report: Report) -> Dict[str, Any]:
    return {
        "sha": report.sha,
        "checks_seen": report.checks_seen,
        "indeterminate": report.indeterminate,
        "message": report.message,
        "reds": [red.as_dict() for red in report.reds],
    }


def resolve_exit_code(report: Report, exit_zero: bool) -> int:
    """
    2 for indeterminate, 1 for any red, 0 only for "checks seen, none red".

    ``--exit-zero`` suppresses only the *red* exit. It cannot suppress 2, so a
    report-only caller still cannot mistake "nothing classified" for "clean".
    """
    if report.indeterminate:
        return 2
    if report.reds and not exit_zero:
        return 1
    return 0


def build_api() -> GitHubApi:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token:
        raise WatchdogConfigError("GITHUB_TOKEN is required")
    if "/" not in repository:
        raise WatchdogConfigError("GITHUB_REPOSITORY must be 'owner/repo'")
    api_root = os.environ.get("GITHUB_API_URL", DEFAULT_API_ROOT).strip() or DEFAULT_API_ROOT
    return GitHubApi(token, repository, api_root, request_timeout())


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Classify why a commit's checks are red.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pr", type=int, help="pull request number; its head sha is used")
    target.add_argument("--sha", help="commit sha to classify")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument(
        "--exit-zero",
        action="store_true",
        help="report-only: do not exit 1 on red (exit 2 on indeterminate still stands)",
    )
    args = parser.parse_args(argv)
    try:
        api = build_api()
        sha = args.sha.strip() if args.sha else head_sha_for_pr(api, args.pr)
        report = classify_commit(api, sha)
    except WatchdogConfigError as exc:
        _emit(f"ci-red-cause: {exc}", err=True)
        return 2
    if args.json:
        _emit(json.dumps(_payload(report), indent=2))
    else:
        render(report)
    return resolve_exit_code(report, args.exit_zero)


if __name__ == "__main__":
    sys.exit(main())
