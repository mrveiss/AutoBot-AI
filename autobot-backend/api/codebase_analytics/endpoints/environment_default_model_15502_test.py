# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The env-analysis AI filter's default model is served by the backend, not held by the UI (#15502).

The frontend used to mirror the quality-tier model name; it now reads it from
``GET /api/analytics/codebase/env-analysis/default-model``. The route and the ``llm_model``
query default of ``/env-analysis`` must both bind to the one ``QUALITY_MODEL`` constant.
"""

import inspect

from api.codebase_analytics.endpoints import environment, environment_default_model
from api.codebase_analytics.router import router as analytics_router
from autobot_shared.ssot_config import QUALITY_MODEL


async def test_default_model_route_returns_the_quality_tier() -> None:
    assert await environment_default_model.get_env_analysis_default_model() == {"model": QUALITY_MODEL}


def test_the_env_analysis_query_default_is_the_same_constant() -> None:
    wrapped = inspect.unwrap(environment.get_environment_analysis)
    default = inspect.signature(wrapped).parameters["llm_model"].default
    assert default.default == QUALITY_MODEL


def _client(*, deny: bool = False):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    def _forbid() -> None:
        raise HTTPException(status_code=403)

    app = FastAPI()
    app.include_router(analytics_router, prefix="/api/analytics/codebase")
    for dep in analytics_router.dependencies:
        app.dependency_overrides[dep.dependency] = _forbid if deny else (lambda: None)
    return TestClient(app, raise_server_exceptions=False)


def test_the_route_is_served_through_the_router() -> None:
    response = _client().get("/api/analytics/codebase/env-analysis/default-model")
    assert response.status_code == 200
    assert response.json() == {"model": QUALITY_MODEL}


def test_the_route_sits_behind_the_router_auth_like_its_siblings() -> None:
    response = _client(deny=True).get("/api/analytics/codebase/env-analysis/default-model")
    assert response.status_code == 403


def test_the_route_is_read_only() -> None:
    client = _client()
    assert client.post("/api/analytics/codebase/env-analysis/default-model").status_code == 405
