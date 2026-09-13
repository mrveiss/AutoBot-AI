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
* Each invocation's collected count must clear ``--min-collected`` — judged per
  invocation, never on the sum. A union floor is satisfied by whichever
  invocation still works, so a selection that silently stopped matching anything
  stays invisible for as long as its sibling keeps collecting. That is the exact
  shape that left an earlier sweep in this repository blind to ~44% of the tests
  it claimed to cover, and it is why ``--min-collected slm=0`` has to be written
  down rather than absorbed by the backend count.
* Each invocation's passed count must clear ``--min-passed``, so a collapse from
  today's baseline is caught rather than merely being visible in a log nobody opens.

It intentionally does NOT decide whether the run passed — pytest's own exit
status still governs that. This adds the one verdict pytest cannot give: "the
selection still matches the tests it is supposed to match."
"""

# NOTE: deliberately NO ``from __future__ import annotations`` here.
#
# On Python 3.14, ``@dataclass`` resolves *string* annotations by looking its own
# module up in ``sys.modules`` (``dataclasses._is_type`` ->
# ``sys.modules.get(cls.__module__).__dict__``). The future import turns every
# annotation into a string, so a module executed WITHOUT a ``sys.modules`` entry —
# which is how this repo's guard tests load their subject, to avoid tripping the
# sys.modules leak guard — dies at class-creation time with
# ``AttributeError: 'NoneType' object has no attribute '__dict__'``.
#
# Real annotations cost nothing here and keep the module loadable by any loader.

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


def _floor_cell(floors: "Floors", name: str) -> str:
    """The floor this invocation is judged against, marked when declared for it."""
    floor = floors.for_report(name)
    return f"{floor} (declared)" if floors.is_explicit(name) else str(floor)


def render(
    per_report: dict[str, Counts],
    total: Counts,
    marker_expression: str,
    min_collected: "Floors",
    min_passed: "Floors",
) -> str:
    """Build the markdown block shown on the run page and in the log."""
    lines = [
        "## Marker-excluded suite coverage",
        "",
        f"Selection: `{marker_expression}`",
        "",
        "| Invocation | Collected | Executed | Passed | Failed | Errors | Skipped | Collected floor | Passed floor |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, counts in per_report.items():
        lines.append(
            f"| {name} | {counts.collected} | {counts.executed} | {counts.passed} "
            f"| {counts.failures} | {counts.errors} | {counts.skipped} "
            f"| {_floor_cell(min_collected, name)} | {_floor_cell(min_passed, name)} |"
        )
    lines.append(
        f"| **total** | **{total.collected}** | **{total.executed}** | **{total.passed}** "
        f"| **{total.failures}** | **{total.errors}** | **{total.skipped}** | | |"
    )
    lines.append("")
    lines.append(
        "A skip here means the test was not exercised — usually an absent live service. "
        "It is a real outcome, not a pass: read the count."
    )
    lines.append("")
    lines.append(
        "Floors are judged per invocation, never on the total: a union floor is satisfied "
        "by whichever invocation still works, which is how a sweep stays blind to a sibling "
        "that has silently stopped matching anything."
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


class Floors:
    """Per-invocation floors, with a default for invocations not named."""

    def __init__(self, default: int, overrides: dict[str, int]):
        self.default = default
        self.overrides = overrides

    def for_report(self, name: str) -> int:
        return self.overrides.get(name, self.default)

    def is_explicit(self, name: str) -> bool:
        return name in self.overrides


def parse_floor(values: list[str], option: str) -> Floors:
    """Read repeated ``N`` / ``NAME=N`` values into a :class:`Floors`.

    A bare ``N`` is the floor applied to EVERY invocation separately — never to
    their sum. ``NAME=N`` overrides one invocation, and is the ONLY way to
    declare a floor of 0, so "this one legitimately collects nothing" has to be
    written down rather than absorbed by a sibling's count.
    """
    default: int | None = None
    overrides: dict[str, int] = {}
    for value in values:
        name, _, raw = value.partition("=")
        if not raw:
            default = int(name)
        else:
            overrides[name] = int(raw)
    if default is None:
        raise ReportError(f"{option} needs a bare default in addition to any NAME=N override")
    if default < 1:
        raise ReportError(f"{option} default must be at least 1: a floor of 0 is not a presence assertion")
    for name, floor in overrides.items():
        if floor < 0:
            raise ReportError(f"{option} {name}={floor} is negative")
    return Floors(default, overrides)


def check(per_report: dict[str, Counts], min_collected: Floors, min_passed: Floors) -> list[str]:
    """Return every floor violation, judged PER INVOCATION.

    Deliberately not judged on the sum. A union floor is satisfied by whichever
    invocation still works, so an invocation whose selection silently stopped
    matching anything is invisible for exactly as long as its sibling keeps
    collecting — the shape that made a sweep in this repository blind to ~44% of
    the tests it claimed to cover. Each invocation clears its own floor or the
    run goes red naming that invocation.
    """
    problems: list[str] = []
    for name, counts in sorted(per_report.items()):
        floor = min_collected.for_report(name)
        if counts.collected < floor:
            problems.append(
                f"{name}: collected {counts.collected} test(s), below its floor of {floor}. "
                f"That invocation is selecting nothing — a broken selection, not a clean run."
            )
        floor = min_passed.for_report(name)
        if counts.passed < floor:
            problems.append(
                f"{name}: {counts.passed} test(s) passed, below its floor of {floor}. "
                f"Marker-carrying tests that used to run no longer do; find out which before lowering this floor."
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", help="JUnit XML files, as NAME=PATH or PATH")
    parser.add_argument(
        "--min-collected",
        action="append",
        default=[],
        metavar="N|NAME=N",
        help=(
            "floor on tests collected, applied to EACH invocation separately. A bare N is "
            "the default for every invocation; NAME=N overrides one and is the only way to "
            "declare a floor of 0. Default: 1"
        ),
    )
    parser.add_argument(
        "--min-passed",
        action="append",
        default=[],
        metavar="N|NAME=N",
        help="floor on tests passed, applied to EACH invocation separately. Same syntax. Default: 1",
    )
    parser.add_argument("--marker-expression", default=os.environ.get("MARKER_EXPRESSION", "(unset)"))
    args = parser.parse_args(argv)

    try:
        min_collected = parse_floor(args.min_collected or ["1"], "--min-collected")
        min_passed = parse_floor(args.min_passed or ["1"], "--min-passed")
    except (ReportError, ValueError) as exc:
        parser.error(str(exc))

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

    _emit_summary(render(per_report, total, args.marker_expression, min_collected, min_passed))

    declared = set(min_collected.overrides) | set(min_passed.overrides)
    unknown = sorted(declared - set(per_report))
    if unknown:
        print(  # noqa: print
            f"::error::marker-suite report: floor declared for unknown invocation(s) {unknown}; "
            "a floor that names nothing is a floor that checks nothing",
            file=sys.stderr,
        )
        return 1

    problems = check(per_report, min_collected, min_passed)
    for problem in problems:
        print(f"::error::marker-suite report: {problem}", file=sys.stderr)  # noqa: print
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
