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

    from api.codebase_analytics.endpoints.shared import require_source_access
    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[check_admin_permission] = lambda: True
    # Isolate the query validation from the route-level source-access dependency.
    app.dependency_overrides[require_source_access] = lambda: None
    response = TestClient(app, raise_server_exceptions=False).get("/code/metrics/quality-score")
    assert response.status_code == 422


def test_an_unresolvable_source_is_a_404_for_the_quality_score():
    import asyncio
    from unittest.mock import AsyncMock

    import pytest

    from api.codebase_analytics.endpoints.shared import UnresolvedSourceError

    with patch.object(
        mod, "resolve_scan_root", new=AsyncMock(side_effect=UnresolvedSourceError("src-x"))
    ):
        with pytest.raises(UnresolvedSourceError) as exc:
            asyncio.run(mod.get_code_quality_score(source_id="src-x", admin_check=True))
    assert exc.value.status_code == 404


def test_one_sources_analysis_is_never_served_for_another(tmp_path):
    import asyncio
    from unittest.mock import AsyncMock

    state = {"code_analysis_cache": {}, "last_analysis_time": None}
    roots = {"src-a": tmp_path / "a", "src-b": tmp_path / "b"}
    scanned = []

    class Controller:
        async def perform_code_analysis(self, request, source_id):
            scanned.append((source_id, request.target_path))
            result = {"timestamp": f"t-{source_id}", "codebase_metrics": {"total_files": len(scanned)}}
            state["code_analysis_cache"][source_id] = result
            return result

    async def root_of(source_id):
        return roots[source_id]

    async def score(source_id):
        return await mod.get_code_quality_score(source_id=source_id, admin_check=True)

    with (
        patch.object(mod, "analytics_state", state),
        patch.object(mod, "analytics_controller", Controller()),
        patch.object(mod, "resolve_scan_root", new=AsyncMock(side_effect=root_of)),
    ):
        first = asyncio.run(score("src-a"))
        second = asyncio.run(score("src-b"))
        again = asyncio.run(score("src-a"))
    assert first["last_analysis"] == "t-src-a" and second["last_analysis"] == "t-src-b"
    assert scanned == [("src-a", str(roots["src-a"])), ("src-b", str(roots["src-b"]))]  # A reused, B scanned itself
    assert again["last_analysis"] == "t-src-a"
