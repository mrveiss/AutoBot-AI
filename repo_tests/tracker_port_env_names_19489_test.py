# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The MCP tracker reads each port from the SSOT's ``AUTOBOT_*`` name first (#19489).

``network.ts`` read bare names (``BACKEND_PORT``, ``BROWSER_SERVICE_PORT``, ...), so an operator
overriding a port the canonical way (``PortConfig``'s alias) changed nothing in the tracker. Each
port now reads ``port(canonical, legacy, fallback)``; the canonical name must equal the alias of
its ``PortConfig`` field. Literal defaults stay held by their existing pins.
"""

from __future__ import annotations

import ast
import re

from repo_tests._paths import repo_root

_NETWORK_TS = "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/src/constants/network.ts"
_SSOT = "autobot_shared/ssot_config.py"
#: network.ts key -> the PortConfig field it mirrors.
FIELDS = {
    "BACKEND_PORT": "backend",
    "FRONTEND_PORT": "frontend",
    "REDIS_PORT": "redis",
    "OLLAMA_PORT": "ollama",
    "VNC_PORT": "vnc",
    "BROWSER_SERVICE_PORT": "browser",
    "AI_STACK_PORT": "aistack",
    "NPU_WORKER_PORT": "npu",
    "NPU_WORKER_WINDOWS_PORT": "npu_windows",
}
#: PortConfig fields not yet on this tree, each with what adds them. Stale-checked.
PENDING_FIELDS: dict[str, str] = {}
_PORT_CALL = re.compile(r"^\s*(\w+_PORT): port\('(\w+)', '(\w+)', '(\d+)'\)", re.M)
_ANY_PORT_KEY = re.compile(r"^\s*(\w+_PORT): ", re.M)


def port_aliases() -> dict[str, str]:
    """``PortConfig`` field -> its env alias, read from the class."""
    tree = ast.parse((repo_root() / _SSOT).read_text(encoding="utf-8"))
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "PortConfig")
    out = {}
    for node in cls.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Call):
            alias = next((k.value.value for k in node.value.keywords if k.arg == "alias"), None)
            if alias:
                out[node.target.id] = alias
    return out


def _constants_block(text: str) -> str:
    """The ``NetworkConstants = { ... }`` object only, so another ``*_PORT:`` line elsewhere is not read."""
    start = text.find("export const NetworkConstants = {")
    return text[start : text.find("} as const", start)] if start >= 0 else text


def mismatches(text: str, aliases: dict[str, str]) -> list[str]:
    """Each tracker port whose canonical name is not its PortConfig alias, or that skips ``port()``."""
    block = _constants_block(text)
    found = _PORT_CALL.findall(block)
    calls = {key: canonical for key, canonical, _legacy, _default in found}
    out = [f"{key}: not read through port()" for key in _ANY_PORT_KEY.findall(block) if key not in calls]
    out += [f"{key}: legacy fallback is {legacy}, not {key}" for key, _c, legacy, _d in found if legacy != key]
    for key, canonical in calls.items():
        field = FIELDS.get(key)
        if field is None:
            out.append(f"{key}: no PortConfig field mapped")
        elif field in aliases and canonical != aliases[field]:
            out.append(f"{key}: reads {canonical}, PortConfig.{field} is {aliases[field]}")
    return out


def test_every_tracker_port_reads_its_portconfig_alias_first() -> None:
    text = (repo_root() / _NETWORK_TS).read_text(encoding="utf-8")
    assert len(_PORT_CALL.findall(text)) >= 9, "network.ts no longer reads its ports through port()"
    assert mismatches(text, port_aliases()) == []


def test_every_mapped_field_exists_or_is_pending() -> None:
    aliases = port_aliases()
    missing = sorted(f for f in FIELDS.values() if f not in aliases and f not in PENDING_FIELDS)
    stale = sorted(f for f in PENDING_FIELDS if f in aliases)
    assert missing == [], f"no PortConfig field: {missing}"
    assert stale == [], f"PortConfig now has {stale}; delete it from PENDING_FIELDS"


def test_a_bare_or_wrong_name_is_caught() -> None:
    aliases = {"backend": "AUTOBOT_BACKEND_PORT"}
    text = "  BACKEND_PORT: parseInt(process.env.BACKEND_PORT || '8001'),\n"
    assert mismatches(text, aliases) == ["BACKEND_PORT: not read through port()"]
    text = "  BACKEND_PORT: port('BACKEND_PORT', 'BACKEND_PORT', '8001'),\n"
    assert mismatches(text, aliases) == ["BACKEND_PORT: reads BACKEND_PORT, PortConfig.backend is AUTOBOT_BACKEND_PORT"]
    text = "  BACKEND_PORT: port('AUTOBOT_BACKEND_PORT', 'WRONG', '8001'),\n"
    assert mismatches(text, aliases) == ["BACKEND_PORT: legacy fallback is WRONG, not BACKEND_PORT"]
