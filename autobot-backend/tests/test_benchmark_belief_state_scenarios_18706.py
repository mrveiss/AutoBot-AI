# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The belief-state benchmark's scenario data is frozen (#18706).

``fixtures/belief_state_scenarios_18706.json`` was captured from the original
monolithic ``build_scenarios()`` before it was split into per-task builders and
``ToolCall`` became ``BenchmarkToolCall``. The split must not change a byte of
benchmark data.
"""

import dataclasses
import json
from pathlib import Path

from benchmarks.benchmark_belief_state import BenchmarkToolCall, TaskScenario, build_scenarios

_FROZEN = Path(__file__).parent / "fixtures" / "belief_state_scenarios_18706.json"


def _frozen() -> list[dict]:
    return json.loads(_FROZEN.read_text(encoding="utf-8"))


def test_scenarios_equal_frozen_original():
    actual = [dataclasses.asdict(s) for s in build_scenarios()]
    assert actual == _frozen()


def test_scenarios_use_benchmark_tool_call():
    scenarios = build_scenarios()
    assert all(isinstance(s, TaskScenario) for s in scenarios)
    calls = [c for s in scenarios for c in s.tool_calls]
    assert calls, "no tool calls: the isinstance check below would pass vacuously"
    assert all(isinstance(c, BenchmarkToolCall) for c in calls)
