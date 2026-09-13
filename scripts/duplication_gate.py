#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Gate a jscpd run on its absolute duplicated-line count (#16319).

`duplication-guard.yml` runs jscpd over each scope and tees the console report to
a log. This reads the report's Total row and compares its duplicated lines with
the scope's pin.

The guard used to pin jscpd's *percentage* instead, and a percentage fails a PR
that deletes unique code. #16308 kept the same 135 clones and 4,729 duplicated
lines, but it scanned 4.5k fewer lines, so the ratio moved from 1.82% to 1.85%.
That put it over a pin set one hundredth above the measured value. The rule is
"no new duplication", so the count is what gets pinned.

Usage:

    python3 scripts/duplication_gate.py LOG PIN

Exit codes:
- 0: the duplicated lines are at or under PIN.
- 1: they are over PIN, or PIN is still UNMEASURED.
- 2: the log carries no readable Total row, or PIN is not a line count.

Every branch prints the figures it measured, and none prints a guessed one.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

UNMEASURED = "UNMEASURED"

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_BOX = "│"


class Totals(NamedTuple):
    """The figures on jscpd's Total row that the gate reports."""

    files: int
    lines: int
    clones: int
    duplicated_lines: int


def _number(field: str) -> int:
    digits = "".join(character for character in field if character.isdigit())
    if not digits:
        raise ValueError(f"no number in jscpd field {field!r}")
    return int(digits)


def parse_totals(text: str) -> Totals:
    """Read the last Total row of a jscpd console report.

    jscpd draws its table with U+2502 wrapped in ANSI colour, so real output has
    no ASCII pipe (#16163). After normalising, the row reads
    ``| Total: | files | lines | tokens | clones | duplicated (percent) |``.
    """
    flat = _ANSI.sub("", text).replace(_BOX, "|")
    rows = [line for line in flat.splitlines() if "Total:" in line and line.count("|") >= 7]
    if not rows:
        raise ValueError("no jscpd Total row in the log")
    fields = rows[-1].split("|")
    return Totals(
        files=_number(fields[2]),
        lines=_number(fields[3]),
        clones=_number(fields[5]),
        duplicated_lines=_number(fields[6].split("(")[0]),
    )


def gate(totals: Totals, pin: str) -> tuple[int, list[str]]:
    """Return the exit code and the report lines for *totals* against *pin*."""
    report = [
        f"measured:  {totals.duplicated_lines} duplicated lines "
        f"({totals.clones} clones, {totals.lines} lines scanned in {totals.files} files)"
    ]
    if pin == UNMEASURED:
        report.append(f"pin:       {UNMEASURED}: pin it to {totals.duplicated_lines}, the figure above")
        return 1, report
    if not pin.isdigit():
        report.append(f"pin:       {pin!r} is not a count of duplicated lines")
        return 2, report
    over = totals.duplicated_lines - int(pin)
    report.append(f"pin:       {pin} duplicated lines")
    if over > 0:
        report.append(f"OVER BY:   {over} lines")
        return 1, report
    if over < 0:
        report.append(
            f"under the pin by {-over} lines: lower it to {totals.duplicated_lines} to keep the ratchet tight"
        )
    return 0, report


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    log, pin = Path(argv[0]), argv[1]
    try:
        totals = parse_totals(log.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        print(f"could not read jscpd totals from {log}: {exc}. Reporting no figure rather than a guessed one.")
        return 2
    code, report = gate(totals, pin)
    print("\n".join(report))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
