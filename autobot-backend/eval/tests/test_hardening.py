# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hardening tests for the golden-trajectory eval harness (#11062).

Covers the DoS/robustness/hygiene fixes: bounded golden loader, per-replay
timeout, markdown-escaped report interpolation, and validated JSON output path.
"""

import asyncio
import json
from unittest.mock import AsyncMock

from eval import run as run_mod
from eval import store as store_mod
from eval.report import RegressionReport, TrajectoryOutcome, _md_escape
from eval.runner import CandidateResult, TrajectoryReplayer
from eval.store import load_golden_set
from rlm.evaluator import ResponseQualityEvaluator

_FIXTURE = {
    "trajectory_id": "t1",
    "task_class": "code_fix",
    "inputs": {"prompt": "p"},
    "expected_tools": ["read_file"],
    "baseline_score": 0.9,
    "expected_status": "completed",
    "expected_output_excerpt": "ok",
}


def _write_golden(directory, name: str, extra_bytes: int = 0) -> None:
    data = dict(_FIXTURE, trajectory_id=name)
    if extra_bytes:
        data["expected_output_excerpt"] = "x" * extra_bytes
    (directory / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


# --- bounded loader (#11062) ---


def test_load_golden_set_respects_count_cap(tmp_path, monkeypatch):
    for i in range(5):
        _write_golden(tmp_path, f"g{i}")
    monkeypatch.setattr(store_mod, "_MAX_GOLDEN_COUNT", 3)
    assert len(load_golden_set(tmp_path)) == 3


def test_load_golden_set_skips_oversized_files(tmp_path, monkeypatch):
    _write_golden(tmp_path, "small")
    _write_golden(tmp_path, "huge", extra_bytes=5000)
    monkeypatch.setattr(store_mod, "_MAX_GOLDEN_FILE_BYTES", 1000)
    ids = [g.trajectory_id for g in load_golden_set(tmp_path)]
    assert ids == ["small"]  # huge skipped


# --- per-replay timeout (#11062) ---


def test_hanging_replay_recorded_as_failure(monkeypatch):
    monkeypatch.setattr("eval.runner._REPLAY_TIMEOUT_S", 0.05)
    evaluator = ResponseQualityEvaluator()
    evaluator._call_llm = AsyncMock(return_value="SCORE: 0.9\nCRITIQUE: None\nHINT: None")
    replayer = TrajectoryReplayer(evaluator=evaluator)

    async def _hanging_candidate(golden):
        await asyncio.sleep(10)
        return CandidateResult(response_text="never", tool_sequence=[], final_status="completed")

    from eval.store import GoldenTrajectory

    golden = GoldenTrajectory(
        trajectory_id="slow",
        task_class="code_fix",
        inputs={"prompt": "p"},
        expected_tools=["read_file"],
        baseline_score=0.9,
        expected_status="completed",
        expected_output_excerpt="ok",
    )
    rep = asyncio.run(replayer.run([golden], _hanging_candidate))
    (outcome,) = rep.outcomes
    assert outcome.trajectory_id == "slow"
    assert outcome.candidate_score == 0.0 and outcome.tools_ok is False
    assert "timed out" in outcome.detail


# --- markdown escaping (#11062) ---


def test_md_escape_neutralizes_markdown():
    assert _md_escape("a`b|c\nd") == "a\\`b\\|c d"


def test_render_markdown_escapes_crafted_detail():
    rep = RegressionReport(
        outcomes=[
            TrajectoryOutcome(
                trajectory_id="`evil`",
                task_class="x|y",
                baseline_score=0.9,
                candidate_score=0.1,
                tools_ok=False,
                status_ok=True,
                detail="inject `code` | pipe",
            )
        ]
    )
    md = rep.render_markdown()
    assert "`evil`" not in md and "\\`evil\\`" in md
    assert "inject `code`" not in md


# --- output path validation (#11062) ---


def test_resolve_output_path_allows_within_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_OUTPUT_DIR", str(tmp_path))
    resolved = run_mod._resolve_output_path(str(tmp_path / "report.json"))
    assert resolved == (tmp_path / "report.json").resolve()


def test_resolve_output_path_refuses_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_OUTPUT_DIR", str(tmp_path))
    assert run_mod._resolve_output_path("/etc/passwd") is None
    assert run_mod._resolve_output_path(str(tmp_path / ".." / "escape.json")) is None
