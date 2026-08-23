# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Audit Metrics Recorder

Visibility for audit records that were meant to be written and were not
(#14654).

An audit write failing is deliberately non-fatal: `user_management`'s RBAC
middleware catches it so a backend problem cannot turn a correct 403 into a 500.
That decision is right and this does not change it.

What it left missing is any way to *notice*. A live SLM was losing every audit
record to `column audit_logs.updated_at does not exist` while returning 200, and
the only trace was a line in an error log nobody was watching. For a table whose
whole purpose is knowing what happened, silent loss is the worst failure mode it
has.
"""

from prometheus_client import Counter

from autobot_shared.logging_manager import get_logger

from .base import BaseMetricsRecorder

logger = get_logger(__name__)


class AuditMetricsRecorder(BaseMetricsRecorder):
    """Recorder for audit-trail integrity metrics."""

    def _init_metrics(self) -> None:
        """Initialize audit metrics."""
        self.audit_write_failures = Counter(
            "autobot_audit_write_failures_total",
            "Audit records that could not be persisted, by action and error type",
            ["action", "error_type"],
            registry=self.registry,
        )

    def record_write_failure(self, action: str, error_type: str) -> None:
        """Count an audit record that was dropped.

        Args:
            action: the audited action whose record was lost.
            error_type: exception class name, so a schema problem is
                distinguishable from a connectivity one without reading logs.
        """
        self.audit_write_failures.labels(action=action, error_type=error_type).inc()


__all__ = ["AuditMetricsRecorder", "record_audit_write_failure_safely"]


def record_audit_write_failure_safely(action: object, error_type: str) -> None:
    """Count a dropped audit record, without ever raising from the attempt.

    Metrics are best-effort here by construction: every caller runs inside a
    handler that exists so an audit problem cannot break a request, so this must
    not become a way for one to do so (#14654, #14674).

    Lives here rather than in a middleware because both backends need it and it
    was previously defined in only one of them — same bug, same `audit_logs`
    table, one instrumented and the other silent (#14750).
    """
    try:
        from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

        get_metrics_manager().record_audit_write_failure(action=str(action), error_type=error_type)
    except Exception as exc:  # nosec B110  # see docstring: never raise from the audit path
        # Without this the counter's own failure is both unrecorded AND
        # uncounted — a failure counter reporting zero, which is worse than no
        # counter. Debug keeps it out of normal operation while leaving a trace
        # when the metric is inexplicably flat.
        logger.debug("audit write-failure metric could not be recorded: %s", exc)
