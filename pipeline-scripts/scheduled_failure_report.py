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
   decides. Runs exist but none decides: ``inconclusive``, no action. No completed scheduled
   run at all: ``never-run``, no action (a workflow added today has nothing to report yet).
3. **The issue.** Found by a hidden marker line in the body
   (``<!-- scheduled-failure-report:<file> -->``) among the open issues labelled ``bug`` and
   ``ci``; the title is never matched. Failing and no issue: open one. Failing with an issue:
   a NEW comment per failing run (never twice for the same run, whose id is a hidden marker in
   the body or comment). Passing with an issue: a closing comment, then close. An open issue
   whose workflow is no longer scheduled is left to a person and logged.

``--dry-run`` reads everything and writes nothing. Stdlib plus PyYAML; HTTP goes through
``github_api.GitHubApi``, the issue client and paginator are ``issue_api`` (#19522), the comment
reader is the shared helper (#12984). The report goes to STDOUT, diagnostics at WARNING or above.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
# CI runs this as a bare ``python3 pipeline-scripts/...``, so the repo root is added the way the
# sibling pipeline scripts do (audit_unwired_trackers.py), then this directory for the shared clients.
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from github_api import WatchdogApiError, WatchdogError, build_api  # noqa: E402
from issue_api import IssueApiError, IssueClient, list_issues  # noqa: E402

from autobot_shared.logging_manager import get_logger  # noqa: E402

logger = get_logger(__name__)

WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
ISSUE_LABELS = ("bug", "ci")
RUNS_PER_WORKFLOW = 10
MAX_ISSUE_PAGES = 20

FAILING_CONCLUSIONS: FrozenSet[str] = frozenset({"failure", "timed_out", "startup_failure"})
PASSING_CONCLUSIONS: FrozenSet[str] = frozenset({"success"})
STEP_FAILED: FrozenSet[str] = frozenset({"failure", "timed_out"})

STATE_FAILING = "failing"
STATE_PASSING = "passing"
STATE_NEVER_RUN = "never-run"
STATE_INCONCLUSIVE = "inconclusive"

ACTION_OPEN = "open"
ACTION_UPDATE = "update"
ACTION_CLOSE = "close"
ACTION_NONE = "none"
ACTION_ALREADY = "already-reported"
WRITING_ACTIONS = frozenset({ACTION_OPEN, ACTION_UPDATE, ACTION_CLOSE})

NOT_DETERMINED = "not determined"
NO_JOB_STARTED = "none: the run ended before any job started"

REPORT_MARKER = "<!-- scheduled-failure-report:{file} -->"
RUN_MARKER = "<!-- scheduled-failure-run:{run_id} -->"
_REPORT_MARKER_RE = re.compile(r"<!-- scheduled-failure-report:(\S+) -->")
_RUN_MARKER_RE = re.compile(r"<!-- scheduled-failure-run:(\d+) -->")

Json = Dict[str, Any]


class SweepError(IssueApiError):
    """The API answered with something this sweep cannot act on."""


# ---- pure: which workflows are scheduled ------------------------------------------------


@dataclass(frozen=True)
class ScheduledWorkflow:
    file: str
    name: str


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


def plan_for(verdict: Verdict, issue: Optional[Json]) -> str:
    """open / update / close / none, from the verdict and the workflow's open issue (or None)."""
    if verdict.state == STATE_FAILING:
        return ACTION_UPDATE if issue else ACTION_OPEN
    if verdict.state == STATE_PASSING and issue:
        return ACTION_CLOSE
    return ACTION_NONE


@dataclass(frozen=True)
class Failure:
    job: str = NOT_DETERMINED
    step: str = NOT_DETERMINED


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


# ---- pure: issue text and markers -------------------------------------------------------


def run_date(run: Json) -> str:
    return (run.get("run_started_at") or run.get("created_at") or "unknown")[:10]


def _facts(wf: ScheduledWorkflow, run: Json, failure: Failure) -> str:
    return "\n".join(
        [
            "| | |",
            "| --- | --- |",
            f"| Workflow | {wf.name} (`.github/workflows/{wf.file}`) |",
            f"| Run | {run.get('html_url')} |",
            f"| Conclusion | {run.get('conclusion')} |",
            f"| Date (UTC) | {run_date(run)} |",
            f"| First failing job | {failure.job} |",
            f"| First failing step | {failure.step} |",
        ]
    )


def issue_title(wf: ScheduledWorkflow) -> str:
    return f"Scheduled workflow failing: {wf.name} ({wf.file})"


def issue_body(wf: ScheduledWorkflow, run: Json, failure: Failure) -> str:
    return (
        f"{REPORT_MARKER.format(file=wf.file)}\n{RUN_MARKER.format(run_id=run['id'])}\n"
        "The latest scheduled run of this workflow failed.\n\n"
        f"{_facts(wf, run, failure)}\n\n"
        "The daily scheduled-failure sweep opened this issue. A later failing run adds a comment here; "
        "the sweep closes the issue once the workflow's latest scheduled run passes."
    )


def failure_comment(wf: ScheduledWorkflow, run: Json, failure: Failure) -> str:
    marker = RUN_MARKER.format(run_id=run["id"])
    return f"{marker}\nThe scheduled workflow failed again.\n\n{_facts(wf, run, failure)}"


def passing_comment(wf: ScheduledWorkflow, run: Json) -> str:
    return (
        f"The latest scheduled run of {wf.name} passed ({run.get('html_url')}, {run_date(run)}, "
        f"conclusion {run.get('conclusion')}). Closing; a new failure opens a new issue."
    )


def marker_file(body: Optional[str]) -> Optional[str]:
    match = _REPORT_MARKER_RE.search(body or "")
    return match.group(1) if match else None


def issues_by_workflow(issues: Iterable[Json]) -> Dict[str, Json]:
    """Workflow file -> its open issue by marker; with duplicates the lowest number is the home."""
    found: Dict[str, Json] = {}
    for issue in sorted(issues, key=lambda item: item["number"]):
        file = marker_file(issue.get("body"))
        if file is None:
            continue
        if file in found:
            logger.warning("#%s repeats #%s for %s; left to a person", issue["number"], found[file]["number"], file)
            continue
        found[file] = issue
    return found


def reported_run_ids(issue: Json, comments: Iterable[Json]) -> Set[int]:
    """Run ids already reported on the issue, from the hidden run markers in its body and comments."""
    texts = [issue.get("body") or ""] + [c.get("body") or "" for c in comments]
    return {int(found) for text in texts for found in _RUN_MARKER_RE.findall(text)}


# ---- IO ---------------------------------------------------------------------------------


class SweepClient(IssueClient):
    """The shared issue client, raising ``SweepError``, plus the Actions reads this sweep needs."""

    error = SweepError

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

    def open_report_issues(self) -> Dict[str, Json]:
        """Open issues carrying the report labels, by workflow; a partial listing is refused, not acted on."""
        params = {"state": "open", "labels": ",".join(ISSUE_LABELS)}
        items, complete = list_issues(self, params, max_pages=MAX_ISSUE_PAGES)
        if not complete:
            raise self.error(f"more than {MAX_ISSUE_PAGES} pages of open {'/'.join(ISSUE_LABELS)} issues")
        return issues_by_workflow(items)

    def comment(self, number: int, body: str) -> None:
        self.call("POST", f"/repos/{self.repo}/issues/{number}/comments", {"body": body}, ok=(201,))


@dataclass(frozen=True)
class Outcome:
    file: str
    state: str
    action: str
    issue: Optional[int] = None

    def line(self) -> str:
        return "\t".join([self.file, self.state, self.action, f"#{self.issue}" if self.issue else "-"])


Done = Tuple[str, Optional[int]]


def _open(client: SweepClient, wf: ScheduledWorkflow, run: Json, dry_run: bool) -> Done:
    failure = client.failure_of(run["id"])
    if dry_run:
        return ACTION_OPEN, None
    payload = {"title": issue_title(wf), "body": issue_body(wf, run, failure), "labels": list(ISSUE_LABELS)}
    created = client.call("POST", f"/repos/{client.repo}/issues", payload, ok=(201,))
    return ACTION_OPEN, created["number"]


def _update(client: SweepClient, wf: ScheduledWorkflow, run: Json, issue: Json, dry_run: bool) -> Done:
    number = issue["number"]
    if run["id"] in reported_run_ids(issue, client.comments(number)):
        return ACTION_ALREADY, number
    failure = client.failure_of(run["id"])
    if not dry_run:
        client.comment(number, failure_comment(wf, run, failure))
    return ACTION_UPDATE, number


def _close(client: SweepClient, wf: ScheduledWorkflow, run: Json, issue: Json, dry_run: bool) -> Done:
    number = issue["number"]
    if not dry_run:
        client.comment(number, passing_comment(wf, run))
        client.call("PATCH", f"/repos/{client.repo}/issues/{number}", {"state": "closed", "state_reason": "completed"})
    return ACTION_CLOSE, number


def handle_workflow(client: SweepClient, wf: ScheduledWorkflow, issues: Dict[str, Json], dry_run: bool) -> Outcome:
    verdict = verdict_of(client.scheduled_runs(wf.file))
    issue = issues.get(wf.file)
    action = plan_for(verdict, issue)
    run = verdict.run
    if action == ACTION_OPEN:
        done, number = _open(client, wf, run, dry_run)
    elif action == ACTION_UPDATE:
        done, number = _update(client, wf, run, issue, dry_run)
    elif action == ACTION_CLOSE:
        done, number = _close(client, wf, run, issue, dry_run)
    else:
        done, number = ACTION_NONE, (issue["number"] if issue else None)
    shown = f"would-{done}" if dry_run and done in WRITING_ACTIONS else done
    return Outcome(wf.file, verdict.state, shown, number)


def sweep(
    client: SweepClient, workflows: Sequence[ScheduledWorkflow], dry_run: bool
) -> Tuple[List[Outcome], List[str]]:
    """Every workflow handled on its own: one API failure is reported and the rest still run."""
    issues = client.open_report_issues()
    for file in sorted(set(issues) - {wf.file for wf in workflows}):
        logger.warning("#%s is open for %s, no longer scheduled; left to a person", issues[file]["number"], file)
    outcomes: List[Outcome] = []
    errors: List[str] = []
    for wf in workflows:
        try:
            outcomes.append(handle_workflow(client, wf, issues, dry_run))
        except SweepError as exc:
            errors.append(f"{wf.file}: {exc}")
    return outcomes, errors


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="read everything, write no issue or comment")
    args = parser.parse_args(argv)
    workflows, problems = scan_workflows()
    if not workflows:
        logger.error("no scheduled workflow found under %s; refusing to report a clean sweep", WORKFLOW_DIR)
        return 1
    try:
        outcomes, errors = sweep(SweepClient(build_api()), workflows, args.dry_run)
    except (IssueApiError, WatchdogError) as exc:
        logger.error("%s", exc)
        return 1
    sys.stdout.write("workflow\tstate\taction\tissue\n")
    sys.stdout.write("".join(f"{outcome.line()}\n" for outcome in outcomes))
    for problem in [*problems, *errors]:
        logger.error("%s", problem)
    return 1 if problems or errors else 0


if __name__ == "__main__":
    sys.exit(main())
