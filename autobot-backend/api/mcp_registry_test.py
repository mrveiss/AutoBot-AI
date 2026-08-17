# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every discovered MCP bridge has a declared default permission (#14420 review).

`autobot_shared.auth.mcp_tool_permissions_test.test_every_bridge_has_a_default`
already guards the 11 static bridges by parsing `autobot-backend/api/*_mcp.py`
sources offline. That check cannot see a bridge that only exists via the
`autobot.mcp_bridges` entry-point group (a plugin, no local `*_mcp.py` file to
parse) — there are no registrants there today, so the gap is latent.

`required_permission()` resolves an unmapped bridge to `None`, and
`PermissionEnforcementExtension` (#14420) reads a `None` `tool_permission` as
"undeclared/legacy, allow" — for every role, including unauthenticated. A
bridge added tomorrow via the entry-point path with no
`BRIDGE_DEFAULT_PERMISSIONS` entry would be silently permissive from day one.

This test reads the same `MCP_BRIDGES` list `_build_tool_entry` resolves
`required_permission` against, so entry-point-discovered bridges are covered
too, not just the module-scan fallback.
"""

from api.mcp_registry import MCP_BRIDGES
from autobot_shared.auth.mcp_tool_permissions import BRIDGE_DEFAULT_PERMISSIONS


def test_every_discovered_bridge_has_a_default_permission():
    """A discovered bridge with no default resolves every one of its tools to
    `required_permission() is None`, which reads as an unconditional allow —
    not the "absence is a denial" `mcp_tool_permissions` documents."""
    discovered = {name for name, _desc, _endpoint, _features in MCP_BRIDGES}
    missing = discovered - set(BRIDGE_DEFAULT_PERMISSIONS)

    assert not missing, (
        f"bridge(s) discovered with no BRIDGE_DEFAULT_PERMISSIONS entry: {sorted(missing)} — "
        "every tool on an unmapped bridge silently allows any role, including unauthenticated"
    )


def test_mcp_bridges_is_actually_populated():
    """Guard the guard: an empty MCP_BRIDGES would make the assertion above
    vacuous — discovery failing silently must not read as 'nothing to check'."""
    assert len(MCP_BRIDGES) >= 10, f"only {len(MCP_BRIDGES)} bridges discovered — did discovery break?"
