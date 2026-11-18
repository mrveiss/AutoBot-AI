# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``move_subtree_to_project`` writes in bounded batches, after discovery finished (#21032)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from llc.services import work_item_hierarchy as hierarchy
from llc.services.work_item_hierarchy import SUBTREE_UPDATE_BATCH, move_subtree_to_project

ROOT, PROJECT, COMPANY = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _children(ids):
    result = MagicMock()
    result.scalars.return_value.all.return_value = ids
    return result


def _bound_ids(statement) -> int:
    """How many ids the statement's ``id IN (...)`` carries."""
    compiled = statement.compile()
    return max(len(v) for v in compiled.params.values() if isinstance(v, (list, tuple)))


def _is_update(statement) -> bool:
    return statement.__class__.__name__ == "Update"


async def test_more_descendants_than_one_batch_go_out_in_several_updates_in_one_transaction():
    ids = [uuid.uuid4() for _ in range(2 * SUBTREE_UPDATE_BATCH + 5)]
    session = AsyncMock()
    session.execute.side_effect = [_children(ids), _children([])] + [MagicMock() for _ in range(3)]

    assert await move_subtree_to_project(session, ROOT, PROJECT, COMPANY) == len(ids)

    updates = [c.args[0] for c in session.execute.await_args_list if _is_update(c.args[0])]
    assert [_bound_ids(u) for u in updates] == [SUBTREE_UPDATE_BATCH, SUBTREE_UPDATE_BATCH, 5]
    session.commit.assert_not_called()  # the caller's transaction, never its own
    session.begin.assert_not_called()


async def test_a_failing_later_descendant_query_issues_no_update():
    level_two = [uuid.uuid4()]
    session = AsyncMock()
    session.execute.side_effect = [_children([uuid.uuid4()]), _children(level_two), RuntimeError("db went away")]

    with pytest.raises(RuntimeError):
        await move_subtree_to_project(session, ROOT, PROJECT, COMPANY)

    assert not [c for c in session.execute.await_args_list if _is_update(c.args[0])]


def test_the_batch_is_under_the_driver_bind_limit():
    assert 0 < hierarchy.SUBTREE_UPDATE_BATCH < 32767
