# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Developer-mode error helpers match concrete paths against route templates (#22280)."""

from api.developer import allowed_methods_for_path

_ENDPOINTS = [
    {"path": "/items/{id}", "method": "GET"},
    {"path": "/items/{id}", "method": "DELETE"},
    {"path": "/health", "method": "GET"},
]


def test_a_concrete_path_matches_its_route_template():
    assert allowed_methods_for_path(_ENDPOINTS, "/items/42") == ["GET", "DELETE"]


def test_a_literal_route_matches_only_itself():
    assert allowed_methods_for_path(_ENDPOINTS, "/health") == ["GET"]
    assert allowed_methods_for_path(_ENDPOINTS, "/health/extra") == []


def test_a_path_no_route_matches_has_no_methods():
    assert allowed_methods_for_path(_ENDPOINTS, "/nothing") == []
