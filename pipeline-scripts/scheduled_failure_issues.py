# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The issue side of the scheduled-failure sweep: markers, text, structure and matching (#21592).

Split from ``scheduled_failure_report.py`` (which keeps discovery, the verdict and the sweep) at its
size ceiling. No ``__main__``: it is a library, not a launched script. Pure functions only; the API
calls stay in the sweep's client.

Three kinds of open issue are told apart, all from ONE listing of the open issues, all by hidden markers
and never by what the text says:

* the **umbrella**: its FIRST body line is ``<!-- scheduled-failure-report:umbrella -->``;
* the sweep's **own** issue for a workflow: its FIRST body line is ``<!-- scheduled-failure-report:<file> -->``;
  it may be closed on recovery;
* a **person's** issue, opted in by a line ``<!-- scheduled-failure-tracks:<file> -->`` anywhere in its
  body: the sweep comments there instead of opening its own, and never closes it. Merely naming the file
  does not opt in. With several issues tracking one file, the lowest number wins and the rest are logged.

The hidden run markers (``scheduled-failure-run`` for a failing run, ``scheduled-failure-recovered`` for
the note that it passes again) make every comment idempotent per run, and say whether the last word on an
issue was a failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from autobot_shared.env_utils import env_int_clamped, env_str
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

Json = Dict[str, Any]

ISSUE_LABELS = ("bug", "ci")
#: The structure the 2-hourly issue-structure sweep requires (#19522): a goal milestone ``M<n> - ...``, a
#: ``phase:M<n>.<k>`` label with the same ``n``, and a native parent. Env-backed so a re-planned milestone is
#: a configuration change.
PHASE_LABEL = env_str("SCHEDULED_FAILURE_PHASE_LABEL", "phase:M5.3")
MILESTONE_TITLE = env_str(
    "SCHEDULED_FAILURE_MILESTONE", "M5 - Engineering platform: CI/CD security, debugging and dependency tooling"
)
#: A scheduled workflow that GitHub has known for more than this many days and that has no completed scheduled
#: run is treated as failing.
NEVER_RUN_DAYS = env_int_clamped("SCHEDULED_FAILURE_NEVER_RUN_DAYS", 7, min_v=1)

UMBRELLA_KEY = "umbrella"
NEVER_KEY = "never"
NOT_DETERMINED = "not determined"

REPORT_MARKER = "<!-- scheduled-failure-report:{file} -->"
TRACKS_MARKER = "<!-- scheduled-failure-tracks:{file} -->"
RUN_MARKER = "<!-- scheduled-failure-run:{key} -->"
RECOVERED_MARKER = "<!-- scheduled-failure-recovered:{key} -->"
_REPORT_MARKER_RE = re.compile(r"<!-- scheduled-failure-report:(\S+) -->")
_TRACKS_MARKER_RE = re.compile(r"<!-- scheduled-failure-tracks:(\S+) -->")
_EVENT_RE = re.compile(r"<!-- scheduled-failure-(run|recovered):(\w+) -->")


@dataclass(frozen=True)
class ScheduledWorkflowFile:
    file: str
    name: str


@dataclass(frozen=True)
class Failure:
    job: str = NOT_DETERMINED
    step: str = NOT_DETERMINED


# ---- pure: text -------------------------------------------------------------------------


def run_key(run: Optional[Json]) -> str:
    """The idempotency key of a report: the run id, or ``never`` when there is no run at all."""
    return str(run["id"]) if run else NEVER_KEY


def run_date(run: Json) -> str:
    return (run.get("run_started_at") or run.get("created_at") or "unknown")[:10]


def _facts(wf: ScheduledWorkflowFile, run: Optional[Json], failure: Failure, age_days: Optional[int]) -> str:
    rows = [f"| Workflow | {wf.name} (`.github/workflows/{wf.file}`) |"]
    if run is None:
        age = "unknown" if age_days is None else f"{age_days} days ago"
        rows += ["| Scheduled runs | none has completed |", f"| Workflow registered | {age} |"]
    else:
        rows += [
            f"| Run | {run.get('html_url')} |",
            f"| Conclusion | {run.get('conclusion')} |",
            f"| Date (UTC) | {run_date(run)} |",
            f"| First failing job | {failure.job} |",
            f"| First failing step | {failure.step} |",
        ]
    return "\n".join(["| | |", "| --- | --- |", *rows])


def issue_title(wf: ScheduledWorkflowFile) -> str:
    return f"Scheduled workflow failing: {wf.name} ({wf.file})"


