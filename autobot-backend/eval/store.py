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

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from orchestration.success_criteria import SuccessCriteria, SuccessCriteriaType

# #11062: bound the golden loader so a runaway fixture dir cannot OOM/hang the
# harness. Env-tunable; defaults are generous vs the current ~75 goldens.
_MAX_GOLDEN_COUNT = env_int("EVAL_MAX_GOLDEN_COUNT", 1000)
_MAX_GOLDEN_FILE_BYTES = env_int("EVAL_MAX_GOLDEN_FILE_BYTES", 1_000_000)

logger = get_logger(__name__)

GOLDEN_DIR = Path(__file__).parent / "golden"

FIXTURE_VERSION = "2"
#: Fixture versions ``from_fixture`` understands. v1 has no ``tool_match`` or ``success_criteria`` (#20843).
SUPPORTED_FIXTURE_VERSIONS = frozenset({"1", "2"})
#: ``exact``: the tool sequence must equal ``expected_tools`` (v1 behaviour). ``subsequence``: the expected tools
#: must appear in order, other calls may interleave.
TOOL_MATCH_MODES = ("exact", "subsequence")


def _criterion_from_dict(entry: Dict[str, Any]) -> SuccessCriteria:
    """One fixture entry as a ``SuccessCriteria``; ``custom`` is refused (a callable cannot live in JSON)."""
    kind = SuccessCriteriaType(entry["type"])
    if kind is SuccessCriteriaType.CUSTOM:
        raise ValueError("a fixture success criterion cannot be 'custom': a callable is not serialisable")
    return SuccessCriteria(
        criteria_type=kind,
        parameters=dict(entry.get("parameters") or {}),
        weight=float(entry.get("weight", 1.0)),
        required=bool(entry.get("required", True)),
        description=str(entry.get("description", "")),
    )


def _checked_tool_match(data: Dict[str, Any]) -> str:
    """The fixture's ``tool_match``, refusing an unknown mode rather than silently comparing another way."""
    mode = str(data.get("tool_match") or "exact")
    if mode not in TOOL_MATCH_MODES:
        raise ValueError(f"tool_match must be one of {TOOL_MATCH_MODES}, got {mode!r}")
    return mode


def _checked_criteria(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The fixture's ``success_criteria``, validated at load so a bad entry fails the load, not the run."""
    entries = [dict(e) for e in (data.get("success_criteria") or [])]
    for entry in entries:
        _criterion_from_dict(entry)
    return entries


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
    #: v2 (#20843): how ``expected_tools`` is compared, and the typed criteria a live answer must satisfy,
    #: in the ``orchestration.success_criteria`` shape. A v1 fixture carries neither.
    tool_match: str = "exact"
    success_criteria: List[Dict[str, Any]] = field(default_factory=list)
    #: Tools a live run may call beyond ``expected_tools``; anything else fails the run as ``forbidden_tool``.
    #: Empty by default, so a read-only golden allows nothing (#20843).
    allowed_tools: List[str] = field(default_factory=list)

    def criteria(self) -> List[SuccessCriteria]:
        """The ``success_criteria`` entries as evaluator objects."""
        return [_criterion_from_dict(entry) for entry in self.success_criteria]

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
        version = str(data.get("fixture_version") or "1")
        if version not in SUPPORTED_FIXTURE_VERSIONS:
            raise ValueError(f"unsupported golden fixture_version {version!r}")
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
            tool_match=_checked_tool_match(data),
            success_criteria=_checked_criteria(data),
            allowed_tools=[str(t) for t in (data.get("allowed_tools") or [])],
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
        if len(goldens) >= _MAX_GOLDEN_COUNT:
            logger.warning("Golden cap %d reached; ignoring remaining files in %s (#11062)", _MAX_GOLDEN_COUNT, root)
            break
        size = path.stat().st_size
        if size > _MAX_GOLDEN_FILE_BYTES:
            logger.warning("Skipping oversized golden %s (%d > %d bytes) (#11062)", path, size, _MAX_GOLDEN_FILE_BYTES)
            continue
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        goldens.append(GoldenTrajectory.from_fixture(data))
    logger.info("Loaded %d golden trajectories from %s", len(goldens), root)
    return goldens
