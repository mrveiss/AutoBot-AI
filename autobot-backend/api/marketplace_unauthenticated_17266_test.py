# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17266 AC3: every marketplace route turns away a caller with no credentials, driven over HTTP.

``marketplace_auth_17266_test`` reads the dependency graph; this drives each route through a ``TestClient``
with the REAL ``get_current_user`` / ``check_admin_permission`` doing the rejecting. Only the identity lookup
(``resolve_human_user``) is stood in, answering "nobody" as it does for a request with no token or cookie.
The routes are enumerated from ``router.routes``, never listed by hand.
"""

from __future__ import annotations

import importlib
import re
import sys
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from tests.conftest import load_real_auth_middleware


@pytest.fixture
def served(monkeypatch):
    """``(client, routes)``: the marketplace router mounted behind the production auth module."""
    real = load_real_auth_middleware()
    monkeypatch.setitem(sys.modules, "auth_middleware", real)
    api_pkg = importlib.import_module("api")
    # Both the module cache and the package attribute are put back at teardown.
    monkeypatch.delitem(sys.modules, "api.marketplace", raising=False)
    monkeypatch.setattr(api_pkg, "marketplace", getattr(api_pkg, "marketplace", None), raising=False)
    module = importlib.import_module("api.marketplace")
    monkeypatch.setattr(real, "resolve_human_user", AsyncMock(return_value=None))
    app = FastAPI()
    app.include_router(module.router, prefix="/api/marketplace")
    routes = [r for r in module.router.routes if isinstance(r, APIRoute)]
    yield TestClient(app, raise_server_exceptions=False), routes


def test_the_inventory_is_not_empty(served):
    _, routes = served
    assert routes, "marketplace router exposes no routes; the loop below would pass vacuously"


def test_every_route_rejects_a_caller_with_no_credentials(served):
    client, routes = served
    answers = {}
    for route in routes:
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            url = "/api/marketplace" + re.sub(r"\{[^}]+\}", "x", route.path)
            answers[f"{method} {route.path}"] = client.request(method, url).status_code
    assert answers, "no route was driven"
    assert {k: v for k, v in answers.items() if v not in (401, 403)} == {}
