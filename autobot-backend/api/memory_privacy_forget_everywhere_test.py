# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``DELETE /forget-everywhere/{memory_id}`` refuses an ambiguous id (#13739).

The route used to hand the id to a fan-out that deleted from every store. Now
the store is resolved from the user's own listing, and an id held by more than
one store is a 409 naming the candidates rather than a guess that destroys the
one the caller did not mean.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.memory_privacy import forget_everywhere
from memory.transparency import AmbiguousMemoryId

_USER = {"user_id": "alice", "username": "alice"}


def _request():
    """The route only passes the request to the admin check, which is not reached.

    ``target_user_id`` must be passed explicitly as ``None``: calling the handler
    directly bypasses FastAPI, so the parameter default is a ``Query`` object,
    which is truthy and would send the caller down the admin branch.
    """
    return object()


@pytest.mark.asyncio
async def test_an_ambiguous_id_is_a_409_naming_the_stores():
    with (
        patch(
            "memory.transparency.forget_everywhere",
            AsyncMock(side_effect=AmbiguousMemoryId("6", ["general", "graph"])),
        ),
        patch("api.memory_privacy.audit_log", AsyncMock()) as audit,
    ):
        with pytest.raises(HTTPException) as caught:
            await forget_everywhere(memory_id="6", request=_request(), target_user_id=None, current_user=_USER)

    assert caught.value.status_code == 409
    assert caught.value.detail["stores"] == ["general", "graph"]
    assert caught.value.detail["memory_id"] == "6"
    # The refusal is auditable — a delete that did not happen still matters.
    assert audit.await_args.kwargs["result"] == "rejected"
    assert audit.await_args.kwargs["details"]["ambiguous_stores"] == ["general", "graph"]


@pytest.mark.asyncio
async def test_an_unambiguous_id_still_returns_the_per_store_map():
    resolved = {
        "verbatim": False,
        "trajectory": False,
        "working_memory": False,
        "graph": True,
        "retrieval_learner": False,
        "general": False,
    }
    with (
        patch("memory.transparency.forget_everywhere", AsyncMock(return_value=resolved)),
        patch("api.memory_privacy.audit_log", AsyncMock()),
    ):
        body = await forget_everywhere(memory_id="6", request=_request(), target_user_id=None, current_user=_USER)

    assert body["results"] == resolved
    assert body["deleted_from"] == ["graph"]
    assert body["memory_id"] == "6"
    assert body["user_id"] == "alice"
