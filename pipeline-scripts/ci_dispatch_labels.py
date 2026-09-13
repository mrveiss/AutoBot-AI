# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which runner pool a starved workflow run is waiting for (#16309).

A run left unstarted past the stall threshold does not say, on its own, which
pool it waits for. Reading every such run as waiting on the self-hosted pool
turned GitHub-hosted concurrency saturation into a reported self-hosted outage:
approved PRs went red with "self-hosted run(s) queued ... no runner available"
while their queued jobs carried ``ubuntu-latest`` and the self-hosted runner sat
idle.

A queued job's ``labels`` (``GET /actions/runs/{id}/jobs``) name its pool, so a
starved run is placed by them:

* ``SELF_HOSTED`` — a job ``queued`` on a ``self-hosted`` label. The only
  placement that can be an outage, and only while no self-hosted job is served.
* ``HOSTED`` — jobs ``queued`` on GitHub-hosted labels only: concurrency
  saturation, reported with its counts, never as an outage.
* ``WAITING`` — no job queued and one ``pending``: waiting its turn in a
  concurrency group (#16320's ``queue: max`` shards), which is not starvation.
* No readable job — #13045's ``jobs: []``, a failed listing, or a run past the
  lookup budget — is placed by its workflow's declared ``runs-on`` (#14364):
  ``SELF_HOSTED`` when the declaration names the pool or cannot be read,
  ``UNATTRIBUTED`` otherwise.

Job listings are budgeted per sweep (``WATCHDOG_MAX_QUEUED_JOB_LOOKUPS``): a
saturated queue is exactly when hundreds of runs starve, and the workflow
token's hourly request budget is shared with every other job.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple, Type

# A job carrying this label runs on the self-hosted pool.
SELF_HOSTED_LABEL = "self-hosted"

# Starved runs whose jobs one sweep may list; WATCHDOG_MAX_QUEUED_JOB_LOOKUPS overrides it.
DEFAULT_QUEUED_JOB_LOOKUPS = 40

# Where a starved run is waiting (see the module docstring).
SELF_HOSTED = "self_hosted"
HOSTED = "hosted"
WAITING = "waiting"
UNATTRIBUTED = "unattributed"

# How many run names one commit-status description carries.
NAMED_RUNS = 3

JobsByRun = Dict[Any, List[Dict[str, Any]]]


def job_is_self_hosted(job: Dict[str, Any]) -> bool:
    """True when this job was dispatched to the self-hosted pool."""
    labels = [str(label).lower() for label in (job.get("labels") or [])]
    return SELF_HOSTED_LABEL in labels


def run_requires_self_hosted(run: Dict[str, Any], self_hosted_paths: Optional[Set[str]]) -> bool:
    """True when this run's workflow declares at least one self-hosted job.

    Unknown resolves to True from both directions — an unreadable workflow set,
    or a run carrying no `path`. The verdict this gates asserts a specific
    cause, and suppressing a real self-hosted outage is the worse error of the
    two, so an unattributable run stays reportable.
    """
    if self_hosted_paths is None:
        return True
    path = str(run.get("path") or "")
    return not path or path in self_hosted_paths


def hosted_in_progress(jobs: Sequence[Dict[str, Any]]) -> int:
    """GitHub-hosted jobs executing in one run: the ``M running`` of a saturation finding."""
    return sum(1 for job in jobs if job.get("status") == "in_progress" and not job_is_self_hosted(job))


def _queued_on_labels(jobs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Queued jobs that carry labels; a queued job with none names no pool."""
    return [job for job in jobs if job.get("status") == "queued" and job.get("labels")]


def place_run(
    run: Dict[str, Any],
    jobs: Optional[Sequence[Dict[str, Any]]],
    self_hosted_paths: Optional[Set[str]],
) -> str:
    """The pool one starved run waits for: its queued jobs' labels, else its workflow's declaration."""
    queued = _queued_on_labels(jobs or ())
    if any(job_is_self_hosted(job) for job in queued):
        return SELF_HOSTED
    if queued:
        return HOSTED
    if any(job.get("status") == "pending" for job in jobs or ()):
        return WAITING
    return SELF_HOSTED if run_requires_self_hosted(run, self_hosted_paths) else UNATTRIBUTED


def place_runs(
    starved: Sequence[Dict[str, Any]],
    jobs_by_run: JobsByRun,
    self_hosted_paths: Optional[Set[str]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Every starved run, grouped under the pool it waits for."""
    placed: Dict[str, List[Dict[str, Any]]] = {SELF_HOSTED: [], HOSTED: [], WAITING: [], UNATTRIBUTED: []}
    for run in starved:
        placed[place_run(run, jobs_by_run.get(run.get("id")), self_hosted_paths)].append(run)
    return placed


def self_hosted_starved(
    starved: Sequence[Dict[str, Any]],
    jobs_by_run: JobsByRun,
    self_hosted_paths: Optional[Set[str]],
) -> List[Dict[str, Any]]:
    """The starved runs waiting on the self-hosted pool: the only ones an outage may name."""
    return place_runs(starved, jobs_by_run, self_hosted_paths)[SELF_HOSTED]


def _names(runs: Sequence[Dict[str, Any]]) -> str:
    return ", ".join(sorted({str(run.get("name", "?")) for run in runs})[:NAMED_RUNS])


def _saturation(
    hosted: Sequence[Dict[str, Any]],
    jobs_by_run: JobsByRun,
    stall_minutes: int,
    hosted_running: Optional[int],
) -> str:
    queued = sum(len(_queued_on_labels(jobs_by_run[run.get("id")])) for run in hosted)
    running = "unknown" if hosted_running is None else hosted_running
    return (
        f"hosted-runner concurrency saturated ({queued} queued, {running} running) "
        f"over {stall_minutes}m: {_names(hosted)}"
    )


def starved_verdict(
    starved: Sequence[Dict[str, Any]],
    jobs_by_run: Optional[JobsByRun],
    self_hosted_paths: Optional[Set[str]],
    stall_minutes: int,
    pool_serving: bool,
    hosted_running: Optional[int] = None,
) -> Optional[Tuple[str, str]]:
    """
    A head's commit-status ``(state, description)`` for its starved runs; None when none is starved.

    Only self-hosted runs with no self-hosted job served are an outage. A hosted
    backlog outranks contention on a serving pool, and both stay ``pending``:
    never green, because the head is demonstrably not verified yet (#13045). A
    run waiting its turn in a concurrency group has dispatched, so it is left out.

    *hosted_running* counts the GitHub-hosted jobs executing across the runs the
    pool inspection listed, so it is a floor once that inspection's budget ran out.
    """
    jobs_by_run = jobs_by_run or {}
    placed = place_runs(starved, jobs_by_run, self_hosted_paths)
    outage = placed[SELF_HOSTED]
    if outage and not pool_serving:
        return "failure", (
            f"{len(outage)} self-hosted run(s) queued over {stall_minutes}m "
            f"with no runner available: {_names(outage)}"
        )
    if placed[HOSTED]:
        return "pending", _saturation(placed[HOSTED], jobs_by_run, stall_minutes, hosted_running)
    busy = outage + placed[UNATTRIBUTED]
    if busy:
        return "pending", f"{len(busy)} run(s) queued over {stall_minutes}m behind a busy queue: {_names(busy)}"
    return None


class QueuedJobReader:
    """Lists the jobs of starved runs, spending at most one budget of listings per sweep."""

    def __init__(
        self,
        api: Any,
        api_error: Type[Exception],
        emit: Callable[[str], None],
        budget: Optional[int] = None,
    ) -> None:
        # `api` is held rather than `api.run_jobs`: a sweep that meets no
        # starved run never needs the listing, so it never asks for one.
        self._api = api
        self._api_error = api_error
        self._emit = emit
        self.remaining = DEFAULT_QUEUED_JOB_LOOKUPS if budget is None else budget
        self._spent_said = False

    def read(self, runs: Sequence[Dict[str, Any]]) -> JobsByRun:
        """Jobs by run id. A run left out is placed by its workflow's declaration."""
        jobs_by_run: JobsByRun = {}
        for run in runs:
            if self.remaining <= 0:
                self._say_spent()
                break
            self.remaining -= 1
            try:
                jobs_by_run[run.get("id")] = self._api.run_jobs(int(run["id"]))
            except self._api_error as exc:
                self._emit(f"  queued-job labels unread, placed by its workflow instead: {exc}")
        return jobs_by_run

    def _say_spent(self) -> None:
        if not self._spent_said:
            self._emit("  queued-job lookup budget spent: further starved runs are placed by their workflow's runs-on")
            self._spent_said = True
