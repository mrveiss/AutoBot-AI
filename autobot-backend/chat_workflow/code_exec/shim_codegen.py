# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shim module codegen for the compose tool (GH#11568).

Generates the ``autobot_tools`` Python module that is prepended to user scripts.
Each shim function calls the server-side broker via JSON-RPC over stdio, using a
per-call monotonic id so concurrent same-tool calls correlate their replies.
"""

from chat_workflow.code_exec.protocol import RPC_SENTINEL

# GH#11662: classification lives in the single tool-policy source; re-exported
# here so existing consumers (and test patch points) keep working.
from chat_workflow.code_exec.tool_policy import (  # noqa: F401
    CODEEXEC_INJECTABLE_TOOLS,
    SENSITIVE_TOOLS,
)


def injectable_tool_set(allowed_work: list[str], forbidden_work: frozenset[str]) -> list[str]:
    """Return the sorted injectable tool names for this agent.

    Intersects the declarative allowlist with ``allowed_work`` (when the agent is
    profile-bound), removes ``forbidden_work``, and ALWAYS removes SENSITIVE_TOOLS
    so sensitive tools can never be injected even if added to the env allowlist.
    """
    base = (CODEEXEC_INJECTABLE_TOOLS - forbidden_work) - SENSITIVE_TOOLS
    if allowed_work:
        return sorted(base & set(allowed_work))
    return sorted(base)


def _shim_for(tool: str) -> str:
    return (
        f"async def {tool}(**kwargs):\n"
        f'    """Call the {tool} tool via the broker."""\n'
        f'    return await _rpc_call("{tool}", kwargs)\n'
    )


def _rpc_helper() -> str:
    """Shared RPC helper: per-call monotonic id + reply correlation on that id.

    RPC request lines are prefixed with ``RPC_SENTINEL`` so the executor pump can
    tell them apart from the script's own stdout / final result (GH#11613).
    """
    return (
        "_call_seq = 0\n"
        "_pending = {}\n\n"
        "def _next_id():\n"
        "    global _call_seq\n"
        "    _call_seq += 1\n"
        "    return _call_seq\n\n"
        "async def _rpc_call(tool, params):\n"
        "    call_id = _next_id()\n"
        '    req = json.dumps({"id": call_id, "tool": tool, "params": params})\n'
        '    sys.stdout.write(_RPC_SENTINEL + req + "\\n")\n'
        "    sys.stdout.flush()\n"
        "    while call_id not in _pending:\n"
        "        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)\n"
        "        reply = json.loads(line)\n"
        '        _pending[reply.get("id")] = reply\n'
        "    reply = _pending.pop(call_id)\n"
        '    if not reply.get("ok"):\n'
        '        raise RuntimeError(reply.get("error", "tool call failed"))\n'
        '    return reply.get("result")\n\n'
    )


def generate_shim_module(tools: list[str]) -> str:
    """Return Python source for the ``autobot_tools`` shim module."""
    header = (
        '"""autobot_tools — generated RPC shims. Do not edit."""\n'
        "import asyncio, json, sys\n\n"
        f"_RPC_SENTINEL = {RPC_SENTINEL!r}\n\n"
    )
    return header + _rpc_helper() + "\n".join(_shim_for(t) for t in tools)
