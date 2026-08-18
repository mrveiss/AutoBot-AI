# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every discovered MCP bridge has a declared default permission (#14420 review,
runtime denial landed at #14523).

`autobot_shared.auth.mcp_tool_permissions_test.test_every_bridge_has_a_default`
already guards the 11 static bridges by parsing `autobot-backend/api/*_mcp.py`
sources offline. That check cannot see a bridge that only exists via the
`autobot.mcp_bridges` entry-point group (a plugin, no local `*_mcp.py` file to
parse) — there are no registrants there today, so the gap is latent.

Before #14523, `required_permission()` resolved an unmapped bridge to `None`,
and `PermissionEnforcementExtension` read that `None` as "undeclared/legacy,
allow" — for every role, including unauthenticated. A bridge added via the
entry-point path with no exact `TOOL_PERMISSIONS`/`BRIDGE_DEFAULT_PERMISSIONS`
entry would have been silently permissive from day one. #14523 makes
`required_permission()` refuse any undeclared tool regardless of bridge, so an
entry-point bridge missing here is no longer a silent grant — it is refused
outright. This test stays: `BRIDGE_DEFAULT_PERMISSIONS` is still the registry
every governed bridge must join, and a bridge nobody registered here is a
governance gap even though it can no longer be exploited as an under-grant.

This test reads the same `MCP_BRIDGES` list `_build_tool_entry` resolves
`required_permission` against, so entry-point-discovered bridges are covered
too, not just the module-scan fallback.
"""

from api.mcp_registry import MCP_BRIDGES
from autobot_shared.auth.mcp_tool_permissions import BRIDGE_DEFAULT_PERMISSIONS


def test_every_discovered_bridge_has_a_default_permission():
    """A discovered bridge missing from `BRIDGE_DEFAULT_PERMISSIONS` is refused
    outright at runtime since #14523 (no fallback grant left to inherit) —
    this stays as the registry gate: every bridge `_build_tool_entry` resolves
    a tool against must be acknowledged here, or its tools work for nobody."""
    discovered = {name for name, _desc, _endpoint, _features in MCP_BRIDGES}
    missing = discovered - set(BRIDGE_DEFAULT_PERMISSIONS)

    assert not missing, (
        f"bridge(s) discovered with no BRIDGE_DEFAULT_PERMISSIONS entry: {sorted(missing)} — "
        "every tool on an unregistered bridge is refused outright (#14523); register the bridge "
        "here and declare its tools in TOOL_PERMISSIONS."
    )


def test_mcp_bridges_is_actually_populated():
    """Guard the guard: an empty MCP_BRIDGES would make the assertion above
    vacuous — discovery failing silently must not read as 'nothing to check'."""
    assert len(MCP_BRIDGES) >= 10, f"only {len(MCP_BRIDGES)} bridges discovered — did discovery break?"
