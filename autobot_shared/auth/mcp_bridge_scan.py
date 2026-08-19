# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Static scan of MCP bridge sources for the tool names they register (#14494).

Extracted from ``mcp_tool_permissions_test.py`` (#13228) so the coverage guard
that has to run as a required check (``tools/lint/check_mcp_tool_permission_coverage.py``)
and the pytest guards that exercise the same data read the identical answer.
Two parsers of the same source text can drift the moment one of them misses a
tool the other still catches — the exact "guard narrower than its own subject"
shape #13228 already hit once, when globbing only ``*_mcp.py`` silently skipped
``redis_mcp`` (a package, not a module): all 25 of its tools were undeclared and
nothing said so.

This module only parses source text. It does not decide what a tool is allowed
to do — that is ``mcp_tool_permissions.py``.
"""

from __future__ import annotations

import pathlib
import re

#: Bridges live under here; two parents up from this file (``autobot_shared/auth/``).
BRIDGE_DIR = pathlib.Path(__file__).resolve().parents[2] / "autobot-backend" / "api"

# Three source shapes a bridge uses to declare a tool:
#  - a `("name", "description", {...})` tuple, 4-space indented inside a list
#    literal (`[ ( ... ), ( ... ) ]`);
#  - the same tuple assigned directly to an ALL_CAPS module-level constant, with
#    no enclosing list. #14494: `sequential_thinking_mcp` declares its one tool
#    this way, and the list-literal pattern alone never matched it -- that
#    bridge's whole tool surface was invisible to every guard below it, an
#    empty-enumeration case that read as clean because nothing was there to fail;
#  - an MCP SDK `Tool(name="...", ...)` keyword argument.
_TUPLE_TOOL = re.compile(r'^\s{4}\(\s*\n\s{8}"([a-z0-9_]+)"', re.M)
_MODULE_TUPLE_TOOL = re.compile(r'^[A-Z_][A-Z0-9_]*\s*=\s*\(\s*\n\s{4}"([a-z0-9_]+)"', re.M)
_KWARG_TOOL = re.compile(r'name="([a-z0-9_]+)"')


#: Bridge module stems intentionally excluded from governance, keyed to the
#: reason they are excluded. #14586: this used to be a bare
#: ``if p.stem != "manual_mcp"`` filter with no comment explaining why -- an
#: exclusion that could grow with no review trail, and did (manual_mcp was
#: added here with no declared permissions and no test pinning the choice).
#: Empty today: manual_mcp was un-excluded and governed as the twelfth
#: bridge (#14586). A future exclusion must add a reasoned entry here, not a
#: second inline stem check -- ``mcp_bridge_scan_test.py`` asserts every
#: ``*_mcp.py``/``*_mcp`` source not in ``all_declared_tools()`` is named here.
EXCLUDED_BRIDGE_STEMS: dict[str, str] = {}


def bridge_files(base: pathlib.Path | None = None) -> list[pathlib.Path]:
    """Every bridge's tool-declaring source, module- or package-shaped.

    #13228: globbing only ``*_mcp.py`` silently omitted ``redis_mcp``, which is
    a package (``api/redis_mcp/tools.py``). #14586: any stem in
    ``EXCLUDED_BRIDGE_STEMS`` is skipped -- an auditable table instead of an
    inline name check, so a new exclusion cannot land without a reason next
    to it.
    """
    directory = base or BRIDGE_DIR
    modules = [p for p in directory.glob("*_mcp.py") if p.stem not in EXCLUDED_BRIDGE_STEMS]
    packages = [
        p / "tools.py"
        for p in directory.glob("*_mcp")
        if p.is_dir() and p.stem not in EXCLUDED_BRIDGE_STEMS and (p / "tools.py").is_file()
    ]
    return sorted(modules + packages)


def bridge_name(path: pathlib.Path) -> str:
    """The bridge a source file belongs to (``redis_mcp/tools.py`` -> ``redis_mcp``)."""
    return path.parent.name if path.stem == "tools" else path.stem


def declared_tools(path: pathlib.Path) -> set[str]:
    """Tool names a bridge module declares, minus the bridge's own name."""
    src = path.read_text(encoding="utf-8")
    named = set(_TUPLE_TOOL.findall(src)) | set(_MODULE_TUPLE_TOOL.findall(src))
    names = named or set(_KWARG_TOOL.findall(src))
    return {n for n in names if n != bridge_name(path)}


def all_declared_tools(base: pathlib.Path | None = None) -> dict[str, set[str]]:
    """Bridge name -> set of tool names, for every bridge this system governs."""
    return {bridge_name(p): declared_tools(p) for p in bridge_files(base)}


__all__ = [
    "BRIDGE_DIR",
    "EXCLUDED_BRIDGE_STEMS",
    "all_declared_tools",
    "bridge_files",
    "bridge_name",
    "declared_tools",
]
