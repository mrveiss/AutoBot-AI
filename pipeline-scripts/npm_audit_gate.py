# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Gate the frontend dependency audit on ONE ``npm audit --json`` report (#16337).

The Security Scan job used to call npm's audit service twice: ``npm audit
--json`` for the artifact, then ``npm audit --audit-level=high`` as the gate.
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
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
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

PASSED, FOUND, UNAVAILABLE = "passed", "found", "unavailable"
EXIT_CODES = {PASSED: 0, FOUND: 1, UNAVAILABLE: 2}
ANNOTATION_TITLES = {FOUND: "npm audit: advisories found", UNAVAILABLE: "npm audit: could not check"}


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


def _counts(vulnerabilities: dict) -> dict[str, int]:
    return {
        key: value if isinstance(value, int) else 0
        for key, value in ((key, vulnerabilities.get(key, 0)) for key in SEVERITY_ORDER)
    }


def classify(stdout: str, log: str = "") -> Verdict:
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
    result = FOUND if any(counts[severity] for severity in FAILING_SEVERITIES) else PASSED
    return Verdict(result, counts=counts, endpoint=endpoint)


Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def _run_npm_audit(command: list[str]) -> subprocess.CompletedProcess[str]:
    """One network call. ``--loglevel=http`` puts the endpoint npm used in stderr."""
    argv = [*command, "audit", "--json", "--loglevel=http"]
    return subprocess.run(argv, capture_output=True, text=True, check=False, timeout=timeout_seconds())


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
    verdict = outcome.verdict
    if verdict.result == PASSED:
        return "**Passed:** no high or critical advisories in autobot-frontend."
    if verdict.result == FOUND:
        return (
            f"**Failed, advisories found:** {verdict.counts['critical']} critical and "
            f"{verdict.counts['high']} high. Bump the dependency; do not silence the gate (#13400)."
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
    title = ANNOTATION_TITLES.get(outcome.verdict.result)
    headline = _headline(outcome, attempts).replace("**", "")
    _emit(f"::error title={title}::{headline}" if title else headline)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--npm", default="npm", help='npm command to run, e.g. "npx --yes npm@11.19.1"')
    parser.add_argument("--report", default="audit-results.json", help="where the raw report is written")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    attempts = max_attempts()
    outcome = audit_with_retries(shlex.split(args.npm), attempts, retry_delay_seconds(), run=_run_npm_audit)
    Path(args.report).write_text(outcome.report, encoding="utf-8")
    _write_summary(summary_lines(outcome, attempts))
    _announce(outcome, attempts)
    return EXIT_CODES[outcome.verdict.result]


if __name__ == "__main__":
    sys.exit(main())
