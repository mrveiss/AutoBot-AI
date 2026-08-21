# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A dropped audit record must be countable (#14654).

A live SLM lost every audit write for hours to `column audit_logs.updated_at
does not exist`, while returning 200. The swallow is deliberate — `user_management`'s
RBAC middleware catches it so an audit problem cannot turn a correct 403 into a
500 — and this does not change that. What was missing is any way to notice.

The rules below cover the failure mode that would make this change pointless:
a recorder that exists, exports cleanly, and is never constructed. This repo has
been bitten by exactly that ("full surface, no sink" — config, API and docs all
present while nothing emits), so the wiring is asserted, not assumed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

prometheus_client = pytest.importorskip("prometheus_client")

from autobot_shared.monitoring.metrics.audit import AuditMetricsRecorder  # noqa: E402

_SHARED = Path(__file__).resolve().parent.parent.parent
_MANAGER = _SHARED / "monitoring" / "prometheus_metrics.py"
_MIDDLEWARE = _SHARED.parent / "autobot-slm-backend" / "user_management" / "middleware" / "rbac_middleware.py"


def _sample(counter, action: str, error_type: str) -> float:
    """Current value of the labelled counter."""
    return counter.labels(action=action, error_type=error_type)._value.get()


def test_the_counter_actually_counts():
    """Executed, not inspected — a recorder that cannot increment is decoration."""
    registry = prometheus_client.CollectorRegistry()
    recorder = AuditMetricsRecorder(registry)

    before = _sample(recorder.audit_write_failures, "permission_denied", "ProgrammingError")
    recorder.record_write_failure(action="permission_denied", error_type="ProgrammingError")
    after = _sample(recorder.audit_write_failures, "permission_denied", "ProgrammingError")

    assert after == before + 1


def test_error_type_is_a_label_so_a_schema_fault_is_distinguishable():
    """The live failure was a schema error, not connectivity.

    Counting them together would answer "are we losing audits?" but not "why",
    which is the question that shortens the next incident.
    """
    registry = prometheus_client.CollectorRegistry()
    recorder = AuditMetricsRecorder(registry)

    recorder.record_write_failure(action="permission_denied", error_type="ProgrammingError")
    recorder.record_write_failure(action="permission_denied", error_type="OperationalError")

    assert _sample(recorder.audit_write_failures, "permission_denied", "ProgrammingError") == 1
    assert _sample(recorder.audit_write_failures, "permission_denied", "OperationalError") == 1


def test_the_manager_records_and_exports_the_counter():
    """Drive the real manager end to end, not its source text.

    #14674 review: the first version of this file asserted with `ast.parse`
    and substring checks that `record_audit_write_failure` existed and was
    called. Those pass whether or not the method does anything — make it a
    no-op and every one of them stays green, which is the failure mode this
    whole PR is about (a counter that reports zero).

    So this constructs the real `PrometheusMetricsManager`, calls the method
    the middleware calls, and asserts the **sample** appears in the exported
    text. Following `cgroup_memory_test.py:391-405`, which records the same
    lesson: `# HELP` alone proves nothing, because prometheus_client emits it
    for empty families too — the assertion has to be on a value.
    """
    from autobot_shared.monitoring.prometheus_metrics import PrometheusMetricsManager

    manager = PrometheusMetricsManager()
    manager.record_audit_write_failure(action="login_success", error_type="ProgrammingError")

    text = manager.get_metrics().decode()

    assert (
        'autobot_audit_write_failures_total{action="login_success",error_type="ProgrammingError"} 1.0'
        in text
    ), (
        "the counter did not reach the exported registry — either the recorder "
        "is not constructed on the manager's registry, or the manager method "
        "does not delegate to it. Exported text:\n" + text[:2000]
    )


def test_a_second_failure_increments_rather_than_replaces():
    """A counter that resets would under-report exactly when it matters."""
    from autobot_shared.monitoring.prometheus_metrics import PrometheusMetricsManager

    manager = PrometheusMetricsManager()
    for _ in range(3):
        manager.record_audit_write_failure(action="login_success", error_type="OperationalError")

    text = manager.get_metrics().decode()

    assert (
        'autobot_audit_write_failures_total{action="login_success",error_type="OperationalError"} 3.0'
        in text
    ), "three failures must count as three, not one"


def test_the_swallowing_path_emits_the_counter():
    """The whole point: the place that drops the record is the place that counts it.

    If this call is removed, audit loss goes back to being invisible while every
    other rule here still passes.
    """
    source = _MIDDLEWARE.read_text(encoding="utf-8")

    assert (
        "_record_audit_write_failure(" in source
    ), "the RBAC middleware no longer counts a dropped audit entry (#14654)"


def test_counting_never_raises_from_the_audit_path():
    """It runs inside the handler that exists so audits cannot break requests.

    A metrics backend problem must not become the thing that returns a 500 —
    which would invert the decision this whole path is built on.
    """
    source = _MIDDLEWARE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    helper = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_record_audit_write_failure"),
        None,
    )

    assert helper is not None, "the counting helper is gone"
    assert any(
        isinstance(node, ast.Try) for node in ast.walk(helper)
    ), "the counting helper does not guard itself; a metrics failure could propagate into the audit path"
