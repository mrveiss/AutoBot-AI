# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Re-dispatch red checks whose cause was infrastructure, not the diff (#15139).

A run that never obtained a runner is reported to the pull request as
``failure`` -- the same signal a real test failure produces. `red CI never
merges` then fires on an infrastructure condition and whoever reads it goes
hunting for a defect that is not there.

GitHub will not let a concluded run un-conclude, so "report it as pending" is
not an option. Re-dispatching is: a re-run turns an infrastructure conclusion
back into a pending check, and red goes back to meaning "something executed and
failed".

WHY THIS SWEEPS OPEN PULL REQUESTS RATHER THAN ONE SHA. The workflow step that
drives this tool fires on ``schedule``/``push``/``workflow_dispatch`` -- never
on ``pull_request``, where a PR's own unreviewed copy of this file would be
executing with `actions: write` -- and none of those events carries a pull
request in their payload. A single ``--sha`` therefore had nothing to resolve
to but the base branch tip, which is never the head a real PR is red on. The
sibling ``ci_dispatch_watchdog.py --check dispatch`` sweep already solves this
the same way: list every open pull request against the base branch and act on
each head. This module follows that pattern instead of inventing a second one.

WHY THIS IS A SEPARATE MODULE FROM ci_red_cause.py. That module states, and
depends on, never writing anything back -- which is why the workflow can run it
BEFORE the self-modification guard, where a pull request's own copy of the code
is executing. Adding a write path there would spend the job's `actions: write`
permission from unreviewed code. The classification is imported from it; the
writing lives here, behind the guard.

ADMISSION CONTROL IS THE POINT. Re-running eagerly re-queues into whatever was
already too full to dispatch -- the same condition that produced the failure,
with a retry loop attached. Every gate below refuses to spend rather than
guessing:

  * unknown rate-limit budget is treated as no budget, never as headroom
  * an in-progress count at the ceiling stops the sweep entirely
  * the re-run budget is small, fixed, and spent ACROSS THE WHOLE SWEEP -- not
    reset per pull request, which is exactly how sweeping N PRs instead of one
    sha would turn a single outage into a rate-limit exhaustion
  * a run that has already been re-dispatched keeps its red

That last one matters most: a SECOND non-dispatch is a capacity or configuration
signal, and it must stand where a human sees it rather than be retried away.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci_dispatch_watchdog import (  # noqa: E402
    DEFAULT_BASE_BRANCH,
    collect_heads,
)
from ci_red_cause import (  # noqa: E402
    INFRASTRUCTURE_CAUSES,
    build_api,
    classify_commit,
)

# Free-tier public repositories get roughly 20 concurrent jobs. Stopping a
# little under it leaves room for the runs already on their way in, so a retry
# never takes the last slot from a first attempt.
DEFAULT_CAPACITY_CEILING = 16

# Per sweep, not per pull request. Unbounded fan-out over open PRs is how a
# watchdog turns one outage into a rate-limit exhaustion.
DEFAULT_MAX_RERUNS = 3

# attempt 1 was the failure; attempt 2 is this retry. A third means the
# condition is not transient.
DEFAULT_MAX_ATTEMPTS = 2

# Enough headroom left for the rest of the sweep to finish and publish.
DEFAULT_RATE_RESERVE = 200


# These two live here rather than on GitHubApi in ci_dispatch_watchdog.py: that
# module is a grandfathered file under the #14236 size ratchet, and the
# exemption freezes the size it was granted for rather than licensing more.
# `api.request` is the shared client's public entry point, so nothing is forked
# by calling it from here -- only the two calls unique to this tool live here.


def rerun_run(api: Any, run_id: int) -> Tuple[int, str]:
    """Re-dispatch a run.

    ``rerun-failed-jobs`` rather than ``rerun``: a run that never dispatched has
    exactly one failed job and nothing worth repeating, and on a partly
    successful run this avoids paying again for the jobs that passed. GitHub
    rejects the request on state grounds if the run is not re-runnable, which is
    returned rather than raised.
    """
    status, body = api.request(
        "POST", f"/repos/{api.repository}/actions/runs/{run_id}/rerun-failed-jobs"
    )
    message = str(body.get("message", "")) if isinstance(body, dict) else ""
    return status, message


def rate_limit_remaining(api: Any) -> int:
    """Remaining core REST budget, or -1 when it cannot be read.

    Inside Actions the GITHUB_TOKEN budget is 1,000/hour per repository, not the
    5,000 a PAT gets, and the sweep this rides on already spends against it. -1
    means "unknown", which callers must treat as "do not spend" rather than as
    headroom.
    """
    status, body = api.request("GET", "/rate_limit")
    if status != 200 or not isinstance(body, dict):
        return -1
    core = (body.get("resources") or {}).get("core") or {}
    remaining = core.get("remaining")
    return int(remaining) if isinstance(remaining, int) else -1


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def _emit(text: str) -> None:
    print(text)  # noqa: print - this tool's output IS its report


def capacity_blocked(api: Any, ceiling: int) -> Optional[str]:
    """Refuse the sweep when the queue cannot absorb a re-dispatch."""
    in_progress = api.recent_runs(per_page=100, run_status="in_progress")
    count = len(in_progress)
    if count >= ceiling:
        return f"{count} runs in progress, ceiling {ceiling} — a re-run would only lengthen the queue"
    return None


