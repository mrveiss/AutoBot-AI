#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Report how many marker-carrying tests actually ran, and fail if none did (#14930).

`.github/workflows/marker-tests.yml` runs the complement of the PR gate's
exclusion — `integration or slow or distributed or performance`. Until this
script existed the workflow's only signal was pytest's exit code, and its two
steps ended in ``|| [ $? -eq 5 ]``: exit 5 is "no tests collected", which was
swallowed as a legitimate outcome. That is the exact shape this repository has
been bitten by repeatedly — **an empty result reading as a clean result**. A
run in which the marker selection silently stopped matching anything was
indistinguishable, from the outside, from a run in which everything passed.

So this script asserts PRESENCE rather than absence of failure:

* Every report file it is told to expect must exist. A missing file is a hard
  failure, never "nothing to check" — a pytest that died before writing its XML
  is precisely the case that must not read as clean.
* The aggregate collected count must clear ``--min-collected`` (at least 1).
* The passed count must clear ``--min-passed``, so a collapse from today's
  baseline is caught rather than merely being visible in a log nobody opens.

It intentionally does NOT decide whether the run passed — pytest's own exit
status still governs that. This adds the one verdict pytest cannot give: "the
selection still matches the tests it is supposed to match."
"""

from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# The names pytest writes on <testsuite>. Kept as a constant so a pytest change
# that renames one surfaces as a parse failure rather than a silent zero.
_REQUIRED_ATTRS = ("tests", "failures", "errors", "skipped")


@dataclass(frozen=True)
class Counts:
    """One invocation's outcome, as pytest's JUnit XML reports it."""

    collected: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0

    @property
    def passed(self) -> int:
        return self.collected - self.failures - self.errors - self.skipped

    @property
    def executed(self) -> int:
        """Tests that ran a body — everything collected that was not skipped."""
        return self.collected - self.skipped

    def __add__(self, other: "Counts") -> "Counts":
        return Counts(
            collected=self.collected + other.collected,
            failures=self.failures + other.failures,
            errors=self.errors + other.errors,
            skipped=self.skipped + other.skipped,
        )


class ReportError(RuntimeError):
    """A report could not be read or understood. Never downgraded to zero."""


def parse_report(path: Path) -> Counts:
    """Read one JUnit XML file into :class:`Counts`.

    Raises rather than returning zeros for a missing or malformed file. A parse
    failure that returned ``Counts()`` would be reported as "collected nothing",
    which is a different — and much more alarming — claim than "could not read
    the report", and the two must not be confused.
    """
    if not path.exists():
        raise ReportError(
            f"expected JUnit report {path} does not exist — pytest did not reach the end of the run. "
            f"This is a failure, not an empty result."
        )

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ReportError(f"{path} is not parseable JUnit XML: {exc}") from exc

    suites = list(root.iter("testsuite"))
    if not suites:
        raise ReportError(f"{path} contains no <testsuite> element")

    total = Counts()
    for suite in suites:
        missing = [attr for attr in _REQUIRED_ATTRS if attr not in suite.attrib]
        if missing:
            raise ReportError(f"{path}: <testsuite> is missing attribute(s) {missing}; cannot count reliably")
        total = total + Counts(
            collected=int(suite.attrib["tests"]),
            failures=int(suite.attrib["failures"]),
            errors=int(suite.attrib["errors"]),
            skipped=int(suite.attrib["skipped"]),
        )
    return total


def render(per_report: dict[str, Counts], total: Counts, marker_expression: str) -> str:
    """Build the markdown block shown on the run page and in the log."""
    lines = [
        "## Marker-excluded suite coverage",
        "",
        f"Selection: `{marker_expression}`",
        "",
        "| Invocation | Collected | Executed | Passed | Failed | Errors | Skipped |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, counts in per_report.items():
        lines.append(
            f"| {name} | {counts.collected} | {counts.executed} | {counts.passed} "
            f"| {counts.failures} | {counts.errors} | {counts.skipped} |"
        )
    lines.append(
        f"| **total** | **{total.collected}** | **{total.executed}** | **{total.passed}** "
        f"| **{total.failures}** | **{total.errors}** | **{total.skipped}** |"
    )
    lines.append("")
    lines.append(
        "A skip here means the test was not exercised — usually an absent live service. "
        "It is a real outcome, not a pass: read the count."
    )
    return "\n".join(lines)


def _emit_summary(text: str) -> None:
    """Print, and append to the GitHub step summary when running in Actions."""
    print(text)  # noqa: print
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def check(per_report: dict[str, Counts], min_collected: int, min_passed: int) -> list[str]:
    """Return every floor violation. An empty list means the floors held."""
    total = Counts()
    for counts in per_report.values():
        total = total + counts

    problems: list[str] = []
    if total.collected < min_collected:
        problems.append(
            f"the marker selection collected {total.collected} test(s), below the floor of {min_collected}. "
            f"The suite is selecting nothing — that is a broken selection, not a clean run."
        )
    if total.passed < min_passed:
        problems.append(
            f"{total.passed} test(s) passed, below the floor of {min_passed}. "
            f"Marker-carrying tests that used to run no longer do; find out which before lowering this floor."
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", help="JUnit XML files, as NAME=PATH or PATH")
    parser.add_argument(
        "--min-collected",
        type=int,
        default=1,
        help="fail when fewer than this many tests were collected in total (default: 1)",
    )
    parser.add_argument(
        "--min-passed",
        type=int,
        default=1,
        help="fail when fewer than this many tests passed in total (default: 1)",
    )
    parser.add_argument("--marker-expression", default=os.environ.get("MARKER_EXPRESSION", "(unset)"))
    args = parser.parse_args(argv)

    if args.min_collected < 1:
        parser.error("--min-collected must be at least 1: a floor of 0 is not a presence assertion")

    per_report: dict[str, Counts] = {}
    for entry in args.reports:
        name, _, raw_path = entry.partition("=")
        if not raw_path:
            name, raw_path = Path(entry).stem, entry
        try:
            per_report[name] = parse_report(Path(raw_path))
        except ReportError as exc:
            print(f"::error::marker-suite report: {exc}", file=sys.stderr)  # noqa: print
            return 1

    total = Counts()
    for counts in per_report.values():
        total = total + counts

    _emit_summary(render(per_report, total, args.marker_expression))

    problems = check(per_report, args.min_collected, args.min_passed)
    for problem in problems:
        print(f"::error::marker-suite report: {problem}", file=sys.stderr)  # noqa: print
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
