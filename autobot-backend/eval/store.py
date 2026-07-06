# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Golden-trajectory store (GH#10546).

A golden trajectory is one canonical task run captured for regression
testing.  On disk it is the LLC replay fixture shape (see
``llc/services/replay_service.py::export_fixture``) with three eval-specific
fields added:

- ``task_class``     — grouping key for the report (e.g. "code_fix").
- ``expected_tools`` — ordered tool names the run is expected to call.
- ``baseline_score`` — the RLM quality score of the recorded canonical run,
  used as the comparison point for drift.

Seed goldens live under ``eval/golden/*.json``.  Keeping the fixture shape
means a real recorded run (from the replay export endpoint) can be dropped
in as a golden with only these three keys added — no new format invented.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

GOLDEN_DIR = Path(__file__).parent / "golden"

FIXTURE_VERSION = "1"


@dataclass
class GoldenTrajectory:
    """One recorded canonical task run used as a regression baseline."""

    trajectory_id: str
    task_class: str
    inputs: Dict[str, Any]
    expected_tools: List[str]
    baseline_score: float
    expected_status: str = "completed"
    expected_output_excerpt: str = ""
    agent_config: Dict[str, Any] = field(default_factory=dict)

    @property
    def query(self) -> str:
        """Best-effort user query text from the recorded inputs."""
        for key in ("prompt", "query", "message", "task", "input"):
            val = self.inputs.get(key)
            if isinstance(val, str) and val.strip():
                return val
        return json.dumps(self.inputs, sort_keys=True)

    @classmethod
    def from_fixture(cls, data: Dict[str, Any]) -> "GoldenTrajectory":
        """Build a golden from a replay-fixture-shaped dict."""
        expected = data.get("expected_output") or {}
        return cls(
            trajectory_id=str(data.get("trajectory_id") or data.get("run_id") or "unknown"),
            task_class=str(data.get("task_class") or "uncategorized"),
            inputs=dict(data.get("inputs") or {}),
            expected_tools=list(data.get("expected_tools") or []),
            baseline_score=float(data.get("baseline_score", 0.0)),
            expected_status=str(expected.get("final_status") or "completed"),
            expected_output_excerpt=str(expected.get("output_text_excerpt") or ""),
            agent_config=dict(data.get("agent_config") or {}),
        )


def load_golden_set(directory: Path | None = None) -> List[GoldenTrajectory]:
    """Load every ``*.json`` golden trajectory from *directory*.

    Args:
        directory: Folder to scan; defaults to ``eval/golden/``.

    Returns:
        Golden trajectories sorted by ``trajectory_id`` for stable ordering.
    """
    root = directory or GOLDEN_DIR
    goldens: List[GoldenTrajectory] = []
    for path in sorted(root.glob("*.json")):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        goldens.append(GoldenTrajectory.from_fixture(data))
    logger.info("Loaded %d golden trajectories from %s", len(goldens), root)
    return goldens
