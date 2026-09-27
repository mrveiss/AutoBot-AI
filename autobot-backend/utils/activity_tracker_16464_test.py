# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The desktop tracker can actually build its row (#16464).

#16464 ported `desktop_activities` into the live Alembic chain, which was
necessary and NOT SUFFICIENT: `track_desktop_activity` passed ``metadata=`` to
``DesktopActivityModel``, whose column is ``extra_data``. ``metadata`` is
reserved on the declarative Base -- that is *why* the column is named
``extra_data`` -- so the constructor raised ``TypeError`` before any SQL was
emitted. The table existed and nothing could write to it.

It was invisible because `api/vnc_proxy.py` wraps the call in
``except Exception`` and logs "Control-lock audit logging failed ... (non-fatal)".
A code defect presented as a non-fatal audit hiccup, and on this host the
message had never appeared at all -- so the absence of a missing-table error in
the logs was never evidence the path worked. Nothing reached the database.

The double CAPTURES the constructed model rather than mocking the constructor,
because the defect is in construction: a double that never builds the model
cannot notice a constructor that refuses its arguments.
"""

from __future__ import annotations

import uuid

import pytest

from models.activities import DesktopActivityModel
from utils.activity_tracker import track_desktop_activity


class _CapturingSession:
    """Captures what would be persisted, so the row can be inspected."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        return None

    async def refresh(self, _obj: object) -> None:
        return None


@pytest.mark.asyncio
async def test_the_tracker_can_construct_its_row_at_all() -> None:
    """The defect: this raised TypeError on `metadata=` before touching the DB."""
    db = _CapturingSession()

    await track_desktop_activity(db=db, user_id=uuid.uuid4(), action="click")

    assert db.added, "nothing was staged for persistence"
    assert isinstance(db.added[0], DesktopActivityModel)


@pytest.mark.asyncio
async def test_metadata_lands_in_extra_data() -> None:
    """The public parameter is `metadata`; the column is `extra_data`.

    Asserts the value actually arrives, not merely that the call did not raise --
    renaming the kwarg to something else the model happens to accept would pass
    a no-exception check.
    """
    db = _CapturingSession()

    await track_desktop_activity(db=db, user_id=uuid.uuid4(), action="type", metadata={"app": "terminal"})

    assert db.added[0].extra_data == {"app": "terminal"}


@pytest.mark.asyncio
async def test_the_model_has_no_metadata_column_to_write_to() -> None:
    """Pins WHY the kwarg was wrong, so the fix is not reverted as cosmetic.

    `metadata` is the declarative Base's MetaData object. It is not a column and
    never was, which is the whole reason the column is `extra_data`.
    """
    assert "extra_data" in DesktopActivityModel.__table__.columns
    assert "metadata" not in DesktopActivityModel.__table__.columns


@pytest.mark.asyncio
async def test_omitted_metadata_becomes_an_empty_dict_not_none() -> None:
    """The column is non-optional in the model, so None would be a second bug."""
    db = _CapturingSession()

    await track_desktop_activity(db=db, user_id=uuid.uuid4(), action="move")

    assert db.added[0].extra_data == {}
