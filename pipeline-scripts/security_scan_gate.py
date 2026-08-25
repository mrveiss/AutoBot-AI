#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Turn a security scanner's report into a job verdict and a job summary (#13543).

Every scanner in `.github/workflows/security.yml` ended in `|| true`, so
`Dependency Security Scan` and `Static Application Security Testing (SAST)` could
go red only on checkout, toolchain setup or dependency install. A green tick said
nothing at all about security, while the job names claimed a substantive control.

This script is the missing half. It reads what a scanner wrote and decides:

* a report that is absent or unparseable is a HARD FAILURE, never zero findings.
  A scanner that died before writing its output is precisely the case that must
  not read as clean — the same rule `marker_suite_report.py` follows (#14930);
* findings at or above ``--fail-on`` beyond ``--allowed`` fail the step;
* every run writes a severity table to ``$GITHUB_STEP_SUMMARY``, so the counts
  are readable from the checks tab without downloading an artifact.

``--fail-on never`` exists for a scanner whose backlog is too large to gate on
today. It is deliberately loud: the summary says in words that the step does not
gate, so nobody reads its green as a verdict. Silence there is how a name comes
to overclaim.
"""

# NOTE: deliberately NO ``from __future__ import annotations`` here, for the same
# reason marker_suite_report.py documents. ``@dataclass`` resolves *string*
# annotations by looking its own module up in ``sys.modules``; a module executed
# WITHOUT a ``sys.modules`` entry — which is how this directory's guard tests load
# their subject, to avoid tripping the sys.modules leak guard (#13337) — then dies
# at class-creation time with ``AttributeError: 'NoneType' object has no
# attribute '__dict__'``. Real annotations cost nothing and keep it loadable.

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Most severe first. "unknown" is last and is still a finding: a scanner that
# reports no severity (pip-audit, flake8) must not be gated into invisibility.
SEVERITIES = ("critical", "high", "medium", "low", "unknown")

_FLAKE8_LINE = re.compile(r"^(?P<location>[^:]+:\d+:\d+):\s+(?P<code>[A-Z]+\d+)\s")


class ReportError(RuntimeError):
    """A report could not be read or understood. Never downgraded to zero."""


@dataclass(frozen=True)
class Finding:
    severity: str
    identifier: str
    location: str


def _normalise(raw: str) -> str:
    value = (raw or "").strip().lower()
    return value if value in SEVERITIES else "unknown"


def parse_bandit(payload: str) -> list[Finding]:
    """bandit ``-f json``: ``results[]`` with ``issue_severity`` HIGH/MEDIUM/LOW."""
    document = json.loads(payload)
    return [
        Finding(
            severity=_normalise(result.get("issue_severity", "")),
            identifier=str(result.get("test_id", "?")),
            location=f"{result.get('filename', '?')}:{result.get('line_number', '?')}",
        )
        for result in document.get("results", [])
    ]


def parse_pip_audit(payload: str) -> list[Finding]:
    """pip-audit ``--format=json``: one finding per vuln, severity not reported.

    pip-audit carries no severity field, so every finding lands in ``unknown``.
    That is why the workflow gates it with ``--fail-on any``: filtering by a
    severity the tool never emits would silently pass everything.
    """
    document = json.loads(payload)
    dependencies = document.get("dependencies", document if isinstance(document, list) else [])
    return [
        Finding(
            severity="unknown",
            identifier=str(vuln.get("id", "?")),
            location=f"{dependency.get('name', '?')}=={dependency.get('version', '?')}",
        )
        for dependency in dependencies
        for vuln in dependency.get("vulns", [])
    ]


def parse_npm_audit(payload: str) -> list[Finding]:
    """npm ``audit --json`` (npm 7+): the ``vulnerabilities`` map, one per package."""
    document = json.loads(payload)
    return [
        Finding(
            severity=_normalise(entry.get("severity", "")),
            identifier=str(name),
            location=str(entry.get("range", "?")),
        )
        for name, entry in (document.get("vulnerabilities") or {}).items()
    ]


def parse_flake8(payload: str) -> list[Finding]:
    """flake8 default text output: ``path:line:col: CODE message``."""
    findings = []
    for line in payload.splitlines():
        match = _FLAKE8_LINE.match(line.strip())
        if match:
            findings.append(Finding(severity="unknown", identifier=match["code"], location=match["location"]))
    return findings


PARSERS = {
    "bandit": parse_bandit,
    "pip-audit": parse_pip_audit,
    "npm-audit": parse_npm_audit,
    "flake8": parse_flake8,
}


def read_report(path: Path, fmt: str) -> list[Finding]:
    """Parse one report, raising rather than returning an empty list."""
    if not path.exists():
        raise ReportError(
            f"expected {fmt} report {path} does not exist — the scanner did not reach the end of "
            f"its run. That is a failure, not an absence of findings."
        )
    payload = path.read_text(encoding="utf-8")
    if fmt != "flake8" and not payload.strip():
        raise ReportError(f"{fmt} report {path} is empty; a scanner that wrote nothing has not reported 'clean'")
    try:
        return PARSERS[fmt](payload)
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        raise ReportError(f"{path} is not readable as a {fmt} report: {exc}") from exc


def counts_by_severity(findings: list[Finding]) -> dict[str, int]:
    return {severity: sum(1 for f in findings if f.severity == severity) for severity in SEVERITIES}


def at_or_above(findings: list[Finding], threshold: str) -> list[Finding]:
    """Findings the gate judges. ``any`` takes everything; ``never`` takes nothing."""
    if threshold == "never":
        return []
    if threshold == "any":
        return list(findings)
    ceiling = SEVERITIES.index(threshold)
    return [f for f in findings if SEVERITIES.index(f.severity) <= ceiling]


def _verdict_line(threshold: str, judged: int, allowed: int) -> str:
    """One sentence saying what this step's result does and does not mean."""
    if threshold == "never":
        return (
            "**This step does not gate.** Its result is a report only — a green tick here is not "
            "a statement that the tree is clean. See the decision recorded in `security.yml`."
        )
    scope = "any severity" if threshold == "any" else f"severity {threshold} or worse"
    if judged > allowed:
        return f"**FAIL** — {judged} finding(s) at {scope}, above the allowance of {allowed}."
    return f"**PASS** — {judged} finding(s) at {scope}, within the allowance of {allowed}."


def render(title: str, findings: list[Finding], threshold: str, allowed: int, sample: int = 10) -> str:
    """The markdown block written to the run page and the log."""
    counts = counts_by_severity(findings)
    judged = at_or_above(findings, threshold)
    lines = [f"## {title}", "", "| Severity | Findings |", "| --- | ---: |"]
    lines += [f"| {severity} | {counts[severity]} |" for severity in SEVERITIES]
    lines += [f"| **total** | **{len(findings)}** |", ""]
    lines.append(_verdict_line(threshold, len(judged), allowed))
    if judged:
        lines += ["", f"Findings judged by this gate (first {sample}):", ""]
        lines += [f"- `{f.identifier}` [{f.severity}] {f.location}" for f in judged[:sample]]
        if len(judged) > sample:
            lines.append(f"- …and {len(judged) - sample} more; the full report is in the run artifacts.")
    return "\n".join(lines)


def emit(text: str) -> None:
    """Print, and append to the GitHub step summary when running in Actions."""
    print(text)  # noqa: print
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", required=True, choices=sorted(PARSERS), help="report format to parse")
    parser.add_argument("--report", required=True, type=Path, help="path the scanner wrote")
    parser.add_argument("--title", required=True, help="heading for the job-summary block")
    parser.add_argument(
        "--fail-on",
        required=True,
        choices=(*SEVERITIES, "any", "never"),
        help="fail on findings at this severity or worse; 'any' for every finding; 'never' to report only",
    )
    parser.add_argument(
        "--allowed",
        type=int,
        default=0,
        help="measured backlog tolerated at that threshold (default: 0). Raise only with a recorded reason.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.allowed < 0:
        _parser().error("--allowed cannot be negative")

    try:
        findings = read_report(args.report, args.format)
    except ReportError as exc:
        print(f"::error::security scan gate: {exc}", file=sys.stderr)  # noqa: print
        return 1

    emit(render(args.title, findings, args.fail_on, args.allowed))

    judged = at_or_above(findings, args.fail_on)
    if len(judged) > args.allowed:
        print(  # noqa: print
            f"::error::security scan gate: {args.title} — {len(judged)} finding(s) at or above "
            f"'{args.fail_on}', allowance {args.allowed}. Fix the finding; do not re-add '|| true'.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