def budget_blocked(api: Any, reserve: int) -> Optional[str]:
    """Refuse the sweep when the REST budget is low or unreadable."""
    remaining = rate_limit_remaining(api)
    if remaining < 0:
        return "rate-limit budget unreadable — treating as spent, not as headroom"
    if remaining < reserve:
        return f"{remaining} REST calls left, reserve {reserve}"
    return None


def job_run_context(api: Any, job_id: int) -> Tuple[Optional[int], int]:
    """Return ``(run_id, run_attempt)`` for a job, or ``(None, 0)``."""
    status, body = api.request("GET", f"/repos/{api.repository}/actions/jobs/{job_id}")
    if status != 200 or not isinstance(body, dict):
        return None, 0
    run_id = body.get("run_id")
    attempt = body.get("run_attempt")
    return (int(run_id) if isinstance(run_id, int) else None,
            int(attempt) if isinstance(attempt, int) else 0)


def retry_candidates(report: Any) -> List[Any]:
    """Infrastructure-caused reds carrying a job id, in report order."""
    return [red for red in report.reds
            if red.cause in INFRASTRUCTURE_CAUSES and red.job_id]


class PrCandidate(NamedTuple):
    """One infrastructure-caused red, tagged with the pull request it came from."""

    pr_number: int
    red: Any


def collect_candidates(api: Any, heads: Sequence[Any]) -> List[PrCandidate]:
    """Classify every open PR head and flatten to infrastructure-caused reds.

    Head order in, head order out: the per-sweep budget in :func:`redispatch`
    is spent walking this list, so the order here is the order PRs get a
    re-dispatch before the budget runs out.
    """
    candidates: List[PrCandidate] = []
    for head in heads:
        report = classify_commit(api, head.sha)
        candidates.extend(PrCandidate(head.number, red) for red in retry_candidates(report))
    return candidates


def redispatch(api: Any, candidates: Sequence[PrCandidate], limits: Dict[str, int],
               dry_run: bool) -> Tuple[int, List[str]]:
    """Re-dispatch up to the sweep budget, spent across ALL candidates -- not
    reset per pull request. Returns ``(count, lines)``."""
    lines: List[str] = []
    done = 0
    for item in candidates:
        pr, red = item.pr_number, item.red
        if done >= limits["max_reruns"]:
            lines.append(f"  budget spent ({limits['max_reruns']}) — PR #{pr} {red.check_name} left red")
            break
        run_id, attempt = job_run_context(api, red.job_id)
        if run_id is None:
            lines.append(f"  PR #{pr} {red.check_name}: could not resolve its run — left red")
            continue
        if attempt >= limits["max_attempts"]:
            lines.append(f"  PR #{pr} {red.check_name}: attempt {attempt} — a repeat is not transient, left red")
            continue
        if dry_run:
            lines.append(f"  would re-dispatch PR #{pr} {red.check_name} (run {run_id}, attempt {attempt}, {red.cause})")
            done += 1
            continue
        status, message = rerun_run(api, run_id)
        if 200 <= status < 300:
            lines.append(f"  re-dispatched PR #{pr} {red.check_name} (run {run_id}, was {red.cause})")
            done += 1
        else:
            lines.append(f"  PR #{pr} {red.check_name}: re-run refused ({status}) {message}".rstrip())
    return done, lines


def _sweep_limits() -> Dict[str, int]:
    return {
        "ceiling": _env_int("CI_RETRY_CAPACITY_CEILING", DEFAULT_CAPACITY_CEILING),
        "max_reruns": _env_int("CI_RETRY_MAX_RERUNS", DEFAULT_MAX_RERUNS),
        "max_attempts": _env_int("CI_RETRY_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS),
        "reserve": _env_int("CI_RETRY_RATE_RESERVE", DEFAULT_RATE_RESERVE),
    }


def run(dry_run: bool, base_branch: str = DEFAULT_BASE_BRANCH) -> int:
    api = build_api()
    limits = _sweep_limits()
    _emit(f"ci-dispatch-retry: sweeping open PRs targeting {base_branch}")
    blocked = budget_blocked(api, limits["reserve"]) or capacity_blocked(api, limits["ceiling"])
    if blocked:
        _emit(f"  holding off — {blocked}")
        _emit("  nothing re-dispatched; the reds stand and stay visible.")
        return 0
    heads = collect_heads(api.open_pull_requests(base_branch), api.repository)
    if not heads:
        _emit(f"  no open PRs targeting {base_branch} — nothing to sweep.")
        return 0
    candidates = collect_candidates(api, heads)
    if not candidates:
        _emit(f"  {len(heads)} open PR(s) swept, none carrying infrastructure-caused reds.")
        return 0
    done, lines = redispatch(api, candidates, limits, dry_run)
    for line in lines:
        _emit(line)
    _emit(f"  {done} of {len(candidates)} infrastructure-caused red(s) re-dispatched across {len(heads)} PR(s).")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Re-dispatch infrastructure-caused red checks across open PRs (#15139)")
    parser.add_argument("--base", default=None,
                         help="PR base branch to sweep (default: $WATCHDOG_BASE_BRANCH or Dev_new_gui)")
    parser.add_argument("--dry-run", action="store_true", help="classify and report, re-dispatch nothing")
    args = parser.parse_args(argv)
    base_branch = args.base or os.environ.get("WATCHDOG_BASE_BRANCH", "").strip() or DEFAULT_BASE_BRANCH
    try:
        return run(args.dry_run, base_branch)
    except Exception as exc:  # noqa: BLE001 - a watchdog must not take the sweep down
        _emit(f"ci-dispatch-retry: could not complete — {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
