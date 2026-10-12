# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every caller of the source registry handles `RegistryUnavailable` on purpose (#17982).

`get_source` / `get_default_source_id` used to return None when the registry
could not be read, which each caller read as "no such source". They raise now, so
each caller either fails loudly with a clear status or degrades deliberately.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.codebase_analytics.endpoints.shared import authorize_source_access, default_source_id
from api.codebase_analytics.source_storage import RegistryUnavailable

_DOWN = AsyncMock(side_effect=RegistryUnavailable("down"))


@pytest.mark.asyncio
async def test_authorization_answers_503_for_a_fault_and_404_for_an_unknown_id():
    with patch("api.codebase_analytics.source_storage.get_source", _DOWN):
        with pytest.raises(HTTPException) as fault:
            await authorize_source_access("some-id", {"username": "u"})
    with patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as unknown:
            await authorize_source_access("some-id", {"username": "u"})
    assert fault.value.status_code == 503 and unknown.value.status_code == 404


@pytest.mark.asyncio
async def test_a_handler_cannot_mistake_a_dead_registry_for_no_default_source():
    with patch("api.codebase_analytics.source_storage.get_default_source_id", _DOWN):
        with pytest.raises(HTTPException) as caught:
            await default_source_id()
    assert caught.value.status_code == 503
    with patch("api.codebase_analytics.source_storage.get_default_source_id", AsyncMock(return_value=None)):
        assert await default_source_id() is None, "a genuinely empty registry is still 'no default'"


def test_the_app_level_handler_turns_an_unhandled_fault_into_503():
    from initialization.registry_handlers import register_registry_handlers

    app = FastAPI()
    register_registry_handlers(app)

    @app.get("/boom")
    async def boom():
        raise RegistryUnavailable("secret-host:6379 refused")

    response = TestClient(app).get("/boom")
    assert response.status_code == 503
    assert "secret-host" not in response.text, "the cause is logged, never returned"


@pytest.mark.asyncio
async def test_the_project_list_degrades_without_the_source_summary():
    from llc.api.sprints import _project_source_summary

    with patch("api.codebase_analytics.source_storage.get_source", _DOWN):
        assert await _project_source_summary("11111111-1111-1111-1111-111111111111") is None


@pytest.mark.asyncio
async def test_project_disposal_aborts_rather_than_orphaning_the_clone():
    """Before: a fault returned silently, the project was deleted and its clone orphaned."""
    from llc.services.project_disposal import _dispose_source

    with patch("api.codebase_analytics.source_storage.get_source", _DOWN):
        with pytest.raises(RegistryUnavailable):
            await _dispose_source("some-id")
