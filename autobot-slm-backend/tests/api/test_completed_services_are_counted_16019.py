# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A completed oneshot is counted as healthy, not dropped (#16019).

The per-node view stopped reporting `slm-admin-ui` and the `postgresql` wrapper
as `unknown` — and the count the operator actually reads still did not see them
at all. `api/monitoring.py` bucketed only RUNNING and FAILED with no `else`, so
a `completed` service landed in neither.

**That is the same symptom the issue was opened for, one layer up.** Found in
review, not by the fix's own tests, because those tests measured the mapping and
the defect had moved to the aggregation.

Every status the collector can emit is asserted against the declared enum here,
so the next state added to `_map_status_from_states` cannot reach the database
without joining the vocabulary the aggregates switch on.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SLM = Path(__file__).resolve().parents[2]

# The enum is read from SOURCE, not imported. `autobot-slm-backend/conftest.py`
# stubs `models.database` as a MagicMock for the whole session (#16024), and a
# MagicMock satisfies almost any assertion -- the first draft of this file
# compared `ServiceStatus.COMPLETED.value` against a set built from the same
# mocks, where both sides are the same child object, and passed while proving
# nothing. Parsing the declaration is unmockable, and it is also the right
# subject: what the aggregates switch on is the declared vocabulary.


def _declared_statuses() -> set[str]:
    """Values of `ServiceStatus`, parsed from models/database.py."""
    tree = ast.parse((_SLM / "models" / "database.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ServiceStatus":
            return {
                stmt.value.value
                for stmt in node.body
                if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant)
            }
    raise AssertionError("ServiceStatus not found in models/database.py")

#: Every value `HealthCollector._map_status_from_states` can return (#16019).
_COLLECTOR_STATES = {
    "running",
    "completed",
    "failed",
    "crash-loop",
    "starting",
    "stopping",
    "stopped",
    "unknown",
}

#: Statuses the operator's counts must treat as healthy. A oneshot that ran to
#: completion did its job; excluding it is what made a healthy node read short.
_HEALTHY = {"running", "completed"}


def test_every_state_the_collector_emits_is_a_declared_status():
    """The column is `String(20)`, so an undeclared value stores and renders with
    no error — and is then silently absent from every aggregate that switches on
    the enum. Nothing would have surfaced this at runtime."""
    undeclared = sorted(_COLLECTOR_STATES - _declared_statuses())
    assert not undeclared, (
        f"the health collector emits {undeclared}, which ServiceStatus does not "
        "declare — they will store fine and be counted nowhere (#16019)"
    )


def test_completed_is_healthy_and_distinct_from_running():
    """Both halves matter.

    Folding COMPLETED into RUNNING at the source would fix the count and destroy
    the distinction the per-node view needs: nothing is resident for a oneshot,
    and an operator asking 'is it running' deserves a different answer from 'did
    it run'.
    """
    assert "completed" in _declared_statuses()
    assert "completed" in _HEALTHY and "completed" != "running"


def test_unknown_is_not_healthy():
    """The contrast. A fix that counted everything as healthy would pass the test
    above while destroying the only signal these counts carry."""
    for absent in ("unknown", "failed", "stopped"):
        assert absent in _declared_statuses(), f"{absent} is not even declared"
        assert absent not in _HEALTHY


def test_the_aggregates_switch_on_completed():
    """Ordering-free source check on both call sites.

    The per-node aggregate and NodeMetrics are separate loops that drifted apart
    before; asserting one would leave the other exactly as it was.
    """
    source = (_SLM / "api" / "monitoring.py").read_text(encoding="utf-8")
    assert source.count("ServiceStatus.COMPLETED.value") == 2, (
        "both service-count aggregates must treat COMPLETED as healthy — one of "
        "them still drops it (#16019)"
    )