def issue_body(wf: ScheduledWorkflowFile, run: Optional[Json], failure: Failure, age_days: Optional[int] = None) -> str:
    lead = (
        "The latest scheduled run of this workflow failed."
        if run
        else "This workflow is scheduled, but no scheduled run of it has ever completed."
    )
    return (
        f"{REPORT_MARKER.format(file=wf.file)}\n{RUN_MARKER.format(key=run_key(run))}\n{lead}\n\n"
        f"{_facts(wf, run, failure, age_days)}\n\n"
        "The daily scheduled-failure sweep opened this issue. A later failing run adds a comment here; "
        "the sweep closes the issue once the workflow's latest scheduled run passes."
    )


def failure_comment(
    wf: ScheduledWorkflowFile,
    run: Optional[Json],
    failure: Failure,
    age_days: Optional[int] = None,
    human: bool = False,
) -> str:
    lead = "The scheduled workflow failed again." if run else "Still no completed scheduled run of this workflow."
    if human:
        lead += f" Reported here because this issue tracks `{wf.file}`."
    return f"{RUN_MARKER.format(key=run_key(run))}\n{lead}\n\n{_facts(wf, run, failure, age_days)}"


def passing_comment(wf: ScheduledWorkflowFile, run: Json, human: bool = False) -> str:
    seen = f"({run.get('html_url')}, {run_date(run)}, conclusion {run.get('conclusion')})"
    if human:
        return (
            f"{RECOVERED_MARKER.format(key=run_key(run))}\n"
            f"The latest scheduled run of {wf.name} passes {seen}. This issue is left open for a person."
        )
    return f"The latest scheduled run of {wf.name} passed {seen}. Closing; a new failure opens a new issue."


# ---- pure: markers and targets ----------------------------------------------------------


def marker_file(body: Optional[str]) -> Optional[str]:
    """The workflow file (or ``umbrella``) named by the FIRST body line's report marker, else None."""
    first = (body or "").lstrip("﻿").split("\n", 1)[0].strip()
    match = _REPORT_MARKER_RE.fullmatch(first)
    return match.group(1) if match else None


def tracked_workflow_files(body: Optional[str]) -> set:
    """The workflow files a person's issue opted in to, by ``scheduled-failure-tracks`` lines anywhere in its body."""
    return set(_TRACKS_MARKER_RE.findall(body or ""))


def has_parent(issue: Json) -> bool:
    """True when the listing item already has a native parent (any parent: one is never replaced)."""
    return bool(issue.get("parent_issue_url"))


def marker_events(issue: Json, comments: Iterable[Json]) -> List[Tuple[str, str]]:
    """``(kind, key)`` for every run/recovered marker in the body, then the comments in order."""
    texts = [issue.get("body") or ""] + [c.get("body") or "" for c in comments]
    return [(kind, key) for text in texts for kind, key in _EVENT_RE.findall(text)]


def reported_keys(events: Sequence[Tuple[str, str]]) -> set:
    return {key for kind, key in events if kind == "run"}


def last_word_is_failure(events: Sequence[Tuple[str, str]]) -> bool:
    return bool(events) and events[-1][0] == "run"


@dataclass(frozen=True)
class Targets:
    own: Dict[str, Json]
    human: Dict[str, Json]
    umbrella: Optional[Json]


def _lowest(found: Sequence[Json], what: str) -> Optional[Json]:
    if not found:
        return None
    ranked = sorted(found, key=lambda item: item["number"])
    if len(ranked) > 1:
        logger.warning("%s named by #%s; using #%s", what, [i["number"] for i in ranked[1:]], ranked[0]["number"])
    return ranked[0]


def build_targets(items: Iterable[Json], files: Iterable[str]) -> Targets:
    """Sort one listing of open issues into the umbrella, the sweep's own issues and the opted-in person's ones."""
    listed = list(items)
    marked = {item["number"]: marker_file(item.get("body")) for item in listed}
    umbrella = _lowest([i for i in listed if marked[i["number"]] == UMBRELLA_KEY], "the umbrella")
    own: Dict[str, Json] = {}
    for item in sorted(listed, key=lambda i: i["number"]):
        key = marked[item["number"]]
        if key and key != UMBRELLA_KEY and key not in own:
            own[key] = item
    unmarked = [(i, tracked_workflow_files(i.get("body"))) for i in listed if marked[i["number"]] is None]
    human: Dict[str, Json] = {}
    for file in files:
        if file in own:
            continue
        chosen = _lowest([i for i, tracked in unmarked if file in tracked], f"{file} is tracked by")
        if chosen is not None:
            human[file] = chosen
    return Targets(own, human, umbrella)
