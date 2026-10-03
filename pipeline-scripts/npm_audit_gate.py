# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Gate the frontend dependency audit on ONE ``npm audit --json`` report (#16337).

The Security Scan job used to call npm's audit service twice: ``npm audit
--json`` for the artifact, then ``npm audit --audit-level=high`` as the gate.

Attribution is per ``via`` ENTRY, not per package (#17889, second review). Three defects
lived in one line of the first version: ids collected across the whole ``via`` list before
asking whether any were missing, so a second dict with no ``GHSA-`` url was dropped (a
legacy ``npmjs.com/advisories/N`` url is that shape); one string in ``via`` set a flag that
suppressed the check entirely; and a string ``via`` was trusted without checking the package
it names is in the report. A failing entry with no ``severity`` was skipped outright while
``metadata.counts`` went on reporting it high. Anything that cannot be attributed to a GHSA
id now fails, because an advisory the gate cannot name is one it cannot excuse.
The gate repeated a network call for data the first one already had, and when
that second call failed -- a 400 from npm's retiring ``audits/quick`` fallback
on 2026-09-11 -- the job went red exactly as it does for a real advisory.

This makes one call, retried a bounded number of times while the service is
unavailable, and decides from the report it got. Three results, each with its
own exit code, job-summary headline and annotation:

* ``passed``      (0) no high or critical advisory.
* ``found``       (1) at least one high or critical advisory.
* ``unavailable`` (2) no usable report after every attempt. The gate could not
  check, which is NOT a pass -- it stays fail-closed -- but it says it did not
  look instead of claiming it found something.

A report npm fetched through ``audits/quick`` counts as ``unavailable``. npm
7-10 falls back to that retiring endpoint when the bulk advisory call fails;
npm 11 dropped the fallback. The workflow pins npm 11 for this call, and this
check keeps a future downgrade from quietly depending on the old endpoint.

    python3 ../pipeline-scripts/npm_audit_gate.py --npm "npx --yes npm@11.19.1"

Env-backed constants (unset or invalid falls back to the default):
    NPM_AUDIT_MAX_ATTEMPTS          attempts before "unavailable" (default 3)
    NPM_AUDIT_RETRY_DELAY_SECONDS   pause between attempts (default 15)
    NPM_AUDIT_TIMEOUT_SECONDS       limit on one attempt (default 180)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 15
DEFAULT_TIMEOUT_SECONDS = 180

SEVERITY_ORDER = ("critical", "high", "moderate", "low", "info")
FAILING_SEVERITIES = ("critical", "high")

BULK_ENDPOINT = "/-/npm/v1/security/advisories/bulk"
QUICK_ENDPOINT = "/-/npm/v1/security/audits/quick"
_ENDPOINT_MARKER = "/-/npm/v1/security/"
_GHSA = re.compile(r"GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}")

PASSED, FOUND, UNAVAILABLE = "passed", "found", "unavailable"
EXIT_CODES = {PASSED: 0, FOUND: 1, UNAVAILABLE: 2}
ANNOTATION_TITLES = {FOUND: "npm audit: advisories found", UNAVAILABLE: "npm audit: could not check"}
EXCUSED_TITLE = "npm audit: passed with a recorded exception"
STALE_TITLE = "npm audit: the exception record is stale"


@dataclass
class Verdict:
    """What one audit attempt showed."""

    result: str
    counts: dict[str, int] = field(default_factory=dict)
    reason: str = ""
    endpoint: str = "unknown"


@dataclass
class Outcome:
    """The verdict the gate acts on, how many attempts it took, and the raw report."""

    verdict: Verdict
    attempts: int
    report: str


@dataclass(frozen=True)
class AdvisoryException:
    """One advisory the gate yields to, with the reason and the date it stops counting."""

    expires: str
    reason: str


#: Advisories with NO published fix, which the gate yields to until ``expires``.
#:
#: Yielding is deliberate and recorded, which is what the workflow comment above this
#: gate asks for -- "if an advisory ever has no published fix and the gate has to yield,
#: change it deliberately and record why on #13400 -- do not silence it as a flake".
#:
#: Four conditions, each failing LOUDLY rather than quietly widening the gate:
#:   * ``expires`` is in the future. An expired entry fails the gate naming itself, so the
#:     yield cannot outlive the reason for it by inattention.
#:   * npm reports **no fix available** for any failing package. The moment a bump exists
#:     the exception stops being honoured and the gate demands the bump -- which is the
#:     only reason this is not a silence.
#:   * every entry is still reported. A drained entry fails, the same shrink-only pressure
#:     the ratchet baselines use, so the record cannot accumulate dead policy.
#:   * an advisory not listed here still fails. The set is a floor on scrutiny, not a lid.
#:
#: The expiry is enforced by THIS GATE and not by the test suite, deliberately: a test
#: failing on a date would block every Python PR, where the gate blocks only the PRs that
#: trigger the frontend suite. So the suite stays date-independent and #17890 carries the
#: reminder to look again before 2026-11-14.
ADVISORY_EXCEPTIONS: dict[str, AdvisoryException] = {
    "GHSA-vfj7-8cjw-p6xm": AdvisoryException(
        expires="2026-11-14",
        reason=(
            "braces <= 3.0.3 stack-exhaustion DoS, published 2026-09-18 with "
            "first_patched_version null -- every lockfile here is already at 3.0.3, so no "
            "bump exists. Reached only through devDependencies (stylelint and "
            "@vue/eslint-config-typescript, via micromatch/fast-glob/globby); nothing in a "
            "shipped bundle imports it. Owner decision 2026-10-03, recorded on #13400."
        ),
    ),
}


def _attribute_entry(package: str, entry: dict, detail: dict) -> tuple[set[str], list[str]]:
    """``(advisory ids this entry names, reasons it is not fully attributed)`` -- per via
    entry, for the three reasons in the module docstring."""
    ids: set[str] = set()
    problems: list[str] = []
    vias = entry.get("via") or []
    if not vias:
        return ids, [f"{package} is a failing advisory with no `via` entries to attribute"]
    for via in vias:
        if isinstance(via, dict):
            match = _GHSA.search(str(via.get("url") or ""))
            if match:
                ids.add(match.group(0))
            else:
                problems.append(f"{package} names an advisory with no GHSA id: {via.get('url') or via!r}")
        elif isinstance(via, str):
            if via not in detail:
                problems.append(f"{package} is attributed to `{via}`, which the report does not describe")
        else:
            problems.append(f"{package} has a `via` entry that is neither an advisory nor a package: {via!r}")
    return ids, problems


def _failing_advisories(report: dict) -> tuple[set[str], bool, list[str]] | None:
    """``(advisory ids, any failing package is fixable, reasons attribution is incomplete)``.

    ``None`` when the detail is unreadable, which must NOT be read as "nothing to see": the
    caller keeps a failing verdict. The parse failed OPEN twice before this.
    """
    detail = report.get("vulnerabilities")
    if not isinstance(detail, dict):
        return None
    ids: set[str] = set()
    fixable = False
    problems: list[str] = []
    for package, entry in sorted(detail.items()):
        if not isinstance(entry, dict):
            problems.append(f"{package}'s entry is not a mapping, so its severity is unknown")
            continue
        severity = entry.get("severity")
        if severity is None:
            # Skipping it treated "no severity recorded" as "not failing", while
            # metadata.counts went on reporting it high (second #17889 review).
            problems.append(f"{package} has no severity recorded, so it cannot be ruled out")
            continue
        if severity not in FAILING_SEVERITIES:
            continue
        if entry.get("fixAvailable"):
            fixable = True
        entry_ids, entry_problems = _attribute_entry(str(package), entry, detail)
        ids |= entry_ids
        problems += entry_problems
    return ids, fixable, problems


def _entry_problem(
    advisory: str, exception: AdvisoryException, ids: set[str], fixable: bool, today: date
) -> str | None:
    """Why this entry is not honoured, or ``None`` when it is. Never raises."""
    if advisory not in ids:
        return (
            f"{advisory} is recorded as unfixable but is no longer reported -- remove it from "
            "ADVISORY_EXCEPTIONS; a record that outlives its advisory is dead policy"
        )
    try:
        expires = date.fromisoformat(exception.expires)
    except ValueError:
        return f"{advisory}'s expiry {exception.expires!r} is not a date -- the record is unusable"
    if expires < today:
        return (
            f"{advisory}'s exception expired on {exception.expires} -- re-check for a published "
            "fix and either bump or renew it deliberately"
        )
    if fixable:
        return (
            f"{advisory} is recorded as unfixable, but npm reports a fix available for a failing "
            "package -- bump it; the exception is not honoured while a bump exists"
        )
    return None


def exception_problems(ids: set[str], fixable: bool, today: date) -> tuple[set[str], list[str]]:
    """``(ids honoured, reasons the record itself is wrong)``.

    The second half is the point: a record that can only ever widen the gate is a silence
    with extra steps, so every way it can be stale is a failure that names itself.
    """
    honoured: set[str] = set()
    problems: list[str] = []
    for advisory, exception in sorted(ADVISORY_EXCEPTIONS.items()):
        problem = _entry_problem(advisory, exception, ids, fixable, today)
        if problem:
            problems.append(problem)
        else:
            honoured.add(advisory)
    return honoured, problems


def _emit(text: str, *, err: bool = False) -> None:
    """stdout/stderr ARE this CLI's interface: the job log and GitHub annotations."""
    print(text, file=sys.stderr if err else sys.stdout)  # noqa: print


def _env_int(name: str, default: int, *, minimum: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw.isdigit() or int(raw) < minimum:
        return default
    return int(raw)


def max_attempts() -> int:
    return _env_int("NPM_AUDIT_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS, minimum=1)


def retry_delay_seconds() -> int:
    return _env_int("NPM_AUDIT_RETRY_DELAY_SECONDS", DEFAULT_RETRY_DELAY_SECONDS, minimum=0)


def timeout_seconds() -> int:
    return _env_int("NPM_AUDIT_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, minimum=1)


def endpoint_used(log: str) -> str:
    """The advisory endpoint npm's http log shows it calling.

    ``audits/quick`` wins when both appear: npm only reaches it after the bulk
    call failed, so its presence means the report did not come from bulk.
    """
    if QUICK_ENDPOINT in log:
        return "audits/quick"
    if BULK_ENDPOINT in log:
        return "advisories/bulk"
    return "unknown"


def _error_reason(report: dict) -> str | None:
    error = report.get("error")
    if not error:
        return None
    if isinstance(error, dict):
        return str(error.get("summary") or error.get("code") or error)
    return str(error)


def _counts(vulnerabilities: dict) -> dict[str, int] | None:
    """Every severity's count, or None when any is missing or not a count.

    A missing, non-numeric or negative count is not zero: reading it as zero
    would turn a malformed report into a pass (#16357 review).
    """
    counts = {key: vulnerabilities.get(key) for key in SEVERITY_ORDER}
    if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in counts.values()):
        return None
    return counts  # type: ignore[return-value]


def _counts_contradict_detail(report: dict) -> bool:
    """A zero failing count over a detail entry that IS failing: the report disagrees with
    itself, which is unreadable rather than clean. Closed rather than recorded (#17890 N2)
    because nobody will be here when it becomes reachable."""
    detail = report.get("vulnerabilities")
    return isinstance(detail, dict) and any(
        isinstance(entry, dict) and entry.get("severity") in FAILING_SEVERITIES for entry in detail.values()
    )


def _clean_or_stale(counts: dict[str, int], endpoint: str, today: date) -> Verdict:
    """A clean audit still fails while a recorded exception has outlived its advisory.

    This is the drain case and the one that actually matters: braces being fixed is exactly
    when the counts go to zero, and the staleness check used to sit AFTER the zero-count
    return, so the entry could never be flagged in the only situation where it is stale
    (review on #17889). Shrink-only, the same pressure the ratchet baselines use.
    """
    _, problems = exception_problems(set(), False, today)
    if problems:
        return Verdict(FOUND, counts=counts, reason="; ".join(problems), endpoint=endpoint)
    return Verdict(PASSED, counts=counts, endpoint=endpoint)


def _excused_or_found(report: dict, counts: dict[str, int], endpoint: str, today: date) -> Verdict:
    """A failing count becomes PASSED only when every advisory in it is a recorded exception."""
    detail = _failing_advisories(report)
    if detail is None:
        reason = "advisories found, and the per-package detail was unreadable so none could be excused"
        return Verdict(FOUND, counts=counts, reason=reason, endpoint=endpoint)
    ids, fixable, unattributed = detail
    if unattributed:
        reason = "advisories found that could not be attributed to an advisory id: " + "; ".join(unattributed)
        return Verdict(FOUND, counts=counts, reason=reason, endpoint=endpoint)
    if not ids:
        reason = "advisories found, but the report named no advisory id, so none could be excused"
        return Verdict(FOUND, counts=counts, reason=reason, endpoint=endpoint)
    honoured, problems = exception_problems(ids, fixable, today)
    unexcused = sorted(ids - honoured)
    if problems or unexcused:
        # BOTH, never one: reporting only the stale entry sent the reader to remove it while
        # the gate still failed for an advisory nobody had named (review on #17889).
        if unexcused:
            problems.append(f"not excused: {', '.join(unexcused)}")
        return Verdict(FOUND, counts=counts, reason="; ".join(problems), endpoint=endpoint)
    excused = ", ".join(
        f"{advisory} (expires {ADVISORY_EXCEPTIONS[advisory].expires})" for advisory in sorted(honoured)
    )
    reason = f"{counts['high'] + counts['critical']} excused by recorded exception: {excused} -- see #13400"
    return Verdict(PASSED, counts=counts, reason=reason, endpoint=endpoint)


def classify(stdout: str, log: str = "", today: date | None = None) -> Verdict:
    """One attempt's report as passed / found / unavailable. Never raises."""
    endpoint = endpoint_used(log)
    try:
        report = json.loads(stdout)
    except ValueError:
        return Verdict(UNAVAILABLE, reason="npm audit did not return a JSON report", endpoint=endpoint)
    if not isinstance(report, dict):
        return Verdict(UNAVAILABLE, reason="npm audit returned JSON that is not a report", endpoint=endpoint)
    error = _error_reason(report)
    if error:
        return Verdict(UNAVAILABLE, reason=f"audit endpoint error: {error}", endpoint=endpoint)
    if endpoint == "audits/quick":
        reason = "the bulk advisory call failed and npm fell back to the retiring audits/quick endpoint"
        return Verdict(UNAVAILABLE, reason=reason, endpoint=endpoint)
    vulnerabilities = (report.get("metadata") or {}).get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return Verdict(UNAVAILABLE, reason="the report carries no vulnerability counts", endpoint=endpoint)
    counts = _counts(vulnerabilities)
    if counts is None:
        reason = "the report's severity counts are missing or are not counts"
        return Verdict(UNAVAILABLE, reason=reason, endpoint=endpoint)
    if not any(counts[severity] for severity in FAILING_SEVERITIES):
        if _counts_contradict_detail(report):
            reason = "the severity counts say nothing failing while the per-package detail lists a failing advisory"
            return Verdict(UNAVAILABLE, counts=counts, reason=reason, endpoint=endpoint)
        return _clean_or_stale(counts, endpoint, today or date.today())

    return _excused_or_found(report, counts, endpoint, today or date.today())


Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def _run_npm_audit(command: list[str]) -> subprocess.CompletedProcess[str]:
    """One network call. ``--loglevel=http`` puts the endpoint npm used in stderr.

    ``errors="replace"``: an undecodable byte in npm's output must not raise
    (#16357 review) -- the report then fails to parse and reads as "could not
    check", which is what it is.
    """
    argv = [*command, "audit", "--json", "--loglevel=http"]
    return subprocess.run(
        argv, capture_output=True, text=True, errors="replace", check=False, timeout=timeout_seconds()
    )


def _attempt(command: list[str], run: Runner) -> tuple[str, str]:
    """(stdout, stderr) of one attempt; a timeout or a missing npm yields no report."""
    try:
        completed = run(command)
    except subprocess.TimeoutExpired:
        return "", f"npm audit timed out after {timeout_seconds()}s"
    except OSError as exc:
        return "", f"npm audit could not start: {exc}"
    return completed.stdout or "", completed.stderr or ""


def _log_endpoint_lines(log: str) -> None:
    """Echo npm's advisory-endpoint http lines, so the job log shows which one answered."""
    for line in log.splitlines():
        if _ENDPOINT_MARKER in line:
            _emit(line.strip(), err=True)


def audit_with_retries(
    command: list[str], attempts: int, delay: int, run: Runner, sleep: Callable[[float], None] = time.sleep
) -> Outcome:
    """Call npm audit until it yields a usable report, at most *attempts* times.

    Only ``unavailable`` is retried: a found advisory is an answer, not a flake.
    """
    verdict, stdout = Verdict(UNAVAILABLE, reason="npm audit was never run"), ""
    for attempt in range(1, attempts + 1):
        stdout, log = _attempt(command, run)
        _log_endpoint_lines(log)
        verdict = classify(stdout, log)
        if verdict.result != UNAVAILABLE:
            return Outcome(verdict, attempt, stdout)
        _emit(f"npm audit attempt {attempt}/{attempts} could not check: {verdict.reason}", err=True)
        if attempt < attempts:
            sleep(delay)
    return Outcome(verdict, attempts, stdout)


def _headline(outcome: Outcome, attempts: int) -> str:
    """The one line a reader sees. It must never describe a state that did not happen.

    ``verdict.reason`` was computed and dropped here (review on #17889), so an excused pass
    printed "no high or critical advisories" while six were excused -- the false statement
    being exactly what #13400 forbids, in the one place the mechanism is accountable. Every
    reason now reaches the headline, and a pass through an exception says so.
    """
    verdict = outcome.verdict
    if verdict.result == PASSED:
        if verdict.reason:
            return f"**Passed WITH recorded exception(s):** {verdict.reason}"
        return "**Passed:** no high or critical advisories in autobot-frontend."
    if verdict.result == FOUND:
        failing = verdict.counts["critical"] + verdict.counts["high"]
        if not failing:
            # A clean audit that fails is the stale-record case, and "advisories found: 0"
            # would send the reader hunting an advisory that is not there.
            return f"**Failed, the exception record is stale:** {verdict.reason}"
        return (
            f"**Failed, advisories found:** {verdict.counts['critical']} critical and "
            f"{verdict.counts['high']} high. Bump the dependency; do not silence the gate (#13400)."
            + (f" {verdict.reason}." if verdict.reason else "")
        )
    return (
        f"**Failed, could not check:** no usable audit report after {outcome.attempts} of {attempts} "
        f"attempt(s): {verdict.reason}. This is not an advisory finding; re-run once the registry answers."
    )


def summary_lines(outcome: Outcome, attempts: int) -> list[str]:
    """The job summary: which of the three results happened, and the counts when known."""
    verdict = outcome.verdict
    lines = [
        "## Frontend dependency audit",
        "",
        _headline(outcome, attempts),
        "",
        f"Result: `{verdict.result}` · advisory endpoint: `{verdict.endpoint}` · "
        f"attempts: {outcome.attempts} of {attempts}",
    ]
    if verdict.counts:
        lines += ["", "| Severity | Count |", "| --- | --- |"]
        lines += [f"| {key} | {verdict.counts[key]} |" for key in SEVERITY_ORDER]
    return lines


def _write_summary(lines: list[str]) -> None:
    """Append to the step summary; a summary that cannot be written never decides the gate."""
    text = "\n".join(lines) + "\n"
    path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not path:
        _emit(text)
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as exc:
        _emit(f"Could not write job summary: {exc}", err=True)


def _announce(outcome: Outcome, attempts: int) -> None:
    """One annotation. An excused pass is a WARNING, not silence: it is a pass nobody
    asked for on its merits, and it belongs in the checks UI rather than only the log."""
    verdict = outcome.verdict
    title = ANNOTATION_TITLES.get(verdict.result)
    if verdict.result == FOUND and not (verdict.counts.get("critical", 0) + verdict.counts.get("high", 0)):
        # The title is read on its own in the checks list, so "advisories found" over a
        # stale-record failure contradicts its own headline (found by this change's own test).
        title = STALE_TITLE
    headline = _headline(outcome, attempts).replace("**", "")
    if title:
        _emit(f"::error title={title}::{headline}")
    elif verdict.result == PASSED and verdict.reason:
        _emit(f"::warning title={EXCUSED_TITLE}::{headline}")
    else:
        _emit(headline)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--npm", default="npm", help='npm command to run, e.g. "npx --yes npm@11.19.1"')
    parser.add_argument("--report", default="audit-results.json", help="where the raw report is written")
    return parser.parse_args(argv)


def _write_report(path: str, report: str) -> None:
    """The artifact copy of the report; failing to write it never decides the gate."""
    try:
        Path(path).write_text(report, encoding="utf-8")
    except OSError as exc:
        _emit(f"Could not write {path}: {exc}", err=True)


def _audit_or_could_not_check(npm: str, attempts: int) -> Outcome:
    """Run the audit; anything unexpected inside the gate is "could not check".

    Fail-closed without borrowing another result's exit code (#16357 review): an
    uncaught exception would exit 1, the code for "advisories found", with no
    summary. The exception is named in the verdict and its traceback logged, so
    nothing is swallowed.
    """
    try:
        return audit_with_retries(shlex.split(npm), attempts, retry_delay_seconds(), run=_run_npm_audit)
    except Exception as exc:  # noqa: BLE001 -- reported below as UNAVAILABLE, exit 2
        _emit(traceback.format_exc(), err=True)
        reason = f"the gate itself failed ({type(exc).__name__}: {exc})"
        return Outcome(Verdict(UNAVAILABLE, reason=reason), attempts, "")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    attempts = max_attempts()
    outcome = _audit_or_could_not_check(args.npm, attempts)
    _write_report(args.report, outcome.report)
    _write_summary(summary_lines(outcome, attempts))
    _announce(outcome, attempts)
    return EXIT_CODES[outcome.verdict.result]


if __name__ == "__main__":
    sys.exit(main())
