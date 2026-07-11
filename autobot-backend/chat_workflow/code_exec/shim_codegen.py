# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shim module codegen for the compose tool (GH#11568).

Generates the ``autobot_tools`` Python module that is prepended to user scripts.
Each shim function calls the server-side broker via JSON-RPC over stdio.
"""

import os

CODEEXEC_INJECTABLE_TOOLS: frozenset[str] = frozenset(
    os.environ.get(
        "AUTOBOT_CODEEXEC_INJECTABLE_TOOLS",
        "web_search,scrape_url,map_site,extract_structured_data",
    ).split(",")
)


def injectable_tool_set(allowed_work: list[str], forbidden_work: frozenset[str]) -> list[str]:
    """Return sorted list of injectable tool names for this agent.

    If *allowed_work* is non-empty (profile-bound agent), intersect with CODEEXEC_INJECTABLE_TOOLS.
    If empty (main chat agent), use all CODEEXEC_INJECTABLE_TOOLS minus forbidden.
    """
    base = CODEEXEC_INJECTABLE_TOOLS - forbidden_work
    if allowed_work:
        return sorted(base & set(allowed_work))
    return sorted(base)


def _shim_for(tool: str) -> str:
    return (
        f"async def {tool}(**kwargs):\n"
        f'    """Call the {tool} tool via the broker."""\n'
        f'    req = json.dumps({{"id": "{tool}", "tool": "{tool}", "params": kwargs}})\n'
        '    sys.stdout.write(req + "\\n")\n'
        "    sys.stdout.flush()\n"
        "    line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)\n"
        "    reply = json.loads(line)\n"
        '    if not reply.get("ok"):\n'
        '        raise RuntimeError(reply.get("error", "tool call failed"))\n'
        '    return reply.get("result")\n'
    )


def generate_shim_module(tools: list[str]) -> str:
    """Return Python source for the ``autobot_tools`` shim module."""
    header = '"""autobot_tools — generated RPC shims. Do not edit."""\n' "import asyncio, json, sys\n\n"
    return header + "\n".join(_shim_for(t) for t in tools)
