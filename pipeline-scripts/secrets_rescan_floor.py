#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fail a detect-secrets rescan that read less than the committed baseline holds (#16275).

The ``secret-detection`` job in ``security.yml`` rescans every tracked file and
fails on any finding the committed ``.secrets.baseline`` does not hold as
audited. That comparison is one-sided. A rescan that reads NOTHING -- a filter
in the baseline's own settings widened to match every file, a plugin set that
matches nothing, an empty file list -- yields no findings, so no finding is new,
and the step would pass. That is #16275's own failure mode, a scanner reporting
clean on what it never read, one layer further in.

So the rescan's count is asserted, not only printed:

* it must not be zero while the committed baseline holds findings;
* it must not fall below :data:`FLOOR`;
* the committed baseline must not fall below :data:`FLOOR` either, so removing
  audited entries is a deliberate line in a diff that lowers the floor.

Only counts are printed -- never a path, a hash or a value.

Usage::

    python3 pipeline-scripts/secrets_rescan_floor.py \\
        --rescanned .secrets.baseline --committed COMMITTED_COPY.json

Exit 0 when the rescan read enough, 1 when it did not. An unreadable or
malformed baseline raises, so it can never read as zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

#: Measured 2026-09-11: the committed baseline held 1,331 findings in 284 files,
#: written by detect-secrets 1.5.0 over every tracked file. The floor sits 31
#: below, so a rescan that loses more than that is a narrowed scan, not a cleaner
#: tree. Lower it only in the change that removes baseline entries; raise it as
#: audited entries accumulate. repo_tests/no_tracked_key_material_test.py holds it
#: at or under the committed count and within a fixed headroom of it.
FLOOR = 1_300


def count_findings(baseline: object) -> int:
    """Findings in a parsed detect-secrets baseline. Anything malformed raises."""
    results = baseline.get("results") if isinstance(baseline, dict) else None
    if not isinstance(results, dict):
        raise ValueError("not a detect-secrets baseline: no 'results' mapping")
    if not all(isinstance(entries, list) for entries in results.values()):
        raise ValueError("not a detect-secrets baseline: a 'results' entry is not a list")
    return sum(len(entries) for entries in results.values())


def floor_problems(rescanned: int, committed: int, floor: int = FLOOR) -> list[str]:
    """Every way the rescan read too little. An empty list means it read enough."""
    problems = []
    if rescanned == 0 and committed > 0:
        problems.append(
            f"the rescan read 0 findings while the committed baseline holds {committed}"
            " -- a scan that read nothing, not a clean tree"
        )
    if rescanned < floor:
        problems.append(
            f"the rescan read {rescanned} findings, below the floor of {floor}"
            " -- a narrowed scan, not a cleaner tree"
        )
    if committed < floor:
        problems.append(
            f"the committed baseline holds {committed} findings, below the floor of {floor}"
            " -- lower FLOOR in the change that removes entries"
        )
    return problems


def _load(path: Path) -> object:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail a detect-secrets rescan that read too little.")
    parser.add_argument("--rescanned", type=Path, required=True, help="the baseline the rescan rewrote")
    parser.add_argument("--committed", type=Path, required=True, help="a copy of the committed baseline")
    args = parser.parse_args(argv)
    rescanned = count_findings(_load(args.rescanned))
    committed = count_findings(_load(args.committed))
    summary = f"detect-secrets rescan read {rescanned} finding(s); committed baseline holds {committed}; floor {FLOOR}"
    print(summary)  # noqa: print
    problems = floor_problems(rescanned, committed)
    for problem in problems:
        print(f"::error::{problem}")  # noqa: print
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
