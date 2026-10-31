# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Status enums renamed apart by axis keep their wire values (#14263).

`AgentStatus`, `StepStatus` and `TaskStatus` each named several different axes.
The renames must not touch a single stored or serialized string, so every
renamed enum's members are pinned here. Source is read with `ast`, so the
backend modules (and their heavy imports) are never executed.
"""

from __future__ import annotations

import ast

import pytest
from repo_tests._paths import repo_root

_ROOT = repo_root()

_PINNED: dict[tuple[str, str], dict[str, str]] = {
    ("autobot-backend/models/heartbeat.py", "HeartbeatStatus"): {
        "ACTIVE": "active",
        "DISABLED": "disabled",
        "PAUSED": "paused",
        "ERROR": "error",
        "TERMINATED": "terminated",
    },
    ("autobot-backend/agents/payloads.py", "AgentOutcome"): {
        "SUCCESS": "success",
        "WARNING": "warning",
        "ERROR": "error",
        "UNAVAILABLE": "unavailable",
        "RATE_LIMITED": "rate_limited",
        "DISABLED": "disabled",
    },
    ("autobot-backend/agents/overseer/types.py", "OverseerTaskStatus"): {
        "PENDING": "pending",
        "PLANNING": "planning",
        "EXECUTING": "executing",
        "STREAMING": "streaming",
        "EXPLAINING": "explaining",
        "COMPLETED": "completed",
        "FAILED": "failed",
        "CANCELLED": "cancelled",
    },
    ("autobot-backend/agents/overseer/types.py", "OverseerStepStatus"): {
        "PENDING": "pending",
        "RUNNING": "running",
        "STREAMING": "streaming",
        "WAITING_EXPLANATION": "waiting_explanation",
        "EXPLAINING": "explaining",
        "COMPLETED": "completed",
        "FAILED": "failed",
    },
    ("autobot-backend/planner/types.py", "PlanStepStatus"): {
        "PENDING": "pending",
        "IN_PROGRESS": "in_progress",
        "COMPLETED": "completed",
        "BLOCKED": "blocked",
        "FAILED": "failed",
        "SKIPPED": "skipped",
    },
    ("autobot_shared/status_enums.py", "AgentStatus"): {
        "HEALTHY": "healthy",
        "DEGRADED": "degraded",
        "UNHEALTHY": "unhealthy",
        "OFFLINE": "offline",
    },
}


def _members(rel: str, cls: str) -> dict[str, str]:
    return _members_from_source((_ROOT / rel).read_text(encoding="utf-8"), cls, rel)


def _members_from_source(source: str, cls: str, rel: str = "<source>") -> dict[str, str]:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            return {
                t.id: s.value.value
                for s in node.body
                if isinstance(s, ast.Assign) and isinstance(s.value, ast.Constant)
                for t in s.targets
                if isinstance(t, ast.Name)
            }
    raise AssertionError(f"{cls} not defined in {rel}")


@pytest.mark.parametrize(
    ("site", "expected"), list(_PINNED.items()), ids=lambda v: v[1] if isinstance(v, tuple) else ""
)
def test_renamed_axis_enum_keeps_its_wire_values(site: tuple[str, str], expected: dict[str, str]) -> None:
    assert _members(*site) == expected


def test_contrast_pair_a_changed_value_is_detected() -> None:
    """The real extractor, run on the real file with one value edited, no longer matches the pin."""
    rel = "autobot-backend/models/heartbeat.py"
    source = (_ROOT / rel).read_text(encoding="utf-8")
    pinned = _PINNED[(rel, "HeartbeatStatus")]
    assert _members_from_source(source, "HeartbeatStatus", rel) == pinned
    old_value = pinned["PAUSED"]
    drifted = source.replace(f'"{old_value}"', '"suspended"', 1)
    assert drifted != source, "the contrast edit must change the source"
    assert _members_from_source(drifted, "HeartbeatStatus", rel) != pinned


def test_the_ambiguous_names_no_longer_name_a_second_axis() -> None:
    """Only the canonical definitions keep the bare names (#14263 task 3)."""
    for rel, cls in (
        ("autobot-backend/models/heartbeat.py", "AgentStatus"),
        ("autobot-backend/agents/payloads.py", "AgentStatus"),
        ("autobot-backend/agents/overseer/types.py", "TaskStatus"),
        ("autobot-backend/agents/overseer/types.py", "StepStatus"),
        ("autobot-backend/planner/types.py", "StepStatus"),
    ):
        with pytest.raises(AssertionError):
            _members(rel, cls)
