# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The quality score's security factor counts ONE source's problems (#22198)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from api import analytics_code as mod


def test_the_security_read_names_the_source_and_the_problem_types():
    collection = MagicMock()
    collection.get.return_value = {"metadatas": [{}, {}]}
    with patch("api.codebase_analytics.storage.get_code_collection", return_value=collection):
        score = mod._calculate_security_score({"codebase_metrics": {"total_files": 10}}, "src-1")
    where = collection.get.call_args.kwargs["where"]
    assert {"source_id": "src-1"} in where["$and"] and {"type": "problem"} in where["$and"]
    assert score == 80.0


def test_the_quality_score_route_requires_a_source():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[check_admin_permission] = lambda: True
    response = TestClient(app, raise_server_exceptions=False).get("/code/metrics/quality-score")
    assert response.status_code == 422
