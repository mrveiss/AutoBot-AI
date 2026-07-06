# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Eval CLI entrypoint (GH#10546).

Replays N golden trajectories against a candidate and emits a pass/regress
report per task-class.

Usage::

    cd autobot-backend
    python -m eval.run                      # baseline candidate (always runnable)
    python -m eval.run --json report.json   # write machine-readable report
    python -m eval.run --fail-on-regression # exit 1 if any regression (gated mode)

By default this is a NON-BLOCKING signal: it always exits 0 and prints the
report, mirroring how other advisory CI checks are added.  Pass
``--fail-on-regression`` to gate.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from eval.candidates import baseline_candidate
from eval.report import DEFAULT_SCORE_EPSILON, RegressionReport
from eval.runner import CandidateRunner, TrajectoryReplayer
from eval.store import load_golden_set

logger = get_logger(__name__)


async def run_eval(
    candidate: CandidateRunner | None = None,
    golden_dir: Path | None = None,
    epsilon: float = DEFAULT_SCORE_EPSILON,
) -> RegressionReport:
    """Load goldens, replay against *candidate*, return the report.

    Args:
        candidate: Async ``golden -> CandidateResult`` under test; defaults
            to the self-consistency baseline candidate.
        golden_dir: Golden trajectory directory (defaults to eval/golden/).
        epsilon: Score band within which a change counts as unchanged.
    """
    goldens = load_golden_set(golden_dir)
    replayer = TrajectoryReplayer()
    report = await replayer.run(goldens, candidate or baseline_candidate)
    report.epsilon = epsilon
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trajectory-level eval & regression harness")
    parser.add_argument("--json", default="", help="Write machine-readable report to this path")
    parser.add_argument("--epsilon", type=float, default=DEFAULT_SCORE_EPSILON, help="Score noise band")
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit 1 when any regression is found (gated mode). Default: non-blocking (exit 0).",
    )
    return parser.parse_args()


def _emit(report: RegressionReport, json_path: str) -> None:
    """Print the markdown report and optionally write JSON."""
    logger.info("%s", report.render_markdown())
    if json_path:
        with open(json_path, "w", encoding="utf-8") as handle:
            json.dump(report.to_dict(), handle, indent=2)
        logger.info("Wrote JSON report to %s", json_path)


def main() -> int:
    """CLI entrypoint. Returns the process exit code."""
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    report = run_or_schedule(run_eval(epsilon=args.epsilon))
    _emit(report, args.json)

    if args.fail_on_regression and report.has_regressions:
        logger.error("Regressions detected — failing (gated mode).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
