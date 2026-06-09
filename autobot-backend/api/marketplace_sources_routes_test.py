# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#6523: regression tests for marketplace_sources router prefix.

Pin the fix: marketplace_sources routes must be reachable under their
own prefix (`/marketplace-sources`) rather than under `/plugins`, where
they were shadowed by `plugin_manager`'s `/plugins/{plugin_name}`
wildcard (registered earlier — first-match wins under Starlette).
"""

import pytest


def _registered_paths(router):
    """Extract path strings from an APIRouter's routes."""
    return [r.path for r in router.routes]


def test_marketplace_sources_router_has_no_inner_marketplaces_prefix():
    """Inner routes use root + `/{source_id}`; the `/marketplace-sources`
    prefix is applied at registration time, not duplicated inside the file.

    Pre-#6523: inner paths were `/marketplaces` + `/marketplaces/{source_id}`,
    which combined with prefix `/plugins` produced `/plugins/marketplaces` —
    masked by `plugin_manager`'s wildcard catch.
    """
    from api.marketplace_sources import router

    paths = _registered_paths(router)
    # Three routes: list, add (both ""), delete ("/{source_id}").
    assert "" in paths, f"Expected empty inner-path for list/add; got {paths}"
    assert "/{source_id}" in paths, f"Expected /{{source_id}} for delete; got {paths}"
    # Pin the regression: the buggy inner shape must not return.
    assert "/marketplaces" not in paths, (
        "Inner path `/marketplaces` would re-create the #6523 collision when " "combined with prefix `/plugins`."
    )
    assert "/marketplaces/{source_id}" not in paths


def test_feature_routers_registers_marketplace_sources_off_plugins():
    """Registry config must NOT mount marketplace_sources under `/plugins`.

    Re-introducing prefix `/plugins` would let `plugin_manager`'s
    wildcard `/plugins/{plugin_name}` shadow these routes again.
    """
    from initialization.router_registry.feature_routers import (
        FEATURE_ROUTER_CONFIGS,
    )

    by_name = {entry[0]: entry for entry in FEATURE_ROUTER_CONFIGS}
    assert "api.marketplace_sources" in by_name, "marketplace_sources missing from registry"
    _, prefix, _, _ = by_name["api.marketplace_sources"]
    assert prefix != "/plugins", "#6523 regression: prefix `/plugins` collides with plugin_manager wildcard"
    assert prefix == "/marketplace-sources", f"Expected `/marketplace-sources`; got {prefix!r}"


def test_plugin_manager_wildcard_still_present():
    """Sanity check: plugin_manager's `/plugins/{plugin_name}` wildcard
    still exists — we did NOT fix the collision by removing the wildcard
    side, only by relocating marketplace_sources off the conflicting prefix.
    """
    pytest.importorskip("plugin_manager")
    from plugin_manager import router

    paths = _registered_paths(router)
    assert any("/plugins/{plugin_name}" in p for p in paths), (
        "plugin_manager wildcard expected — if removed, the #6523 fix "
        "rationale changes (fix shouldn't be reverted casually)."
    )
