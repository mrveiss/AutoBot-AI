# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Negative fixture (router_registry): descriptive prefixes — no violations."""

# Registry-config tuples using descriptive/domain-adjective prefixes — not flagged.
ROUTER_CONFIGS = [
    ("api.analytics_reporting", "/reporting", ["analytics-reporting", "analytics"], "analytics_reporting"),
    ("api.stats", "/advanced-stats", ["stats"], "stats"),
]

# include_router with descriptive prefix — also not flagged.
router = object()


def setup_routes(app):
    app.include_router(router, prefix="/reporting")
