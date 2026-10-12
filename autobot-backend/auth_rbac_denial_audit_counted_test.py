# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A permission denial whose audit record is lost must be counted (#14843).

#14750 instrumented the DB-backed denial audit in both backends' RBAC
middleware. ``auth_rbac._deny_permission_access``, ``_deny_any_permission_access``
and ``_deny_role_access`` audit through ``SecurityLayer.audit_log`` instead. That
used to append to a file and swallow the failure; since #17225 D6 it records
through the canonical audit service, and the loss it can still suffer is a
record that could not be scheduled at all (a thread with no event loop, before
any loop was seen). That loss is counted under ``NotScheduled``.

These drive the real denial path down to the real ``services.audit.audit.emit``
and assert the counter moved -- deliberately not "the audit call was made" and
not "nothing raised"; code that dropped the record silently satisfied both.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

_COUNTER = "autobot_audit_write_failures_total"
_EXPECTED_ERROR = "NotScheduled"


def _counter_value(action: str, error_type: str) -> float:
    from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

    value = get_metrics_manager().registry.get_sample_value(_COUNTER, {"action": action, "error_type": error_type})
    return 0.0 if value is None else value


def _layer():
    """A SecurityLayer built without ``__init__``: ``audit_log`` reads no attribute."""
    from security_layer import SecurityLayer

    return SecurityLayer.__new__(SecurityLayer)


def _request(path: str = "/api/analytics/report"):
    request = MagicMock()
    request.url.path = path
    return request


def _no_loop_anywhere():
    """The real loss condition: no running loop here and none captured to hand off to."""
    from services.audit import audit

    return patch.object(audit, "_LOOP", None)


@pytest.mark.parametrize(
    "deny,args",
    [
        ("_deny_permission_access", ("analytics:view",)),
        ("_deny_any_permission_access", (["analytics:view", "analytics:export"],)),
    ],
)
def test_a_lost_denial_audit_record_increments_the_counter(deny, args):
    """Both permission-denial entry points, since only instrumenting one is the bug."""
    from fastapi import HTTPException

    import auth_rbac

    before = _counter_value("permission_denied", _EXPECTED_ERROR)

    with _no_loop_anywhere(), patch.object(auth_rbac, "_get_security_layer", return_value=_layer()):
        with pytest.raises(HTTPException) as raised:
            getattr(auth_rbac, deny)({"username": "someone", "role": "viewer"}, *args, _request())

    # The denial itself must still be a clean 403 -- counting the loss must not
    # turn an audit problem into a request failure.
    assert raised.value.status_code == 403

    after = _counter_value("permission_denied", _EXPECTED_ERROR)
    assert after == before + 1, (
        "the denial audit record was lost and nothing counted it -- it is "
        f"indistinguishable from one that was written ({_COUNTER} did "
        f"not move: {before} -> {after}) (#14843)"
    )


def test_a_scheduled_denial_audit_records_the_event_and_counts_nothing():
    """Negative control: the counter must measure loss, not denials."""
    from fastapi import HTTPException

    import auth_rbac
    from services.audit import audit

    handed_over = []

    def capture(coro, *, name, loop):
        handed_over.append(coro.cr_frame.f_locals["event"])
        coro.close()
        return object()  # a scheduled future

    before = _counter_value("permission_denied", _EXPECTED_ERROR)
    with (
        patch.object(audit, "fire_and_forget_threadsafe", side_effect=capture),
        patch.object(auth_rbac, "_get_security_layer", return_value=_layer()),
    ):
        with pytest.raises(HTTPException):
            auth_rbac._deny_permission_access({"username": "someone", "role": "viewer"}, "analytics:view", _request())

    assert [e.action for e in handed_over] == ["permission_denied"], "the record was not handed to the service"
    assert "analytics:view" in str(handed_over[0].metadata)
    after = _counter_value("permission_denied", _EXPECTED_ERROR)
    assert after == before, "a record that WAS scheduled must not be counted as lost"


def test_a_role_denial_loss_is_counted_under_its_own_action():
    """The third entry point audits ``role_denied``; a counter keyed only to
    ``permission_denied`` would leave that loss invisible."""
    from fastapi import HTTPException

    import auth_rbac

    before = _counter_value("role_denied", _EXPECTED_ERROR)

    with _no_loop_anywhere(), patch.object(auth_rbac, "_get_security_layer", return_value=_layer()):
        with pytest.raises(HTTPException):
            auth_rbac._deny_role_access({"username": "someone", "role": "viewer"}, ["admin"], "viewer", _request())

    after = _counter_value("role_denied", _EXPECTED_ERROR)
    assert after == before + 1, f"a lost role-denial record was not counted ({before} -> {after})"
