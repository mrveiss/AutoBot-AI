#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Project the shard balance that a stored-durations file will produce.

#10691: ``python-suite`` is split six ways with ``pytest-split``. The split is
only as good as the ``.test_durations`` file behind it -- with no durations
every test is assumed to cost the same and the split collapses to equal test
*counts*, which for this suite is badly unbalanced. A six-way split is worth
nothing if one shard carries half the wall clock, so the balance needs to be
visible *before* a run rather than inferred afterwards from six job timings.

This reimplements pytest-split's default ``duration_based_chunks`` algorithm:
walk the collected tests in order, cutting to the next group each time the
current group's accumulated time reaches ``total / splits``. Each shard runs
every invocation, so a shard's projected cost is the sum of its group across
all durations files passed.

Known approximation: the real algorithm runs over pytest's *collection* order,
which this script does not have -- it sorts node IDs instead. That matches
collection at file granularity (pytest walks directories sorted) but not within
a file (pytest uses definition order). Chunk boundaries are coarse relative to
a single test, so the effect on the projection is negligible.

Note the ``[pytest-split] Running group N/M (estimated duration: ...)`` banner
is NOT available as a cross-check under ``-n auto``: xdist collects in the
workers, so pytest-split's deselection -- and that banner -- happen there and
the worker output is suppressed. Verified against a real run: only the
controller-side "No test durations found" notice reaches the job log. The
authoritative per-shard figures are therefore the reported test counts and the
step wall-clock.

Usage:
    summarize_test_durations.py [--splits N] .test_durations [.test_durations_slm ...]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# pytest-split assigns this to any collected test absent from the durations
# file, so a file that has drifted degrades gradually instead of breaking.
_UNKNOWN_TEST_COST = "mean of known durations"


def load_durations(path: Path) -> dict[str, float]:
    """Read one pytest-split durations file."""
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    # pytest-split wrote a list-of-lists before v0.4; accept both.
    if isinstance(data, list):
        data = dict(data)
    return {str(k): float(v) for k, v in data.items()}


def chunk_by_duration(
    durations: dict[str, float], splits: int
) -> list[tuple[int, float]]:
    """Replicate pytest-split's ``duration_based_chunks`` grouping.

    Returns one ``(test_count, seconds)`` pair per group.
    """
    ordered = [durations[name] for name in sorted(durations)]
    if not ordered:
        return [(0, 0.0)] * splits

    time_per_group = sum(ordered) / splits
    counts = [0] * splits
    totals = [0.0] * splits

    group_idx = 0
    for cost in ordered:
        # The real algorithm advances *before* placing, so the final group
        # absorbs any remainder. Mirror that exactly.
        if totals[group_idx] >= time_per_group and group_idx < splits - 1:
            group_idx += 1
        counts[group_idx] += 1
        totals[group_idx] += cost

    return list(zip(counts, totals))


def _format_invocation(path: Path, groups: list[tuple[int, float]]) -> list[str]:
    """Render the per-group table for a single pytest invocation."""
    total = sum(seconds for _, seconds in groups)
    lines = [
        "",
        f"### `{path.name}` — {sum(c for c, _ in groups)} tests, {total / 60:.1f} min total",
        "",
        "| group | tests | projected |",
        "| --- | --- | --- |",
    ]
    lines += [
        f"| {idx} | {count} | {seconds / 60:.1f} min |"
        for idx, (count, seconds) in enumerate(groups, start=1)
    ]
    return lines


def _format_shards(shard_totals: list[float], splits: int) -> list[str]:
    """Render the combined per-shard projection and the balance verdict."""
    slowest, fastest = max(shard_totals), min(shard_totals)
    baseline = sum(shard_totals)
    lines = [
        "",
        "### Projected shard cost, summed serial test time (all invocations)",
        "",
        "| shard | projected | vs slowest |",
        "| --- | --- | --- |",
    ]
    lines += [
        f"| {idx} | {total / 60:.1f} min | {total / slowest * 100:.0f}% |"
        for idx, total in enumerate(shard_totals, start=1)
    ]
    spread = (slowest / fastest) if fastest else float("inf")
    lines += [
        "",
        "> Sums of per-test durations, i.e. serial test time -- NOT wall clock.",
        "> Each shard also runs `-n auto`, so its real wall clock is roughly",
        "> this figure divided by the runner's worker count, plus fixed job",
        "> overhead. The ratios below are unaffected by that division.",
        "",
        f"- unsharded total: **{baseline / 60:.1f} min**",
        f"- slowest shard: **{slowest / 60:.1f} min** "
        f"(effective speed-up **{baseline / slowest:.1f}x** of a theoretical {splits}x)",
        f"- imbalance (slowest / fastest): **{spread:.2f}x**",
        f"- tests with no stored duration are charged the {_UNKNOWN_TEST_COST}",
    ]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits", type=int, default=6)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    report = ["## Test duration split projection"]
    shard_totals = [0.0] * args.splits

    for path in args.paths:
        if not path.exists():
            report.append(f"\n> missing durations file: `{path.name}`")
            continue
        groups = chunk_by_duration(load_durations(path), args.splits)
        report += _format_invocation(path, groups)
        for idx, (_, seconds) in enumerate(groups):
            shard_totals[idx] += seconds

    report += _format_shards(shard_totals, args.splits)
    # stdout is this tool's deliverable: the caller redirects it into
    # $GITHUB_STEP_SUMMARY. A logger would send it to the wrong place.
    print("\n".join(report))  # noqa: print
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
