# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A permission denial whose audit write fails must be counted (#14843).

#14750 instrumented the DB-backed denial audit in both backends' RBAC
middleware, and its guard proves both use the same counter. It could not see a
second denial path: ``auth_rbac._deny_permission_access`` and
``_deny_any_permission_access`` audit through ``SecurityLayer.audit_log``, which
appends a JSON line to a file and swallowed any write failure. A full disk, a
permissions change or a rotated-away directory dropped every record on that path
while requests kept returning correct 403s.

These drive the real denial path with a real write failure and assert the
counter moved. Deliberately not "the audit call was made" and not "nothing
raised" — the unfixed code satisfied both.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_COUNTER = "autobot_audit_write_failures_total"

# Appending to a path that is a DIRECTORY raises IsADirectoryError. Pinning the
# error type rather than accepting any failure asserts WHICH branch ran: a test
# that accepts any label would pass if the write failed for a reason the test
# did not arrange.
_EXPECTED_ERROR = "IsADirectoryError"


def _counter_value(action: str, error_type: str) -> float:
    from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

    value = get_metrics_manager().registry.get_sample_value(_COUNTER, {"action": action, "error_type": error_type})
    return 0.0 if value is None else value


def _layer_writing_to(path: Path):
    """A SecurityLayer whose audit file is unwritable.

    Built without ``__init__`` on purpose: ``audit_log`` reads exactly one
    attribute, and constructing the real thing would drag in config loading that
    has nothing to do with what is under test.
    """
    from security_layer import SecurityLayer

    layer = SecurityLayer.__new__(SecurityLayer)
    layer.audit_log_file = str(path)
    return layer


def _request(path: str = "/api/analytics/report"):
    request = MagicMock()
    request.url.path = path
    return request


@pytest.mark.parametrize(
    "deny,args",
    [
        ("_deny_permission_access", ("analytics:view",)),
        ("_deny_any_permission_access", (["analytics:view", "analytics:export"],)),
    ],
)
def test_a_failed_denial_audit_write_increments_the_counter(tmp_path, deny, args):
    """Both file-backed denial entry points, since only instrumenting one is the bug."""
    from fastapi import HTTPException

    import auth_rbac

    unwritable = tmp_path / "audit-log-is-a-directory"
    unwritable.mkdir()

    before = _counter_value("permission_denied", _EXPECTED_ERROR)

    with patch.object(auth_rbac, "_get_security_layer", return_value=_layer_writing_to(unwritable)):
        with pytest.raises(HTTPException) as raised:
            getattr(auth_rbac, deny)({"username": "someone", "role": "viewer"}, *args, _request())

    # The denial itself must still be a clean 403 — counting the loss must not
    # turn an audit problem into a request failure.
    assert raised.value.status_code == 403

    after = _counter_value("permission_denied", _EXPECTED_ERROR)
    assert after == before + 1, (
        "the denial audit write failed and nothing counted it — the record is "
        f"lost and indistinguishable from one that was written ({_COUNTER} did "
        f"not move: {before} -> {after}) (#14843)"
    )


def test_a_successful_denial_audit_writes_the_record_and_counts_nothing(tmp_path):
    """Negative control: the counter must measure loss, not denials.

    A counter that also moved on success would read as loss during normal
    operation, which is the same defect pointing the other way.
    """
    from fastapi import HTTPException

    import auth_rbac

    audit_file = tmp_path / "audit.log"
    before = _counter_value("permission_denied", _EXPECTED_ERROR)

    with patch.object(auth_rbac, "_get_security_layer", return_value=_layer_writing_to(audit_file)):
        with pytest.raises(HTTPException):
            auth_rbac._deny_permission_access({"username": "someone", "role": "viewer"}, "analytics:view", _request())

    written = audit_file.read_text(encoding="utf-8")
    assert "permission_denied" in written, "the record was not written at all"
    assert "analytics:view" in written

    after = _counter_value("permission_denied", _EXPECTED_ERROR)
    assert after == before, "a record that WAS written must not be counted as lost"


def test_a_role_denial_write_failure_is_counted_under_its_own_action(tmp_path):
    """The third entry point in the same file audits ``role_denied``.

    Its records go down the identical swallow, so a counter keyed only to
    ``permission_denied`` would leave that loss invisible.
    """
    from fastapi import HTTPException

    import auth_rbac

    unwritable = tmp_path / "audit-log-is-a-directory"
    unwritable.mkdir()

    before = _counter_value("role_denied", _EXPECTED_ERROR)

    with patch.object(auth_rbac, "_get_security_layer", return_value=_layer_writing_to(unwritable)):
        with pytest.raises(HTTPException):
            auth_rbac._deny_role_access({"username": "someone", "role": "viewer"}, ["admin"], "viewer", _request())

    after = _counter_value("role_denied", _EXPECTED_ERROR)
    assert after == before + 1, f"a lost role-denial record was not counted ({before} -> {after})"
