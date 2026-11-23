# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21375 AC3: the secret routes write their attempt and outcome rows through ``services.audit.outcome``.

Heartbeat and the secret routes are one mechanism: ``attempted`` first (a 503 and no change when it cannot be
written), then ONE outcome row -- ``success``, ``denied`` or ``failed`` -- linked to the attempt by ``attempt_id``.
Every assertion is on the audit store's events.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from api import secrets_audit_store_18648_test as base
from services.audit.outcome import AUDIT_UNAVAILABLE_DETAIL

SECRET_ID, _delete = base.SECRET_ID, base._delete
client, store = base.client, base.store  # the same fixtures: the route with a faked store write


def _rows(store) -> list:
    return [e for e in store.events if e.action == "secret.delete"]


def _assert_linked_pair(store, outcome: str, reason: str | None) -> None:
    attempt, final = _rows(store)
    assert (attempt.outcome, final.outcome) == ("attempted", outcome)
    assert final.metadata["attempt_id"] == attempt.id and final.id != attempt.id
    assert final.metadata["details"].get("reason") == reason
    assert attempt.resource_id == final.resource_id and SECRET_ID not in str(final.resource_id)


def test_a_completed_delete_links_its_success_row_to_the_attempt(client, store) -> None:
    assert _delete(client).status_code == 200

    _assert_linked_pair(store, "success", None)


def test_a_refused_delete_links_a_denied_row_to_the_attempt(client, store) -> None:
    client.manager.delete_secret = MagicMock(side_effect=PermissionError("owner SECRET-VALUE"))

    assert client.delete(f"/api/secrets/{SECRET_ID}").status_code == 403

    _assert_linked_pair(store, "denied", "permission_denied")
    assert "SECRET-VALUE" not in repr([e.__dict__ for e in store.events])


def test_a_failed_delete_links_a_failed_row_carrying_the_class_name_only(client, store) -> None:
    client.manager.delete_secret = MagicMock(side_effect=RuntimeError("disk said SECRET-VALUE"))

    assert client.delete(f"/api/secrets/{SECRET_ID}").status_code == 500

    _assert_linked_pair(store, "failed", "RuntimeError")
    assert "SECRET-VALUE" not in repr([e.__dict__ for e in store.events])


def test_an_unwritable_attempt_is_a_503_and_the_delete_never_runs(client) -> None:
    client.manager.delete_secret = MagicMock(return_value=True)

    with patch("services.audit.outcome.record_committed", AsyncMock(return_value=False)):
        response = client.delete(f"/api/secrets/{SECRET_ID}")

    assert response.status_code == 503
    assert response.json() == {"detail": AUDIT_UNAVAILABLE_DETAIL}
    client.manager.delete_secret.assert_not_called()


def test_a_write_that_raises_is_also_an_unwritable_attempt(client) -> None:
    client.manager.delete_secret = MagicMock(return_value=True)

    with patch("services.audit.outcome.record_committed", AsyncMock(side_effect=RuntimeError("down"))):
        response = client.delete(f"/api/secrets/{SECRET_ID}")

    assert response.status_code == 503
    client.manager.delete_secret.assert_not_called()


def test_an_unwritable_outcome_is_logged_and_does_not_change_the_answer(client, store, caplog) -> None:
    rows: list = []

    async def only_the_attempt(event):
        rows.append(event)
        return len(rows) == 1

    with patch("services.audit.outcome.record_committed", only_the_attempt):
        assert _delete(client).status_code == 200

    assert [e.outcome for e in rows] == ["attempted", "success"]
    assert "AUDIT_OUTCOME_MISSING" in caplog.text
