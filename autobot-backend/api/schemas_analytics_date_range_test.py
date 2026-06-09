# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for DateRangeParams FastAPI dependency helper (#7110)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

# Ensure autobot-backend is on path so `api.schemas_analytics` resolves both
# when run from the colocated-test root and from a clean pytest session.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from api.schemas_analytics import DateRangeParams  # noqa: E402

# ---------------------------------------------------------------------------
# Direct-instantiation contract — needed for unit tests / non-HTTP callers
# ---------------------------------------------------------------------------


def test_date_range_params_defaults_to_none() -> None:
    """Direct call without args must yield real None defaults, not Query placeholders.

    The Annotated[..., Query(...)] form (vs Query(None) as default value) is
    what makes this work — verified to prevent regression to the older shape.
    """
    r = DateRangeParams()
    assert r.start_date is None
    assert r.end_date is None


def test_date_range_params_explicit_values() -> None:
    r = DateRangeParams(start_date="2026-01-01", end_date="2026-12-31")
    assert r.start_date == "2026-01-01"
    assert r.end_date == "2026-12-31"


def test_date_range_params_partial_values() -> None:
    """Either field may be set independently."""
    r = DateRangeParams(start_date="2026-01-01")
    assert r.start_date == "2026-01-01"
    assert r.end_date is None

    r = DateRangeParams(end_date="2026-12-31")
    assert r.start_date is None
    assert r.end_date == "2026-12-31"


# ---------------------------------------------------------------------------
# FastAPI Depends() integration — query params bind correctly
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_with_endpoint() -> FastAPI:
    app = FastAPI()

    @app.get("/test")
    def endpoint(date_range: DateRangeParams = Depends()):
        return {"start": date_range.start_date, "end": date_range.end_date}

    return app


def test_fastapi_binds_both_query_params(app_with_endpoint: FastAPI) -> None:
    client = TestClient(app_with_endpoint)
    r = client.get("/test?start_date=2026-01-01&end_date=2026-12-31")
    assert r.status_code == 200
    assert r.json() == {"start": "2026-01-01", "end": "2026-12-31"}


def test_fastapi_binds_no_query_params(app_with_endpoint: FastAPI) -> None:
    client = TestClient(app_with_endpoint)
    r = client.get("/test")
    assert r.status_code == 200
    assert r.json() == {"start": None, "end": None}


def test_fastapi_binds_partial_query_params(app_with_endpoint: FastAPI) -> None:
    client = TestClient(app_with_endpoint)
    r = client.get("/test?start_date=2026-06-01")
    assert r.status_code == 200
    assert r.json() == {"start": "2026-06-01", "end": None}


def test_fastapi_openapi_schema_marks_query_params(app_with_endpoint: FastAPI) -> None:
    """OpenAPI schema must list start_date / end_date as query params (`in: query`)."""
    schema = app_with_endpoint.openapi()
    params = schema["paths"]["/test"]["get"]["parameters"]
    by_name = {p["name"]: p for p in params}
    assert by_name["start_date"]["in"] == "query"
    assert by_name["end_date"]["in"] == "query"
    assert by_name["start_date"].get("required", False) is False
    assert "Start date" in by_name["start_date"]["description"]
