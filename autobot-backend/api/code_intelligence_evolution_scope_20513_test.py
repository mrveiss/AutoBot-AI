# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The code-intelligence evolution routes mine the selected source, never a caller-typed path (#20513)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import code_intelligence as mod
from api.codebase_analytics.endpoints import shared

_ROUTES = ("analyze", "patterns", "refactorings", "timeline", "report")


def _client(real_access: bool = False):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(mod.router, prefix="/evolution-test")
    app.dependency_overrides[check_admin_permission] = lambda: True
    if not real_access:
        app.dependency_overrides[shared.require_source_access] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def _url(route: str) -> str:
    return f"/evolution-test/evolution/{route}"


def _call(client, route, **params):
    return client.post(_url(route), params=params) if route == "analyze" else client.get(_url(route), params=params)


def test_each_evolution_route_requires_source_id_and_takes_no_path():
    seen = 0
    for route in mod.router.routes:
        if "/evolution/" not in getattr(route, "path", ""):
            continue
        query = {q.name: q for q in route.dependant.query_params}
        assert "path" not in query, route.path
        assert query["source_id"].field_info.is_required(), route.path
        seen += 1
    assert seen == len(_ROUTES)


@pytest.mark.parametrize("route", _ROUTES)
def test_a_request_without_source_id_is_a_422(route):
    assert _call(_client(), route).status_code == 422


@pytest.mark.parametrize("route", _ROUTES)
def test_a_source_with_no_checkout_is_a_404(route):
    with patch.object(shared, "resolve_source_root", AsyncMock(return_value=None)):
        assert _call(_client(), route, source_id="missing").status_code == 404


@pytest.mark.parametrize("route", _ROUTES)
def test_a_foreign_private_source_is_a_404_with_access_enforcement_left_real(route, tmp_path):
    from api.codebase_analytics.source_models import CodeSource, SourceAccess

    private = CodeSource(name="p", clone_path="/tmp/p", owner_id="alice", access=SourceAccess.PRIVATE)
    with (
        patch("auth_middleware.get_current_user", AsyncMock(return_value={"id": "mallory"})),
        patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=private)),
        patch.object(shared, "resolve_source_root", AsyncMock(return_value=tmp_path)),
    ):
        assert _call(_client(real_access=True), route, source_id="x").status_code == 404


def test_analyze_runs_the_miner_on_the_sources_checkout_only(tmp_path):
    miner = MagicMock()
    miner.return_value.analyze_evolution.return_value = {}
    with (
        patch.object(shared, "resolve_source_root", AsyncMock(return_value=tmp_path)),
        patch.object(mod, "CodeEvolutionMiner", miner),
    ):
        response = _call(_client(), "analyze", source_id="src-1")
    assert response.status_code == 200
    miner.assert_called_once_with(str(tmp_path))
