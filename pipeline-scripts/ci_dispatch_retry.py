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
  * the per-sweep budget is small and fixed, not per-pull-request
  * a run that has already been re-dispatched keeps its red

That last one matters most: a SECOND non-dispatch is a capacity or configuration
signal, and it must stand where a human sees it rather than be retried away.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

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
    remaining = api.rate_limit_remaining()
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


def redispatch(api: Any, candidates: Sequence[Any], limits: Dict[str, int],
               dry_run: bool) -> Tuple[int, List[str]]:
    """Re-dispatch up to the sweep budget. Returns ``(count, lines)``."""
    lines: List[str] = []
    done = 0
    for red in candidates:
        if done >= limits["max_reruns"]:
            lines.append(f"  budget spent ({limits['max_reruns']}) — {red.check_name} left red")
            break
        run_id, attempt = job_run_context(api, red.job_id)
        if run_id is None:
            lines.append(f"  {red.check_name}: could not resolve its run — left red")
            continue
        if attempt >= limits["max_attempts"]:
            lines.append(f"  {red.check_name}: attempt {attempt} — a repeat is not transient, left red")
            continue
        if dry_run:
            lines.append(f"  would re-dispatch {red.check_name} (run {run_id}, attempt {attempt}, {red.cause})")
            done += 1
            continue
        status, message = api.rerun_run(run_id)
        if 200 <= status < 300:
            lines.append(f"  re-dispatched {red.check_name} (run {run_id}, was {red.cause})")
            done += 1
        else:
            lines.append(f"  {red.check_name}: re-run refused ({status}) {message}".rstrip())
    return done, lines


def run(sha: str, dry_run: bool) -> int:
    api = build_api()
    limits = {
        "ceiling": _env_int("CI_RETRY_CAPACITY_CEILING", DEFAULT_CAPACITY_CEILING),
        "max_reruns": _env_int("CI_RETRY_MAX_RERUNS", DEFAULT_MAX_RERUNS),
        "max_attempts": _env_int("CI_RETRY_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS),
        "reserve": _env_int("CI_RETRY_RATE_RESERVE", DEFAULT_RATE_RESERVE),
    }
    _emit(f"ci-dispatch-retry: {sha}")

    blocked = budget_blocked(api, limits["reserve"]) or capacity_blocked(api, limits["ceiling"])
    if blocked:
        _emit(f"  holding off — {blocked}")
        _emit("  nothing re-dispatched; the reds stand and stay visible.")
        return 0

    report = classify_commit(api, sha)
    candidates = retry_candidates(report)
    if not candidates:
        _emit(f"  {len(report.reds)} red check(s), none infrastructure-caused — nothing to re-dispatch.")
        return 0

    done, lines = redispatch(api, candidates, limits, dry_run)
    for line in lines:
        _emit(line)
    _emit(f"  {done} of {len(candidates)} infrastructure-caused red(s) re-dispatched.")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Re-dispatch infrastructure-caused red checks (#15139)")
    parser.add_argument("--sha", required=True, help="head commit to sweep")
    parser.add_argument("--dry-run", action="store_true", help="classify and report, re-dispatch nothing")
    args = parser.parse_args(argv)
    try:
        return run(args.sha, args.dry_run)
    except Exception as exc:  # noqa: BLE001 - a watchdog must not take the sweep down
        _emit(f"ci-dispatch-retry: could not complete — {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
