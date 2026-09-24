# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
HTTP-layer 422 validation tests for the Marketplace API (GH#7328).

Uses FastAPI TestClient to verify that invalid ``category`` and ``sort_by``
query parameters return HTTP 422 Unprocessable Entity with a meaningful error
body — not a 500 or silent coercion.

These complement the enum-level unit tests already in tests/api/test_marketplace.py
which only exercise the Pydantic enum directly.

NOTE: We define a minimal test app using the same enums (same values) as the
real marketplace endpoint rather than importing the full ``api.marketplace``
router, which pulls in the entire AutoBot application stack and requires a
running config/database. The enum types and their valid values are the exact
ones defined in api/marketplace.py (CatalogCategory, CatalogSort — added in
Issue #6534); any change there must be reflected here.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient

# #14881: the real enums, not a copy. This module used to redeclare both with a
# comment promising they were "kept in sync by the test assertions below" --
# see TestEnumParity's removal note below for why that promise could not hold.
# tests/api/test_marketplace.py already imports these at module level, so the
# import is proven safe in this environment rather than assumed.
from api.marketplace import CatalogCategory, CatalogSort

# ---------------------------------------------------------------------------
# Minimal test app — mirrors the real /catalog endpoint's query-param contract
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    """Return a minimal FastAPI app whose /catalog endpoint validates the same
    query params as the real marketplace router."""
    app = FastAPI()

    @app.get("/catalog")
    async def list_catalog(
        category: CatalogCategory = Query(default=CatalogCategory.ALL),
        sort_by: CatalogSort = Query(default=CatalogSort.DOWNLOADS),
        search: str | None = Query(default=None),
    ) -> dict:
        return {"category": category.value, "sort_by": sort_by.value}

    return app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(_make_app(), raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# TestEnumParity removed (#14881)
# ---------------------------------------------------------------------------
# It was titled "Verify our local enums exactly match the real marketplace
# enums" and its docstring said "These tests fail immediately when the real
# enums diverge from our copy". Neither was true: both methods compared this
# file's local copy against a THIRD hardcoded literal set written a few lines
# below it, and never imported api/marketplace.py at all. A value added to or
# removed from the real enum was invisible to them -- a test asserting a
# literal against a literal, in the name of catching drift.
#
# Deleting rather than repairing it is the point. With the enums imported
# above, parity is structural: `_make_app()` now validates against the same
# class the real /catalog endpoint does, so a divergence cannot exist to be
# asserted about, and the 422 cases below exercise the real vocabulary.

# ---------------------------------------------------------------------------
# Invalid category → 422
# ---------------------------------------------------------------------------


class TestInvalidCategory422:
    """GH#7328 — invalid category query param must yield HTTP 422."""

    def test_invalid_category_returns_422(self, client: TestClient):
        resp = client.get("/catalog?category=totally_invalid")
        assert resp.status_code == 422

    def test_invalid_category_response_is_json(self, client: TestClient):
        resp = client.get("/catalog?category=__bad__")
        assert resp.headers.get("content-type", "").startswith("application/json")

    def test_invalid_category_error_body_mentions_field(self, client: TestClient):
        """FastAPI validation errors include the offending field name."""
        resp = client.get("/catalog?category=NOTACAT")
        body = resp.json()
        assert "detail" in body
        detail_str = str(body["detail"]).lower()
        assert "category" in detail_str

    def test_valid_category_all_returns_200(self, client: TestClient):
        resp = client.get("/catalog?category=all")
        assert resp.status_code == 200

    def test_valid_category_analytics_returns_200(self, client: TestClient):
        resp = client.get("/catalog?category=analytics")
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "bad_value",
        ["INVALID", "null", "0", "[]", "true", "other_bad"],
    )
    def test_various_invalid_categories_return_422(self, client: TestClient, bad_value: str):
        resp = client.get(f"/catalog?category={bad_value}")
        assert resp.status_code == 422, f"Expected 422 for category={bad_value!r}, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Invalid sort_by → 422
# ---------------------------------------------------------------------------


class TestInvalidSortBy422:
    """GH#7328 — invalid sort_by query param must yield HTTP 422."""

    def test_invalid_sort_by_returns_422(self, client: TestClient):
        resp = client.get("/catalog?sort_by=totally_invalid")
        assert resp.status_code == 422

    def test_invalid_sort_by_response_is_json(self, client: TestClient):
        resp = client.get("/catalog?sort_by=__bad__")
        assert resp.headers.get("content-type", "").startswith("application/json")

    def test_invalid_sort_by_error_body_mentions_field(self, client: TestClient):
        """FastAPI validation errors include the offending field name."""
        resp = client.get("/catalog?sort_by=NOTAFIELD")
        body = resp.json()
        assert "detail" in body
        detail_str = str(body["detail"]).lower()
        assert "sort_by" in detail_str

    def test_valid_sort_by_downloads_returns_200(self, client: TestClient):
        resp = client.get("/catalog?sort_by=downloads")
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "bad_value",
        ["INVALID", "date", "popularity", "random", "1", "null"],
    )
    def test_various_invalid_sort_by_return_422(self, client: TestClient, bad_value: str):
        resp = client.get(f"/catalog?sort_by={bad_value}")
        assert resp.status_code == 422, f"Expected 422 for sort_by={bad_value!r}, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Both invalid simultaneously → 422 (first error wins, still 422)
# ---------------------------------------------------------------------------


class TestBothParamsInvalid:
    """GH#7328 — both bad params together still return 422."""

    def test_both_invalid_returns_422(self, client: TestClient):
        resp = client.get("/catalog?category=bad&sort_by=worse")
        assert resp.status_code == 422

    def test_both_invalid_error_body_has_multiple_errors(self, client: TestClient):
        """FastAPI collects all validation errors in a single 422 response."""
        resp = client.get("/catalog?category=bad&sort_by=worse")
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], list)
        assert len(body["detail"]) >= 2
