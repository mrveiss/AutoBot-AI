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

import pytest

prometheus_client = pytest.importorskip("prometheus_client")

from autobot_shared.monitoring.metrics.audit import AuditMetricsRecorder  # noqa: E402


def _sample(counter, action: str, error_type: str) -> float:
    """Current value of the labelled counter."""
    return counter.labels(action=action, error_type=error_type)._value.get()


def _exported_sample(manager, action: str, error_type: str) -> float:
    """Current value of the labelled sample in the manager's exported text.

    Read as a delta rather than asserted as an exact 1.0: `get_metrics_manager()`
    is a process-wide singleton that is never reset, so any other test that
    drives this same label pair through it first would break an absolute
    assertion while the code under test is perfectly correct. A false failure is
    cheaper than a false pass but still a trap, and the delta form has no such
    dependence on what ran before.
    """
    needle = f'autobot_audit_write_failures_total{{action="{action}",error_type="{error_type}"}} '
    for line in manager.get_metrics().decode().splitlines():
        if line.startswith(needle):
            return float(line[len(needle) :])
    return 0.0


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

    assert 'autobot_audit_write_failures_total{action="login_success",error_type="ProgrammingError"} 1.0' in text, (
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
        'autobot_audit_write_failures_total{action="login_success",error_type="OperationalError"} 3.0' in text
    ), "three failures must count as three, not one"


def test_the_shared_helper_reaches_the_exported_registry():
    """The hop the middleware actually depends on, executed rather than inspected.

    `test_the_manager_records_and_exports_the_counter` above proves a manager
    you construct yourself exports the sample. The middleware does not construct
    one — it calls `record_audit_write_failure_safely`, which resolves the
    *singleton* via `get_metrics_manager()`. That resolution is the one hop
    nothing covered, and it is the hop that decides whether a dropped audit is
    visible in production.

    It is also the hop that fails quietly: the helper swallows everything by
    design, so a singleton wired to a different registry would leave the counter
    flat with no error anywhere.

    Replaces two tests that read `rbac_middleware.py` as text and asserted a
    function name appeared in it (#14750 review). Those broke when the helper
    was extracted to `autobot_shared`, and would have passed against a helper
    whose body did nothing. Their invariants are covered by execution instead:
    the middleware call sites by `repo_tests/audit_write_failure_counted_test.py`,
    and "counting never raises" by that file's
    `test_the_counter_never_raises_from_the_audit_path`, which drives a failing
    metrics backend through the real helper.
    """
    from autobot_shared.monitoring.metrics.audit import record_audit_write_failure_safely
    from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

    manager = get_metrics_manager()
    before = _exported_sample(manager, "permission_denied", "IntegrityError")

    record_audit_write_failure_safely("permission_denied", "IntegrityError")

    after = _exported_sample(manager, "permission_denied", "IntegrityError")

    assert after == before + 1, (
        "the shared helper did not reach the exported registry. The helper "
        "swallows its own failures, so this is exactly the case that leaves no "
        f"trace: the middleware counts a dropped audit and nothing is exported. "
        f"Sample went {before} -> {after}."
    )
