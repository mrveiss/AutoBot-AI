# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The missing-endpoints report must not manufacture findings (#12745).

On a real source it reported 2400 missing endpoints, of which 97.4% actually
existed in the live OpenAPI. The cause was a backend scan that returned zero
routes: with an empty endpoint map every frontend call matches nothing, so the
comparison reported the entire call surface as drift.
"""

import pytest

from api.codebase_analytics.api_endpoint_scanner import EndpointMatcher


def _Scanner(endpoints, calls):
    """EndpointMatcher owns the comparison; it takes data directly, no filesystem."""
    return EndpointMatcher(endpoints=endpoints, calls=calls)


def _call(path, method="GET", dynamic=False):
    from api.codebase_analytics.models import FrontendAPICallItem

    return FrontendAPICallItem(
        method=method,
        path=path,
        file_path="src/views/Thing.vue",
        line_number=42,
        is_dynamic=dynamic,
    )


# ---------------------------------------------------------------------------
# The zero-scan guard
# ---------------------------------------------------------------------------


def test_empty_endpoint_map_reports_a_scan_error_not_mass_drift():
    calls = [_call(f"/api/thing/{i}") for i in range(50)]
    result = _Scanner([], calls).analyze()

    assert result.missing_endpoints == 0, "an empty scan must not report every call as missing"
    assert result.missing == []
    assert result.scan_error, "the failure must be surfaced, not silently reported as a clean run"
    assert "0 routes" in result.scan_error
    # The calls themselves are still reported, so the data is not lost.
    assert result.frontend_calls == 50


def test_empty_scan_does_not_look_like_a_healthy_report():
    """Zero missing WITHOUT scan_error would read as 'no drift' — the opposite of true."""
    result = _Scanner([], [_call("/api/x/y")]).analyze()

    assert result.backend_endpoints == 0
    assert result.coverage_percentage == 0.0
    assert result.scan_error is not None


# ---------------------------------------------------------------------------
# De-noising
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,reportable",
    [
        ("/api/users/profile", True),
        ("/api/adapters/", False),  # base-path fragment from URL concatenation
        ("/api/secrets/", False),
        ("/endpoint", False),  # docstring example, never an API path
        ("/save", False),
        ("", False),
        ("/api/llc/projects/x", True),
    ],
)
def test_only_real_api_paths_are_reportable(path, reportable):
    assert EndpointMatcher._is_reportable_call(path) is reportable


def test_noise_paths_are_excluded_from_the_missing_report():
    from api.codebase_analytics.models import APIEndpointItem

    endpoints = [
        APIEndpointItem(
            method="GET",
            path="/api/users/profile",
            file_path="api/users.py",
            line_number=1,
            function_name="get_profile",
        )
    ]
    calls = [
        _call("/api/users/profile"),  # matches
        _call("/api/adapters/"),  # noise
        _call("/endpoint"),  # noise
        _call("/api/genuinely/absent"),  # real drift
    ]

    result = _Scanner(endpoints, calls).analyze()

    missing_paths = [m.path for m in result.missing]
    assert missing_paths == ["/api/genuinely/absent"]


def test_a_matched_call_is_never_reported_missing():
    from api.codebase_analytics.models import APIEndpointItem

    endpoints = [
        APIEndpointItem(method="GET", path="/api/a/b", file_path="api/a.py", line_number=1, function_name="ab")
    ]
    result = _Scanner(endpoints, [_call("/api/a/b")]).analyze()

    assert result.missing == []
    assert result.used_endpoints == 1
    assert result.scan_error is None
