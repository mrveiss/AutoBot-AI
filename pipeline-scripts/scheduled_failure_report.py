#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Daily sweep: one issue per failing scheduled workflow, closed when it passes again (#21592).

Run by `.github/workflows/scheduled-failure-report.yml`. Nothing is listed by hand:

1. **Which workflows.** Every ``.github/workflows/*.yml|*.yaml`` whose ``on`` map carries a
   ``schedule`` with at least one ``cron``. PyYAML (YAML 1.1) parses the bare key ``on`` as the
   boolean ``True``, so both spellings are read. ``on: schedule`` and ``on: [schedule]`` (string
   and list forms) name the event without a cron, GitHub never fires them, so they do not count.
2. **The verdict.** The newest COMPLETED run with ``event=schedule`` whose conclusion decides:
   ``success`` passes; ``failure``, ``timed_out`` and ``startup_failure`` fail. ``cancelled``,
   ``skipped``, ``neutral``, ``stale`` and ``action_required`` say nothing about the workflow
   (a person or a concurrency group stopped it), so they are skipped and the next older run
   decides. Runs exist but none decides: ``inconclusive``, no action. No completed scheduled run
   at all: ``never-run`` -- reported as a WARNING in the output, and when the workflow file was
   added more than ``NEVER_RUN_DAYS`` ago (env ``SCHEDULED_FAILURE_NEVER_RUN_DAYS``, default 7) it is
   ``never-fired`` and handled like a failing workflow. The sweep's own file is therefore only a
   warning for its first week.
3. **The issue.** (Markers, matching and text: ``scheduled_failure_issues.py``.) Found by a hidden marker
   line in the body among the open issues; the title is never matched. Failing and no issue: open one with
   the milestone and labels the issue-structure sweep requires, then attach it to the umbrella issue as a
   native sub-issue. Failing with an issue: a NEW comment per failing run, never twice for the same run.
   Passing with the sweep's own issue: a closing comment, then close.
4. **A person's issue.** An open issue whose body carries the line
   ``<!-- scheduled-failure-tracks:<workflow file name> -->`` is opted in: the sweep comments THERE instead
   of opening its own (idempotent per run) and never closes it. On recovery it adds one "passes again"
   note, and only when its own last word on that issue was a failure. Naming the file is not opting in.

``--dry-run`` reads everything and writes nothing. Stdlib plus PyYAML; HTTP goes through
``github_api.GitHubApi``, the issue client and paginator are ``issue_api`` (#19522), the comment
reader is the shared helper (#12984). The report goes to STDOUT, diagnostics at WARNING or above.
"""

from __future__ import annotations

import argparse
import subprocess  # nosec B404  # one fixed `git log` to date a workflow file
import sys
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, FrozenSet, Iterable, List, Optional, Sequence, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
# CI runs this as a bare ``python3 pipeline-scripts/...``, so the repo root is added the way the
# sibling pipeline scripts do (audit_unwired_trackers.py), then this directory for the shared clients.
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from github_api import WatchdogApiError, WatchdogError, build_api  # noqa: E402
from issue_api import IssueApiError, IssueClient, list_issues  # noqa: E402
from scheduled_failure_issues import (  # noqa: E402
    ISSUE_LABELS,
    MILESTONE_TITLE,
    NEVER_RUN_DAYS,
    NOT_DETERMINED,
    PHASE_LABEL,
    Failure,
    Json,
    ScheduledWorkflow,
    Targets,
    build_targets,
    failure_comment,
    issue_body,
    issue_title,
    last_word_is_failure,
    marker_events,
    passing_comment,
    reported_keys,
    run_key,
)

from autobot_shared.logging_manager import get_logger  # noqa: E402

logger = get_logger(__name__)

WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
RUNS_PER_WORKFLOW = 10
MAX_ISSUE_PAGES = 50
MILESTONE_PAGE_SIZE = 100
GIT_TIMEOUT_SECONDS = 60

FAILING_CONCLUSIONS: FrozenSet[str] = frozenset({"failure", "timed_out", "startup_failure"})
PASSING_CONCLUSIONS: FrozenSet[str] = frozenset({"success"})
STEP_FAILED: FrozenSet[str] = frozenset({"failure", "timed_out"})

STATE_FAILING = "failing"
STATE_PASSING = "passing"
STATE_NEVER_RUN = "never-run"
STATE_NEVER_FIRED = "never-fired"
STATE_INCONCLUSIVE = "inconclusive"

ACTION_OPEN = "open"
ACTION_UPDATE = "update"
ACTION_CLOSE = "close"
ACTION_RECOVER = "recovered-note"
ACTION_NONE = "none"
ACTION_ALREADY = "already-reported"
WRITING_ACTIONS = frozenset({ACTION_OPEN, ACTION_UPDATE, ACTION_CLOSE, ACTION_RECOVER})

NO_JOB_STARTED = "none: the run ended before any job started"
NEVER_RUN_NOTE = "WARNING: scheduled, but no scheduled run has completed"

AgeOf = Optional[Callable[[str], Optional[int]]]


class SweepError(IssueApiError):
    """The API answered with something this sweep cannot act on."""


# ---- pure: which workflows are scheduled ------------------------------------------------


def triggers_of(doc: Any) -> Any:
    """The ``on`` value of a parsed workflow; PyYAML reads the unquoted key ``on`` as ``True``."""
    if not isinstance(doc, dict):
        return None
    return doc[True] if True in doc else doc.get("on")


def declares_schedule(triggers: Any) -> bool:
    """True when the map form carries a ``schedule`` entry with a cron; string and list forms never do."""
    if not isinstance(triggers, dict):
        return False
    entries = triggers.get("schedule")
    if not isinstance(entries, list):
        return False
    return any(isinstance(entry, dict) and entry.get("cron") for entry in entries)


def workflow_files(directory: Path) -> List[Path]:
    return sorted(path for pattern in ("*.yml", "*.yaml") for path in directory.glob(pattern))


def _workflow_name(doc: Json, path: Path) -> str:
    name = doc.get("name")
    return name.strip() if isinstance(name, str) and name.strip() else path.stem


def scan_workflows(directory: Path = WORKFLOW_DIR) -> Tuple[List[ScheduledWorkflow], List[str]]:
    """``(scheduled workflows, problems)``; a file that cannot be read is a problem, never a skip."""
    found: List[ScheduledWorkflow] = []
    problems: List[str] = []
    for path in workflow_files(directory):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
            problems.append(f"{path.name}: cannot be read ({type(exc).__name__})")
            continue
        if declares_schedule(triggers_of(doc)):
            found.append(ScheduledWorkflow(path.name, _workflow_name(doc, path)))
    return found, problems


def scheduled_workflows(directory: Path = WORKFLOW_DIR) -> List[ScheduledWorkflow]:
    return scan_workflows(directory)[0]


# ---- pure: verdict and plan -------------------------------------------------------------


@dataclass(frozen=True)
class Verdict:
    state: str
    run: Optional[Json] = None


def verdict_of(runs: Iterable[Json]) -> Verdict:
    """The state of a workflow from its completed scheduled runs, newest decisive run first."""
    ordered = sorted(runs, key=lambda run: run.get("created_at") or "", reverse=True)
    for run in ordered:
        conclusion = run.get("conclusion")
        if conclusion in FAILING_CONCLUSIONS:
            return Verdict(STATE_FAILING, run)
        if conclusion in PASSING_CONCLUSIONS:
            return Verdict(STATE_PASSING, run)
    return Verdict(STATE_INCONCLUSIVE if ordered else STATE_NEVER_RUN)


def settle(verdict: Verdict, age_days: Optional[int], threshold: int = NEVER_RUN_DAYS) -> Verdict:
    """A workflow that never ran and whose file is older than ``threshold`` days has never FIRED."""
    if verdict.state == STATE_NEVER_RUN and age_days is not None and age_days > threshold:
        return Verdict(STATE_NEVER_FIRED)
    return verdict


def plan_for(verdict: Verdict, issue: Optional[Json], human: bool = False) -> str:
    """open / update / close / recovered-note / none, from the verdict and the workflow's issue (or None)."""
    if verdict.state in (STATE_FAILING, STATE_NEVER_FIRED):
        return ACTION_UPDATE if issue else ACTION_OPEN
    if verdict.state == STATE_PASSING and issue:
        return ACTION_RECOVER if human else ACTION_CLOSE
    return ACTION_NONE


def first_failure(jobs: Iterable[Json]) -> Failure:
    """The first failed job and its first failed step; a run with no job at all failed at start-up."""
    listed = list(jobs)
    if not listed:
        return Failure(NO_JOB_STARTED, "-")
    for job in listed:
        if job.get("conclusion") in STEP_FAILED:
            steps = [s for s in job.get("steps") or [] if s.get("conclusion") in STEP_FAILED]
            return Failure(job.get("name") or NOT_DETERMINED, steps[0].get("name") if steps else NOT_DETERMINED)
    return Failure()


def git_age_days(file: str, now: Optional[datetime] = None) -> Optional[int]:
    """Whole days since the workflow file was first added to the history; None when git cannot say."""
    cmd = ["git", "log", "--diff-filter=A", "--format=%aI", "--", f".github/workflows/{file}"]
    try:
        done = subprocess.run(  # nosec B603  # fixed argv, no shell
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=GIT_TIMEOUT_SECONDS
        )
        added = datetime.fromisoformat(done.stdout.split()[-1])
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return None
    return ((now or datetime.now(timezone.utc)) - added).days


def never_run_note(state: str, age: Optional[int]) -> str:
    """The WARNING column for a workflow with no completed scheduled run; empty for every other state."""
    if state not in (STATE_NEVER_RUN, STATE_NEVER_FIRED):
        return ""
    return NEVER_RUN_NOTE if age is None else f"{NEVER_RUN_NOTE} (file added {age} days ago)"


# ---- IO ---------------------------------------------------------------------------------


class SweepClient(IssueClient):
    """The shared issue client, raising ``SweepError``, plus the Actions, milestone and sub-issue calls."""

    error = SweepError

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.problems: List[str] = []
        self._milestone: Optional[int] = None
        self._milestone_read = False

    def comments(self, number: int) -> List[Json]:
        """The shared reader opens its own connection; its OSError/ValueError become a SweepError (one workflow)."""
        try:
            return super().comments(number)
        except (OSError, ValueError) as exc:
            raise self.error(f"cannot read the comments of #{number}: {type(exc).__name__}: {exc}") from exc

    def scheduled_runs(self, file: str) -> List[Json]:
        """Completed ``schedule`` runs of one workflow file; a workflow the API does not know has none."""
        query = urllib.parse.urlencode({"event": "schedule", "status": "completed", "per_page": RUNS_PER_WORKFLOW})
        path = f"/repos/{self.repo}/actions/workflows/{urllib.parse.quote(file)}/runs?{query}"
        status, body = self.api.request("GET", path, None)
        if status == 404:
            return []
        if status != 200 or not isinstance(body, dict):
            raise self.error(f"cannot list the scheduled runs of {file}: HTTP {status}: {body}")
        return list(body.get("workflow_runs") or [])

    def failure_of(self, run_id: int) -> Failure:
        try:
            return first_failure(self.api.run_jobs(run_id))
        except WatchdogApiError as exc:
            raise self.error(str(exc)) from exc

    def all_open_issues(self) -> List[Json]:
        """Every open issue (never a PR) in one listing; a partial listing is refused, not acted on."""
        items, complete = list_issues(self, {"state": "open"}, max_pages=MAX_ISSUE_PAGES)
        if not complete:
            raise self.error(f"more than {MAX_ISSUE_PAGES} pages of open issues; refusing to act on a partial list")
        return items

    def milestone_number(self) -> Optional[int]:
        """The goal milestone's number by title, looked up once per run; None (and a problem) when absent."""
        if not self._milestone_read:
            self._milestone_read = True
            self._milestone = self._find_milestone()
            if self._milestone is None:
                self.problems.append(f"no open milestone titled {MILESTONE_TITLE!r}; issues are opened without one")
        return self._milestone

    def _find_milestone(self) -> Optional[int]:
        try:
            query = urllib.parse.urlencode({"state": "open", "per_page": MILESTONE_PAGE_SIZE})
            for item in self.call("GET", f"/repos/{self.repo}/milestones?{query}"):
                if item.get("title") == MILESTONE_TITLE:
                    return int(item["number"])
        except SweepError as exc:
            self.problems.append(f"cannot list milestones: {exc}")
        return None

    def attach_to_umbrella(self, umbrella: Optional[Json], created: Json) -> None:
        """Make ``created`` a native sub-issue of the umbrella (by the issue's numeric id, not its number)."""
        if umbrella is None:
            return
        path = f"/repos/{self.repo}/issues/{umbrella['number']}/sub_issues"
        try:
            self.call("POST", path, {"sub_issue_id": created["id"]}, ok=(201,))
        except SweepError as exc:
            self.problems.append(f"#{created['number']} was opened but not attached to the umbrella: {exc}")

    def comment(self, number: int, body: str) -> None:
        self.call("POST", f"/repos/{self.repo}/issues/{number}/comments", {"body": body}, ok=(201,))


@dataclass(frozen=True)
class Outcome:
    file: str
    state: str
    action: str
    issue: Optional[int] = None
    note: str = ""

    def line(self) -> str:
        return "\t".join([self.file, self.state, self.action, f"#{self.issue}" if self.issue else "-", self.note])


Done = Tuple[str, Optional[int]]


def _open(
    client: SweepClient, wf: ScheduledWorkflow, verdict: Verdict, targets: Targets, age: Optional[int], dry_run: bool
) -> Done:
    run = verdict.run
    failure = client.failure_of(run["id"]) if run else Failure()
    if dry_run:
        return ACTION_OPEN, None
    payload: Json = {
        "title": issue_title(wf),
        "body": issue_body(wf, run, failure, age),
        "labels": [*ISSUE_LABELS, PHASE_LABEL],
    }
    milestone = client.milestone_number()
    if milestone is not None:
        payload["milestone"] = milestone
    created = client.call("POST", f"/repos/{client.repo}/issues", payload, ok=(201,))
    client.attach_to_umbrella(targets.umbrella, created)
    return ACTION_OPEN, created["number"]


def _update(
    client: SweepClient,
    wf: ScheduledWorkflow,
    verdict: Verdict,
    issue: Json,
    human: bool,
    age: Optional[int],
    dry_run: bool,
) -> Done:
    number, run = issue["number"], verdict.run
    if run_key(run) in reported_keys(marker_events(issue, client.comments(number))):
        return ACTION_ALREADY, number
    failure = client.failure_of(run["id"]) if run else Failure()
    if not dry_run:
        client.comment(number, failure_comment(wf, run, failure, age, human))
    return ACTION_UPDATE, number


def _close(client: SweepClient, wf: ScheduledWorkflow, run: Json, issue: Json, dry_run: bool) -> Done:
    number = issue["number"]
    if not dry_run:
        client.comment(number, passing_comment(wf, run))
        client.call("PATCH", f"/repos/{client.repo}/issues/{number}", {"state": "closed", "state_reason": "completed"})
    return ACTION_CLOSE, number


def _recover(client: SweepClient, wf: ScheduledWorkflow, run: Json, issue: Json, dry_run: bool) -> Done:
    """A person's issue is never closed: one note, and only when our own last word there was a failure."""
    number = issue["number"]
    if not last_word_is_failure(marker_events(issue, client.comments(number))):
        return ACTION_NONE, number
    if not dry_run:
        client.comment(number, passing_comment(wf, run, human=True))
    return ACTION_RECOVER, number


def _apply(
    client: SweepClient,
    wf: ScheduledWorkflow,
    verdict: Verdict,
    targets: Targets,
    issue: Optional[Json],
    human: bool,
    age: Optional[int],
    dry_run: bool,
) -> Done:
    action, run = plan_for(verdict, issue, human), verdict.run
    if action == ACTION_OPEN:
        return _open(client, wf, verdict, targets, age, dry_run)
    if issue is None:
        return ACTION_NONE, None
    if action == ACTION_UPDATE:
        return _update(client, wf, verdict, issue, human, age, dry_run)
    if run is not None and action == ACTION_CLOSE:
        return _close(client, wf, run, issue, dry_run)
    if run is not None and action == ACTION_RECOVER:
        return _recover(client, wf, run, issue, dry_run)
    return ACTION_NONE, issue["number"]


def handle_workflow(
    client: SweepClient, wf: ScheduledWorkflow, targets: Targets, dry_run: bool, age_of: AgeOf = None
) -> Outcome:
    verdict = verdict_of(client.scheduled_runs(wf.file))
    age = age_of(wf.file) if age_of is not None and verdict.state == STATE_NEVER_RUN else None
    verdict = settle(verdict, age)
    own = targets.own.get(wf.file)
    human = None if own else targets.human.get(wf.file)
    done, number = _apply(client, wf, verdict, targets, own or human, human is not None, age, dry_run)
    shown = f"would-{done}" if dry_run and done in WRITING_ACTIONS else done
    note = never_run_note(verdict.state, age)
    if note:
        logger.warning("%s: %s", wf.file, note)
    return Outcome(wf.file, verdict.state, shown, number, note)


def sweep(
    client: SweepClient, workflows: Sequence[ScheduledWorkflow], dry_run: bool, age_of: AgeOf = None
) -> Tuple[List[Outcome], List[str]]:
    """Every workflow handled on its own: one API failure is reported and the rest still run."""
    files = [wf.file for wf in workflows]
    targets = build_targets(client.all_open_issues(), files)
    if targets.umbrella is None:
        client.problems.append("no open issue carries the umbrella marker; new issues are not attached to one")
    for file in sorted(set(targets.own) - set(files)):
        logger.warning("#%s is open for %s, no longer scheduled; left to a person", targets.own[file]["number"], file)
    outcomes: List[Outcome] = []
    errors: List[str] = []
    for wf in workflows:
        try:
            outcomes.append(handle_workflow(client, wf, targets, dry_run, age_of))
        except SweepError as exc:
            errors.append(f"{wf.file}: {exc}")
    return outcomes, [*client.problems, *errors]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="read everything, write no issue or comment")
    args = parser.parse_args(argv)
    workflows, problems = scan_workflows()
    if not workflows:
        logger.error("no scheduled workflow found under %s; refusing to report a clean sweep", WORKFLOW_DIR)
        return 1
    try:
        outcomes, errors = sweep(SweepClient(build_api()), workflows, args.dry_run, git_age_days)
    except (IssueApiError, WatchdogError) as exc:
        logger.error("%s", exc)
        return 1
    sys.stdout.write("workflow\tstate\taction\tissue\tnote\n")
    sys.stdout.write("".join(f"{outcome.line()}\n" for outcome in outcomes))
    for problem in [*problems, *errors]:
        logger.error("%s", problem)
    return 1 if problems or errors else 0


if __name__ == "__main__":
    sys.exit(main())
