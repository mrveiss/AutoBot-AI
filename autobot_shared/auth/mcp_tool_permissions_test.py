# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every MCP tool declares a permission that exists (#13228).

The defect was a seven-entry Redis substring blocklist governing all eleven
bridges, default-allow. The risk in replacing it is a *different* silent failure:
a declaration that names a permission the enum does not have, or a bridge whose
tools nobody declared. Both are checked here, offline — the bridge sources are
parsed rather than a live registry queried, so this runs in CI without a backend.
"""

import pathlib
import re

import pytest

from autobot_shared.auth.mcp_tool_permissions import (
    BRIDGE_DEFAULT_PERMISSIONS,
    TOOL_PERMISSIONS,
    required_permission,
)
from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role

_BRIDGE_DIR = pathlib.Path(__file__).resolve().parents[2] / "autobot-backend" / "api"

# Tool names declared as `("name", "description", {...})` tuples, or `name="..."`.
_TUPLE_TOOL = re.compile(r'^\s{4}\(\s*\n\s{8}"([a-z0-9_]+)"', re.M)
_KWARG_TOOL = re.compile(r'name="([a-z0-9_]+)"')


def _bridge_files():
    """Every bridge's tool-declaring source, module- or package-shaped.

    #13228: globbing only ``*_mcp.py`` silently omitted ``redis_mcp``, which is a
    package (``api/redis_mcp/tools.py``). The omission was invisible precisely
    because these guards iterate over whatever this function returns — a bridge it
    cannot see is a bridge every coverage test below reports as fine. All 25 redis
    tools were undeclared and no test said so.
    """
    modules = [p for p in _BRIDGE_DIR.glob("*_mcp.py") if p.stem != "manual_mcp"]
    packages = [p / "tools.py" for p in _BRIDGE_DIR.glob("*_mcp") if p.is_dir() and (p / "tools.py").is_file()]
    return sorted(modules + packages)


def _bridge_name(path: pathlib.Path) -> str:
    """The bridge a source file belongs to (``redis_mcp/tools.py`` → ``redis_mcp``)."""
    return path.parent.name if path.stem == "tools" else path.stem


def _declared_tools(path: pathlib.Path) -> set:
    """Tool names a bridge module declares, minus the bridge's own name."""
    src = path.read_text(encoding="utf-8")
    names = set(_TUPLE_TOOL.findall(src)) or set(_KWARG_TOOL.findall(src))
    return {n for n in names if n != _bridge_name(path)}


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
    bridges = {_bridge_name(p) for p in _bridge_files()}

    assert not (
        bridges - set(BRIDGE_DEFAULT_PERMISSIONS)
    ), f"bridges with no declared default: {sorted(bridges - set(BRIDGE_DEFAULT_PERMISSIONS))}"


def test_the_bridge_sources_are_actually_being_read():
    """Guard the guard: a parser that finds nothing would pass everything."""
    found = {_bridge_name(p): _declared_tools(p) for p in _bridge_files()}
    total = sum(len(v) for v in found.values())

    assert total > 50, f"only {total} tool names extracted — the parser stopped matching: {found}"


# Verbs that mean a tool changes state, sends a body, or drives input. A tool
# named with one of these must carry an EXPLICIT entry — inheriting its bridge's
# read-level baseline is the silent under-grant this issue exists to prevent.
_MUTATING = (
    "write",
    "delete",
    "remove",
    "create",
    "edit",
    "move",
    "execute",
    "set",
    "post",
    "put",
    "patch",
    "click",
    "type",
    "fill",
    "hover",
    "evaluate",
    "flush",
    "crawl",
    "add_",
)


@pytest.mark.parametrize("bridge", [_bridge_name(p) for p in _bridge_files()])
def test_state_changing_tools_carry_an_explicit_declaration(bridge):
    """A mutating tool must not silently inherit a read-level bridge default.

    Checking `required_permission(...) is not None` would be tautological — every
    known bridge has a default, so nothing on one can resolve to None. The real
    risk is a write tool quietly inheriting read, which is what this catches.
    """
    path = next(p for p in _bridge_files() if _bridge_name(p) == bridge)
    inheriting = [
        t for t in sorted(_declared_tools(path)) if any(verb in t for verb in _MUTATING) and t not in TOOL_PERMISSIONS
    ]

    assert not inheriting, f"{bridge}: mutating tools inheriting a read default: {inheriting}"


# -------------------------------------------------------- resolution rules


def test_an_exact_tool_entry_beats_its_bridge_default():
    """A destructive tool must not inherit its bridge's read-level baseline."""
    assert required_permission("database_execute", "database_mcp") == Permission.MCP_DATABASE_WRITE
    assert required_permission("database_query", "database_mcp") == Permission.MCP_DATABASE_READ


def test_an_unknown_bridge_resolves_to_none():
    """None is what stage 3 refuses — the inversion this issue is about."""
    assert required_permission("whatever", "not_a_bridge") is None


def test_an_undeclared_tool_on_a_known_bridge_inherits_the_least_privilege():
    """A tool added tomorrow under-grants rather than over-grants."""
    assert required_permission("some_future_tool", "browser_mcp") == Permission.MCP_BROWSER_READ


def test_the_old_blocklist_tools_still_require_management():
    """The blocklist's *real* targets keep their grant, under their real names.

    The legacy gate matched by substring, so its pattern ``client_list`` covered the
    tool actually named ``redis_client_list``. Declaring the pattern rather than the
    tool left exact lookup finding nothing — the bug this asserts against.
    """
    for name in ("redis_client_list", "redis_slowlog"):
        assert required_permission(name, "redis_mcp") == Permission.MCP_MANAGE, name


def test_the_blocklist_patterns_that_name_no_tool_are_still_declared():
    """``flushall`` and friends match nothing the redis bridge registers today.

    So the old gate protected nothing. Kept declared anyway: if one is ever added,
    it arrives admin-only rather than arriving undeclared.
    """
    registered = _declared_tools(_BRIDGE_DIR / "redis_mcp" / "tools.py")

    for name in ("config_set", "config_rewrite", "debug", "flushdb", "flushall"):
        assert name not in registered, f"{name} now exists — fold it into the real-name test above"
        assert required_permission(name, "redis_mcp") == Permission.MCP_MANAGE, name


def test_browser_evaluate_is_not_a_read():
    """`evaluate` runs caller-supplied JavaScript; it read as an ordinary user tool."""
    assert required_permission("evaluate", "browser_mcp") == Permission.MCP_BROWSER_CONTROL


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
