# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

"""#14750: a dropped audit record must be counted in BOTH backends.

#14654 was a live SLM dropping every audit record for hours behind a 200, the
only trace in an error log. #14674 made that countable — in one backend. The
other carried a byte-identical handler, same `audit_logs` table, with the same
silent swallow and no counter.

These assert the invariant rather than today's call sites: wherever a
permission-denied audit write is swallowed, the loss is counted.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

MIDDLEWARES = [
    "autobot-backend/user_management/middleware/rbac_middleware.py",
    "autobot-slm-backend/user_management/middleware/rbac_middleware.py",
]


@pytest.mark.parametrize("rel", MIDDLEWARES, ids=["backend", "slm-backend"])
def test_a_swallowed_permission_denied_audit_is_counted(rel: str) -> None:
    path = REPO_ROOT / rel
    assert path.is_file(), f"{rel} is missing — this guard would pass vacuously"
    text = path.read_text(encoding="utf-8")

    assert "failed to persist permission-denied audit entry" in text, (
        f"{rel} no longer swallows a permission-denied audit write, so this guard "
        "is pointed at the wrong place — re-point it rather than deleting it"
    )
    assert "record_audit_write_failure_safely" in text, (
        f"{rel} swallows a failed audit write without counting it. That is the "
        "#14654 shape: the record is lost and nothing says so (#14750)."
    )


def test_both_backends_use_the_same_counter() -> None:
    """One definition, so instrumenting one backend cannot leave the other behind.

    The two handlers were byte-identical and only one was instrumented; a second
    local copy would let them drift again.
    """
    for rel in MIDDLEWARES:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert (
            "from autobot_shared.monitoring.metrics.audit import" in text
        ), f"{rel} does not import the shared counter"
        assert not re.search(
            r"^def _record_audit_write_failure", text, re.M
        ), f"{rel} defines its own copy of the counter again"


def test_the_counter_never_raises_from_the_audit_path() -> None:
    """It runs inside the handler that exists so audit trouble cannot break a request."""
    from autobot_shared.monitoring.metrics.audit import record_audit_write_failure_safely

    import autobot_shared.monitoring.prometheus_metrics as pm

    original = pm.get_metrics_manager

    def explode():
        raise RuntimeError("metrics backend down")

    pm.get_metrics_manager = explode
    try:
        record_audit_write_failure_safely("PERMISSION_DENIED", "OperationalError")
    finally:
        pm.get_metrics_manager = original
