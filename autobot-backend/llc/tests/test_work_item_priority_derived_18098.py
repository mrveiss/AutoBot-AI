# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""WorkItemPriority is derived from the canonical Priority, and nothing observable moved (#18098).

Expected values are LITERALS captured from the hand-written enum before it was derived.
"""

from __future__ import annotations

import json
import pickle

import pytest
from pydantic import ValidationError

from autobot_shared.status_enums import Priority
from llc.models.enums import WorkItemPriority, pg_enum_values

OLD_VALUES = ["critical", "high", "medium", "low"]
OLD_SCHEMA = {
    "description": "Priority of an LLC work item (GH#8213).",
    "enum": ["critical", "high", "medium", "low"],
    "title": "WorkItemPriority",
    "type": "string",
}


def test_every_member_is_the_canonical_priority_member():
    """One vocabulary: each name and value is Priority's, in the old order."""
    assert [(m.name, m.value) for m in WorkItemPriority] == [(n.upper(), n) for n in OLD_VALUES]
    assert all(Priority[m.name].value == m.value for m in WorkItemPriority)


def test_no_database_change():
    """(a) the Postgres enum labels and the SA column enum are the old list, in order."""
    from llc.models.work_item import LLCWorkItem

    column = LLCWorkItem.__table__.c.priority.type
    assert pg_enum_values(WorkItemPriority) == OLD_VALUES
    assert column.enums == OLD_VALUES
    assert column.name == "workitempriority"
    # Contrast: the canonical has labels the database enum does not.
    assert pg_enum_values(Priority) != OLD_VALUES


def _create(priority):
    from llc.api.work_items import WorkItemCreate

    return WorkItemCreate(company_id="c", type="task", title="t", priority=priority)


def test_api_accepts_exactly_the_four_values():
    """(b) the request models accept the four and reject what only the canonical carries."""
    from llc.api.work_items import WorkItemUpdate

    for value in OLD_VALUES:
        assert _create(value).priority.value == value
        assert WorkItemUpdate(priority=value).priority.value == value
    for rejected in ("normal", "urgent"):
        with pytest.raises(ValidationError):
            _create(rejected)
        with pytest.raises(ValidationError):
            WorkItemUpdate(priority=rejected)
        assert Priority(rejected)  # contrast: the canonical does accept it


def test_str_mixin_is_kept():
    """(c) a work-item priority is still a str and still serialises as one."""
    assert isinstance(WorkItemPriority.HIGH, str)
    assert WorkItemPriority.HIGH == "high"
    assert json.dumps({"p": WorkItemPriority.HIGH}, default=str) == '{"p": "high"}'
    # The canonical is a str enum too (#14678), so both compare and serialise alike.
    assert isinstance(Priority.HIGH, str)
    assert Priority.HIGH == WorkItemPriority.HIGH == "high"


def test_identity_survives_pickle_and_naming():
    assert pickle.loads(pickle.dumps(WorkItemPriority.HIGH)) is WorkItemPriority.HIGH
    assert (WorkItemPriority.__module__, WorkItemPriority.__qualname__) == ("llc.models.enums", "WorkItemPriority")
    assert repr(WorkItemPriority.HIGH) == "<WorkItemPriority.HIGH: 'high'>"


def test_generated_schema_is_unchanged():
    """(d) the OpenAPI component for the enum, and the fields that reference it."""
    from llc.api.work_items import WorkItemCreate, WorkItemUpdate

    create = WorkItemCreate.model_json_schema()
    update = WorkItemUpdate.model_json_schema()
    assert create["$defs"]["WorkItemPriority"] == OLD_SCHEMA
    assert update["$defs"]["WorkItemPriority"] == OLD_SCHEMA
    assert create["properties"]["priority"] == {"$ref": "#/$defs/WorkItemPriority", "default": "medium"}
    assert update["properties"]["priority"] == {
        "anyOf": [{"$ref": "#/$defs/WorkItemPriority"}, {"type": "null"}],
        "default": None,
    }
