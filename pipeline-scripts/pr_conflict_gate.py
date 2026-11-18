# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fail a conflicting PR's CI at once (#19769): cancel its runs, set ``no-merge-conflicts``.

Event ``pull_request``: checks the one PR (``PR_NUMBER``). Event ``push`` to main:
checks every open PR into main, ``train-*`` branches included. Decisions are in
``pr_conflict_gate_core.py``; this file is the GitHub REST layer.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pr_conflict_gate_core as core  # noqa: E402
from github_api import GitHubApi, WatchdogError, build_api  # noqa: E402

from autobot_shared.env_utils import env_float_clamped, env_int_clamped  # noqa: E402
from autobot_shared.logging_manager import get_logger  # noqa: E402

logger = get_logger(__name__)

#: Bounded backoff while GitHub reports mergeable=null or a test merge older than the base tip.
#: The default waits 255s in all, across the whole sweep.
UNKNOWN_MAX_ATTEMPTS = env_int_clamped("PR_CONFLICT_GATE_MAX_ATTEMPTS", 8, 1, 10)
UNKNOWN_BACKOFF_SECONDS = env_float_clamped("PR_CONFLICT_GATE_BACKOFF_SECONDS", 5.0, 0.0, 60.0)
UNKNOWN_BACKOFF_FACTOR = 2.0
UNKNOWN_BACKOFF_CAP_SECONDS = 60.0
PAGE_SIZE = 100
MAX_PAGES = 20


class GateError(RuntimeError):
    """A REST call failed in a way that means the gate could not do its job."""


def _get_pull(api: GitHubApi, number: int) -> Dict[str, Any]:
    status, body = api.request("GET", f"/repos/{api.repository}/pulls/{number}")
    if status != 200 or not isinstance(body, dict):
        raise GateError(f"cannot read PR #{number} (HTTP {status}): {body}")
    return body


def _test_merge_parents(api: GitHubApi, pull: Dict[str, Any]) -> List[str]:
    """Parents of GitHub's test merge; empty when it has none to show."""
    sha = pull.get("merge_commit_sha")
    if not sha:
        return []
    status, body = api.request("GET", f"/repos/{api.repository}/commits/{sha}")
    if status in (404, 422):
        return []
    if status != 200 or not isinstance(body, dict):
        raise GateError(f"cannot read test merge {sha[:12]} (HTTP {status}): {body}")
    return [parent["sha"] for parent in body.get("parents", [])]


def _base_tip(api: GitHubApi, branch: str, tips: Dict[str, str]) -> str:
    """The branch's live tip, read once a pass: a PR's ``base.sha`` lags it (#20573)."""
    if branch not in tips:
        status, body = api.request("GET", f"/repos/{api.repository}/git/ref/heads/{branch}")
        if status != 200 or not isinstance(body, dict):
            raise GateError(f"cannot read {branch} (HTTP {status}): {body}")
        tips[branch] = body["object"]["sha"]
    return tips[branch]


def read_pull(api: GitHubApi, number: int, tips: Dict[str, str]) -> tuple[str, Dict[str, Any]]:
    """Classify one PR; a ``mergeable: true`` read off an older test merge is UNKNOWN (#20573)."""
    pull = _get_pull(api, number)
    kind = core.classify(pull)
    if kind == core.MERGEABLE:
        tip = _base_tip(api, pull["base"]["ref"], tips)
        if not core.is_current(_test_merge_parents(api, pull), tip, pull["head"]["sha"]):
            kind = core.UNKNOWN
    return kind, pull


def cancel_runs(api: GitHubApi, sha: str, own_run_id: Optional[int]) -> List[int]:
    """Cancel the head's queued/in-progress runs except this workflow's own."""
    cancelled: List[int] = []
    for run_id in core.runs_to_cancel(api.runs_for_sha(sha), own_run_id):
        status, body = api.request("POST", f"/repos/{api.repository}/actions/runs/{run_id}/cancel")
        if status in (202, 409):  # 409: already finished or cancelling
            cancelled.append(run_id)
        else:
            logger.warning("cannot cancel run %s on %s (HTTP %s): %s", run_id, sha[:12], status, body)
    return cancelled


