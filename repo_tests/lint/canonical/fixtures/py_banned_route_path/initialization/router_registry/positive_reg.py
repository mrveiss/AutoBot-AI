# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Positive fixture (router_registry): era-marker registry prefix + include_router prefix."""

# Surface 3: registry-config tuple where 2nd element is an era-marker mount prefix.
ROUTER_CONFIGS = [
    ("api.search", "/enhanced-search", ["search"], "search"),
]

# Surface 2: include_router with era-marker prefix (detected in any file including registry files).
router = object()


def setup_routes(app):
    app.include_router(router, prefix="/unified-api")
