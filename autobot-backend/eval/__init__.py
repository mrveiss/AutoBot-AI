# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Trajectory-level eval & regression harness (GH#10546).

A golden-trajectory harness that records canonical task runs (input +
expected tool sequence + final outcome), replays them against a candidate
model/prompt/skill set, and scores drift with the RLM evaluator
(``rlm/evaluator.py``) plus deterministic checks.  Emits a per-task-class
regression/improvement report so a model or prompt change that silently
makes the agent worse is caught before it ships.

Reuse:
- ``rlm.evaluator.ResponseQualityEvaluator`` — the response scorer.
- ``llc`` replay fixture shape (``inputs`` / ``expected_output`` /
  ``recorded_events``) — golden trajectories are the same on-disk format,
  extended with ``task_class`` + ``expected_tools`` + ``baseline_score``.
"""

from eval.report import RegressionReport, TaskClassDelta, TrajectoryOutcome
from eval.store import GoldenTrajectory, load_golden_set

__all__ = [
    "GoldenTrajectory",
    "RegressionReport",
    "TaskClassDelta",
    "TrajectoryOutcome",
    "load_golden_set",
]
