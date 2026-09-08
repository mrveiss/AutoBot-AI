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
    """Values of `ServiceStatus`, parsed from service_status.py.

    It moved out of `models/database.py` in #16019: that file was AT its
    grandfathered ceiling, so the three new states could not be added there.
    """
    tree = ast.parse((_SLM / "service_status.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ServiceStatus":
            return {
                stmt.value.value
                for stmt in node.body
                if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant)
            }
    raise AssertionError("ServiceStatus not found in service_status.py")


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


def test_both_aggregates_share_one_bucketing_implementation():
    """They were separate loops and had drifted apart once (#16019 review).

    Asserting the shared call rather than a status literal: a source-level count
    of `ServiceStatus.COMPLETED.value` was satisfied by the text alone and would
    pass with `+=` reverted to `=`. What matters is that neither aggregate has
    its own copy to drift again.
    """
    source = (_SLM / "api" / "monitoring.py").read_text(encoding="utf-8")
    assert source.count("bucket_service_counts(") == 2, (
        "the per-node aggregate and NodeMetrics must both fold through the "
        "shared helper; one of them has grown its own loop again (#16019)"
    )


class _Row:
    """A `(status, count)` row as the aggregate query yields it."""

    def __init__(self, status: str, count: int) -> None:
        self.status = status
        self.count = count


def _bucket(rows):
    """`bucket_service_counts`, loaded by path (the package pulls in autobot_shared)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_svc_16019", _SLM / "service_status.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.bucket_service_counts(rows)


def test_running_and_completed_are_summed_not_overwritten():
    """The subtlest line in the fix, and nothing could see it (review of #16019).

    Two statuses feed one bucket. With `=` instead of `+=`, whichever row
    arrives last wins — a node with 3 running and 2 completed reports **2**, and
    the source-level assertion that COMPLETED appears twice still passes.
    """
    assert _bucket([_Row("running", 3), _Row("completed", 2), _Row("failed", 1)]) == {
        "running": 5,
        "failed": 1,
    }


def test_order_does_not_change_the_answer():
    """`=` would make this pair disagree; `+=` cannot."""
    forward = _bucket([_Row("running", 3), _Row("completed", 2)])
    reverse = _bucket([_Row("completed", 2), _Row("running", 3)])
    assert forward == reverse == {"running": 5, "failed": 0}


def test_unhealthy_and_transitional_states_are_counted_in_neither():
    """The contrast, and the deliberate gap #16019 leaves.

    `starting`/`stopping` are declared and emitted but land in neither bucket,
    so the two counts do not sum to the total. That is intended — a starting
    service is not running — and it is asserted here so the next reader finds a
    decision rather than an oversight.
    """
    counts = _bucket([_Row("starting", 4), _Row("stopping", 2), _Row("unknown", 7)])
    assert counts == {"running": 0, "failed": 0}