def check_pull(
    api: GitHubApi, number: int, own_run_id: Optional[int], target_url: str, tips: Dict[str, str], final: bool
) -> Optional[core.Verdict]:
    """One read of one PR. UNKNOWN publishes only on the final pass, so a settling PR keeps its status."""
    kind, pull = read_pull(api, number, tips)
    # A fork head is outside this repository: the status API cannot reach it and a fork
    # token is read-only. No status at all; whether a fork PR needs the required context
    # is a branch-protection decision for the maintainer (#19769).
    if not core.is_checkable(pull, api.repository):
        logger.info("PR #%s is from a fork; the status API cannot reach its head, skipped", number)
        return None
    sha = pull["head"]["sha"]
    verdict = core.decide(kind)
    if kind == core.UNKNOWN and not final:
        return verdict
    # The status first: it must land even when listing or cancelling runs fails.
    status = api.set_status(sha, verdict.state, core.STATUS_CONTEXT, verdict.description, target_url)
    if status != 201:
        raise GateError(f"cannot set {core.STATUS_CONTEXT} on PR #{number} (HTTP {status})")
    cancelled = cancel_runs(api, sha, own_run_id) if verdict.cancel_runs else []
    logger.info("PR #%s %s: status %s, cancelled %s", number, kind, verdict.state, cancelled)
    return verdict


def settle_pulls(
    api: GitHubApi,
    numbers: Sequence[int],
    own_run_id: Optional[int],
    target_url: str,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Dict[int, core.Verdict], int]:
    """Read every PR, then re-read only the unsettled: one backoff covers them all, not one each."""
    verdicts: Dict[int, core.Verdict] = {}
    failures = 0
    waiting = list(numbers)
    delay = UNKNOWN_BACKOFF_SECONDS
    for attempt in range(UNKNOWN_MAX_ATTEMPTS):
        if attempt:
            sleep(delay)
            delay = min(delay * UNKNOWN_BACKOFF_FACTOR, UNKNOWN_BACKOFF_CAP_SECONDS)
        final, tips, unsettled = attempt == UNKNOWN_MAX_ATTEMPTS - 1, {}, []
        for number in waiting:
            try:
                verdict = check_pull(api, number, own_run_id, target_url, tips, final)
            except (GateError, WatchdogError) as exc:
                logger.error("PR #%s: %s", number, exc)
                failures += 1
                continue
            if verdict is not None:
                verdicts[number] = verdict
                if verdict.kind == core.UNKNOWN and not final:
                    unsettled.append(number)
        waiting = unsettled
        if not waiting:
            break
    return verdicts, failures


def open_pull_numbers(api: GitHubApi, base: str) -> List[int]:
    numbers: List[int] = []
    for page in range(1, MAX_PAGES + 1):
        path = f"/repos/{api.repository}/pulls?state=open&base={base}&per_page={PAGE_SIZE}&page={page}"
        status, body = api.request("GET", path)
        if status != 200 or not isinstance(body, list):
            raise GateError(f"cannot list open PRs (HTTP {status}): {body}")
        numbers += [p["number"] for p in body if core.is_checkable(p, api.repository)]
        if len(body) < PAGE_SIZE:
            return numbers
    raise GateError("more open PRs than the page bound")


def run(api: GitHubApi, event: str, pr_number: str, base: str, own_run_id: Optional[int], target_url: str) -> int:
    if event == "pull_request":
        numbers = [int(pr_number)]
    else:
        numbers = open_pull_numbers(api, base)
    verdicts, failures = settle_pulls(api, numbers, own_run_id, target_url)
    unknown = sum(verdict.kind == core.UNKNOWN for verdict in verdicts.values())
    if unknown:
        logger.warning("%s PR(s) still UNKNOWN after %s attempts", unknown, UNKNOWN_MAX_ATTEMPTS)
    return 1 if failures else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        api = build_api()
    except WatchdogError as exc:
        logger.error("cannot build the GitHub client: %s", exc)
        return 1
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    target_url = f"{server}/{api.repository}/actions/runs/{run_id}" if run_id else ""
    return run(
        api,
        os.environ.get("GITHUB_EVENT_NAME", ""),
        os.environ.get("PR_NUMBER", ""),
        os.environ.get("BASE_BRANCH", "main"),
        int(run_id) if run_id.isdigit() else None,
        target_url,
    )


if __name__ == "__main__":
    sys.exit(main())
