# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Reading a session with no owner never makes the reader its owner (#20025).

An ownerless session is a defect: an admin may look, everyone else sees a missing session, and
nothing is written. A write keeps its rule, because a first message on a new id gives it its owner.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from security.session_ownership import SessionOwnershipValidator
from security.session_posture import unowned_read


def _request(method: str) -> MagicMock:
    return MagicMock(method=method)


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_a_reader_gets_what_a_missing_session_gets(method: str) -> None:
    with pytest.raises(HTTPException) as denied:
        unowned_read("s1", {"username": "u", "role": "user"}, _request(method))
    assert denied.value.status_code == 404 and denied.value.detail == "Chat session not found"


def test_an_admin_may_read_and_gets_no_claim() -> None:
    verdict = unowned_read("s1", {"username": "a", "role": "admin"}, _request("GET"))
    assert verdict["authorized"] is True and verdict["reason"] == "admin_unowned_read"


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_a_write_keeps_its_own_rule(method: str) -> None:
    assert unowned_read("s1", {"username": "u", "role": "user"}, _request(method)) is None


def _validator() -> SessionOwnershipValidator:
    validator = SessionOwnershipValidator.__new__(SessionOwnershipValidator)
    validator._durable_owner = AsyncMock(return_value=None)
    validator.set_session_owner = AsyncMock()
    return validator


@pytest.mark.asyncio
async def test_the_shipped_path_writes_no_owner_on_a_read() -> None:
    validator = _validator()
    with pytest.raises(HTTPException):
        await validator._owner_when_cache_is_empty("s1", "u", {"username": "u", "role": "user"}, _request("GET"))
    validator.set_session_owner.assert_not_awaited()


@pytest.mark.asyncio
async def test_contrast_a_first_write_on_a_new_id_still_records_its_owner() -> None:
    validator = _validator()
    owner, early = await validator._owner_when_cache_is_empty(
        "s1", "u", {"username": "u", "role": "user"}, _request("POST")
    )
    validator.set_session_owner.assert_awaited_once()
    assert owner == "u" and early["reason"] == "legacy_migration"
