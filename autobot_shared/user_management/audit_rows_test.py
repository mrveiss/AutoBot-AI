# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One mapping onto ``audit_logs``, whoever writes the row (#17225 D1).

The ORM class is replaced by a plain recorder of its keyword arguments: what is
under test is the mapping, and instantiating the real mapped class configures
every mapper in the shared registry, which needs each backend's concrete
``Organization`` -- a property of the process, not of this module.
"""

import uuid
from types import SimpleNamespace

import pytest

from autobot_shared.user_management import audit_rows
from autobot_shared.user_management.audit_rows import ACTION_FULL_KEY, SYSTEM_ACTOR, UNSPECIFIED_RESOURCE, audit_row


@pytest.fixture(autouse=True)
def _rows_are_plain_records(monkeypatch):
    monkeypatch.setattr(audit_rows, "AuditLog", lambda **columns: SimpleNamespace(**columns))


def test_a_user_writers_row_names_the_user_as_actor() -> None:
    user = uuid.uuid4()
    row = audit_row(action="team_created", resource_type="team", user_id=user, resource=uuid.UUID(int=7))
    assert row.actor == str(user) and row.user_id == user
    assert row.resource_id == uuid.UUID(int=7) and row.resource_ref == str(uuid.UUID(int=7))
    assert row.category == "security"


def test_a_non_user_actor_and_a_text_resource_fit_the_schema() -> None:
    row = audit_row(action="get.api.files", resource_type=None, actor="agent-7", resource="/api/files")
    assert (row.actor, row.user_id) == ("agent-7", None), "a non-user actor never touches the users FK"
    assert (row.resource_ref, row.resource_id) == ("/api/files", None)
    assert row.resource_type == UNSPECIFIED_RESOURCE


def test_no_actor_is_the_system() -> None:
    assert audit_row(action="x", resource_type="r").actor == SYSTEM_ACTOR


def test_an_over_long_action_is_capped_and_kept_whole_in_details() -> None:
    action = "get." + "a" * 300
    row = audit_row(action=action, resource_type="endpoint", details={"k": 1})
    assert len(row.action) == 100
    assert row.details == {"k": 1, ACTION_FULL_KEY: action}


def test_the_event_id_becomes_the_row_id() -> None:
    event_id = uuid.uuid4()
    assert audit_row(action="x", resource_type="r", event_id=str(event_id)).id == event_id
