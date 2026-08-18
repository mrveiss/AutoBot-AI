# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every MCP tool declares a permission that exists (#13228, #14494).

The defect was a seven-entry Redis substring blocklist governing all eleven
bridges, default-allow. The risk in replacing it is a *different* silent failure:
a declaration that names a permission the enum does not have, or a bridge whose
tools nobody declared. Both are checked here, offline — the bridge sources are
parsed rather than a live registry queried, so this runs in CI without a backend.

#14494 retired the guard that used to sit at the bottom of this file
(``_MUTATING``, a hand-written verb tuple matched against a tool's name). It
caught an under-grant only when a tool's name happened to contain the right
verb — ``select`` did not, and inherited MCP_BROWSER_READ despite changing a
dropdown's value (#14469) — so the coverage it looked like it provided was an
illusion the moment a bridge added a tool named something else. The guard that
replaces it, ``tools/lint/check_mcp_tool_permission_coverage.py`` (a required
check, because the pytest copy of a guard like this gates nothing — #14353),
requires every live tool to be an *exact* key in ``TOOL_PERMISSIONS``: no verb
list to dodge, only a missing entry.
"""

import importlib.util
import pathlib

import pytest

from autobot_shared.auth.mcp_bridge_scan import bridge_files, bridge_name, declared_tools
from autobot_shared.auth.mcp_tool_permissions import (
    _DECLARED_AHEAD_OF_TIME,
    BRIDGE_DEFAULT_PERMISSIONS,
    TOOL_PERMISSIONS,
    required_permission,
)
from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role

_BRIDGE_DIR = pathlib.Path(__file__).resolve().parents[2] / "autobot-backend" / "api"
_CHECKER_PATH = pathlib.Path(__file__).resolve().parents[2] / "tools" / "lint" / "check_mcp_tool_permission_coverage.py"


def _load_coverage_checker():
    """Import the required-check script by path — tools/lint is not a package.

    The decision that blocks a merge lives in that script, not here. Restating
    the comparison would give the guard two definitions that could drift; this
    runs the exact copy CI executes.
    """
    spec = importlib.util.spec_from_file_location("_mcp_coverage_checker", _CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------- the declarations


@pytest.mark.parametrize("perm", sorted(TOOL_PERMISSIONS.values(), key=lambda p: p.value))
def test_every_declared_tool_permission_exists_in_the_enum(perm):
    """AC: every `required_permission` is a real `Permission` member."""
    assert perm in set(Permission)


@pytest.mark.parametrize("perm", sorted(BRIDGE_DEFAULT_PERMISSIONS.values(), key=lambda p: p.value))
def test_every_bridge_default_exists_in_the_enum(perm):
    assert perm in set(Permission)


def test_every_declared_permission_is_granted_to_some_role():
    """A permission no role holds denies everyone — a broken grant, not a strict one."""
    granted = {p for perms in ROLE_PERMISSIONS.values() for p in perms}
    declared = set(TOOL_PERMISSIONS.values()) | set(BRIDGE_DEFAULT_PERMISSIONS.values())

    assert not (declared - granted), f"declared but held by no role: {sorted(p.value for p in declared - granted)}"


# ------------------------------------------------------------- coverage


def test_every_bridge_has_a_default():
    """A bridge with no default leaves its whole tool surface undeclared."""
    bridges = {bridge_name(p) for p in bridge_files()}

    assert not (
        bridges - set(BRIDGE_DEFAULT_PERMISSIONS)
    ), f"bridges with no declared default: {sorted(bridges - set(BRIDGE_DEFAULT_PERMISSIONS))}"


def test_the_bridge_sources_are_actually_being_read():
    """Guard the guard: a parser that finds nothing would pass everything."""
    found = {bridge_name(p): declared_tools(p) for p in bridge_files()}
    total = sum(len(v) for v in found.values())

    assert total > 50, f"only {total} tool names extracted — the parser stopped matching: {found}"


def test_every_live_tool_carries_an_explicit_declaration():
    """#14494: the actual required-check guard, run against the real tree.

    No verb list — a mutating tool named something the retired guard never
    matched (this pass found `intercept_api` and `desktop_special_key`) can no
    longer inherit its bridge's read-level default silently: an undeclared tool
    is a failure here, not a fallback.
    """
    checker = _load_coverage_checker()
    reached, problems = checker.audit()

    assert reached >= checker.DISCOVERY_FLOOR, "the bridge scan reached too few tools — see the checker's own floor"
    assert not problems, "\n\n".join(problems)


# -------------------------------------------------------- resolution rules


def test_an_exact_tool_entry_beats_its_bridge_default():
    """A destructive tool must not inherit its bridge's read-level baseline."""
    assert required_permission("database_execute", "database_mcp") == Permission.MCP_DATABASE_WRITE
    assert required_permission("database_query", "database_mcp") == Permission.MCP_DATABASE_READ


def test_an_unknown_bridge_resolves_to_none():
    """None is what stage 3 refuses — the inversion this issue is about."""
    assert required_permission("whatever", "not_a_bridge") is None


def test_an_undeclared_tool_on_a_known_bridge_inherits_the_least_privilege():
    """A tool `required_permission` has never heard of under-grants rather than
    over-grants. `tools/lint/check_mcp_tool_permission_coverage.py` is what stops
    a REAL tool from staying in this state (#14494) — this pins the fallback
    itself, which stays in place as defense-in-depth."""
    assert required_permission("some_future_tool", "browser_mcp") == Permission.MCP_BROWSER_READ


def test_the_old_blocklist_tools_still_require_management():
    """The blocklist's *real* targets keep their grant, under their real names.

    The legacy gate matched by substring, so its pattern ``client_list`` covered the
    tool actually named ``redis_client_list``. Declaring the pattern rather than the
    tool left exact lookup finding nothing — the bug this asserts against.
    """
    for name in ("redis_client_list", "redis_slowlog"):
        assert required_permission(name, "redis_mcp") == Permission.MCP_MANAGE, name


@pytest.mark.parametrize("name,bridge", sorted(_DECLARED_AHEAD_OF_TIME.items()))
def test_declared_ahead_of_time_tools_still_name_no_live_tool(name, bridge):
    """Every ``_DECLARED_AHEAD_OF_TIME`` entry matches nothing a real bridge
    registers today — ``flushall`` and friends match nothing ``redis_mcp``
    registers, and ``delete_file`` matches nothing ``filesystem_mcp`` registers.
    Kept declared anyway: if one of these ships, it arrives at its intended
    permission instead of arriving undeclared. If this fails, the tool now
    exists — fold it into a real-name test above with its own reasoned entry,
    the way #14469's `select` and this pass's `intercept_api` were."""
    path = next(p for p in bridge_files() if bridge_name(p) == bridge)
    registered = declared_tools(path)

    assert name not in registered, f"{name} now exists on {bridge} — it needs its own declaration, not this exemption"


def test_browser_evaluate_is_not_a_read():
    """`evaluate` runs caller-supplied JavaScript; it read as an ordinary user tool."""
    assert required_permission("evaluate", "browser_mcp") == Permission.MCP_BROWSER_CONTROL


def test_browser_select_is_not_a_read():
    """#14469: `select` changes a dropdown's value, same as click/fill — its name
    carried none of the retired name-matching guard's verbs, so it silently
    inherited the bridge's read-level default until declared here explicitly."""
    assert required_permission("select", "browser_mcp") == Permission.MCP_BROWSER_CONTROL
    assert required_permission("select_index", "browser_mcp") == Permission.MCP_BROWSER_CONTROL


def test_browser_intercept_api_is_not_a_read():
    """#14494: found declared under a name (`intercept_requests`) the bridge does
    not register — the real tool is `intercept_api`, which injects an
    interceptor script into the page (`page.add_init_script`), the same category
    of action as `evaluate`. It had never actually been declared."""
    assert required_permission("intercept_api", "browser_mcp") == Permission.MCP_BROWSER_CONTROL
    assert "intercept_requests" not in TOOL_PERMISSIONS


def test_desktop_special_key_is_not_a_read():
    """#14494: sends key combinations (Return, Escape, ctrl+c, alt+tab …) to the
    desktop — the same category as desktop_keyboard_type — and was undeclared."""
    assert required_permission("desktop_special_key", "vnc_mcp") == Permission.MCP_DESKTOP_CONTROL


def test_knowledge_redis_vector_operations_is_not_a_read():
    """#14494: `operation` can be "flush", "reindex" or "backup", not only "info"
    — a tool whose worst case empties the vector store, undeclared and therefore
    reachable with mere KNOWLEDGE_READ."""
    assert required_permission("redis_vector_operations", "knowledge_mcp") == Permission.KNOWLEDGE_MANAGE


def test_readonly_holds_no_control_grant():
    """The role split has to mean something at the weakest role."""
    readonly = set(ROLE_PERMISSIONS[Role.READONLY])

    for control in (
        Permission.MCP_BROWSER_CONTROL,
        Permission.MCP_DATABASE_WRITE,
        Permission.MCP_HTTP_WRITE,
        Permission.MCP_DESKTOP_CONTROL,
    ):
        assert control not in readonly, control
