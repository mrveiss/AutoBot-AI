# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20665: the record written BEFORE a credential delete or rotate never says "success".

Every assertion is on the audit STORE (the events the canonical logger emits), not on
the status code. A write that then fails must leave "attempted" followed by "failed",
and no record anywhere in the trail that claims the change happened.
"""

from unittest.mock import MagicMock, patch

from api import secrets_audit_store_18648_test as base
from services.audit_logger import AuditLogger

KNOWN_VALUE, SECRET_ID, _delete = base.KNOWN_VALUE, base.SECRET_ID, base._delete
client, store = base.client, base.store  # the same fixtures: the route with a faked store write


def _results(store, operation: str) -> list[tuple[str, str | None]]:
    """(outcome, phase) of every record of `operation`, in write order."""
    return [(e.outcome, e.metadata["details"].get("phase")) for e in store.events if e.action == operation]


def _failing_delete(client):
    client.manager.delete_secret = MagicMock(side_effect=RuntimeError("disk full"))
    return client.delete(f"/api/secrets/{SECRET_ID}")


def _failing_update(client):
    client.manager.update_secret = MagicMock(side_effect=RuntimeError("disk full"))
    return client.put(f"/api/secrets/{SECRET_ID}", json={"value": KNOWN_VALUE})


def test_a_delete_records_attempted_then_success(client, store) -> None:
    assert _delete(client).status_code == 200

    assert _results(store, "secret.delete") == [("attempted", "before_write"), ("success", "completed")]


def test_a_failed_delete_leaves_no_record_claiming_success(client, store) -> None:
    assert _failing_delete(client).status_code == 500

    results = _results(store, "secret.delete")
    assert results[0] == ("attempted", "before_write")
    assert results[-1][0] == "failed"
    assert "success" not in [outcome for outcome, _ in results]


def test_a_failed_update_leaves_no_record_claiming_success(client, store) -> None:
    assert _failing_update(client).status_code == 500

    results = _results(store, "secret.update")
    assert results[0] == ("attempted", "before_write")
    assert results[-1][0] == "failed"
    assert "success" not in [outcome for outcome, _ in results]


async def _read(store, **filters):
    """What the audit READER returns: ``AuditLogger.query`` over a store that applies the filter it is given."""

    async def select(flt, limit=100, offset=0):
        return [e.__dict__ for e in store.events if flt.outcome in (None, e.outcome) and flt.action in (None, e.action)]

    with patch("services.audit_logger.canonical.query_filtered", select):
        return await AuditLogger().query(**filters)


async def test_the_attempted_record_is_not_a_success_for_a_reader_filtering_on_result(client, store) -> None:
    _failing_delete(client)  # leaves "attempted" then "failed"
    _delete(client)  # the positive control: a delete that works leaves a "success"

    successes = await _read(store, operation="secret.delete", result="success")
    attempted = await _read(store, operation="secret.delete", result="attempted")

    assert [e.result for e in successes] == ["success"], "the attempted and failed records are not successes"
    assert [e.result for e in attempted] == ["attempted", "attempted"]
