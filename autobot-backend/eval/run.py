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
import os
from pathlib import Path

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from eval.candidates import baseline_candidate, recorded_replay_candidate
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
    parser.add_argument(
        "--recorded-dir",
        default="",
        help="Directory of recorded runs to replay against (defaults to eval/recorded/).",
    )
    parser.add_argument(
        "--require-real-candidate",
        action="store_true",
        help=(
            "Exit 1 if the run fell through to the self-consistency baseline. "
            "CI passes this so a comparison of the goldens with themselves cannot "
            "be reported as a pass (#16157)."
        ),
    )
    return parser.parse_args()


def resolve_candidate(recorded_dir: Path) -> tuple[CandidateRunner, bool]:
    """Pick the candidate to replay against, and say whether it is a real one.

    Returns ``(candidate, is_real)``. ``is_real`` is False only for the
    self-consistency baseline, which compares each golden with itself and
    therefore cannot fail. Callers use it to refuse to call that a pass.
    """
    if recorded_dir.is_dir() and any(recorded_dir.glob("*.json")):
        return recorded_replay_candidate(recorded_dir), True
    return baseline_candidate, False


def _resolve_output_path(json_path: str) -> Path | None:
    """Resolve ``--json`` within the allowed output dir, refusing escapes (#11062).

    An operator-supplied path could otherwise write outside the working tree
    (``--json /etc/x`` or ``../../x``). Allowed root is ``EVAL_OUTPUT_DIR`` or the
    current working directory. Returns the resolved path, or None if it escapes.
    """
    allowed = Path(os.environ.get("EVAL_OUTPUT_DIR", str(Path.cwd()))).resolve()
    resolved = Path(json_path).resolve()
    if resolved != allowed and allowed not in resolved.parents:
        logger.error("Refusing to write JSON report outside %s: %s (#11062)", allowed, resolved)
        return None
    return resolved


def _emit(report: RegressionReport, json_path: str) -> None:
    """Print the markdown report and optionally write JSON."""
    logger.info("%s", report.render_markdown())
    if json_path:
        resolved = _resolve_output_path(json_path)
        if resolved is None:
            return
        with open(resolved, "w", encoding="utf-8") as handle:
            json.dump(report.to_dict(), handle, indent=2)
        logger.info("Wrote JSON report to %s", resolved)


def main() -> int:
    """CLI entrypoint. Returns the process exit code."""
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    recorded_dir = Path(args.recorded_dir) if args.recorded_dir else Path(__file__).parent / "recorded"
    candidate, is_real = resolve_candidate(recorded_dir)
    report = run_or_schedule(run_eval(candidate=candidate, epsilon=args.epsilon))
    _emit(report, args.json)

    if not is_real:
        # The baseline candidate replays each golden's own recorded outcome, so
        # every comparison is a file against itself and no input can make it
        # red. Saying so is the point: a green here otherwise reads as drift
        # detection to anyone who did not open candidates.py (#16157).
        logger.warning(
            "UNMEASURED: no recorded runs in %s, so this replay compared each golden "
            "with itself. It cannot detect drift and its result asserts nothing.",
            recorded_dir,
        )
        if args.require_real_candidate:
            return 1

    if args.fail_on_regression and report.has_regressions:
        logger.error("Regressions detected — failing (gated mode).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
