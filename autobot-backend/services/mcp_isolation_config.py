# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Per-bridge isolation policy for MCP bridges (#3229).

Declares which bridges run in-process vs. subprocess vs. container and the
resource limits that apply to isolated ones. Pure configuration - no I/O.

Environment variables (read lazily so tests can override):

    MCP_ISOLATION_MODE              global default: inprocess | subprocess
    MCP_ISOLATION_MODE_<BRIDGE>     per-bridge override (upper-case)
    MCP_BRIDGE_CPU_LIMIT            CPU seconds per worker (RLIMIT_CPU)
    MCP_BRIDGE_MEM_LIMIT_MB         address-space cap per worker (RLIMIT_AS)
    MCP_BRIDGE_NOFILE_LIMIT         max open files per worker (RLIMIT_NOFILE)
    MCP_BRIDGE_RESTART_MAX          restarts before permanent failure
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List

from autobot_shared.ssot_config import config


class IsolationMode(str, Enum):
    """How a bridge is executed."""

    INPROCESS = "inprocess"
    SUBPROCESS = "subprocess"
    CONTAINER = "container"


@dataclass(frozen=True)
class BridgePolicy:
    """Isolation policy for a single MCP bridge."""

    bridge: str
    mode: IsolationMode
    cpu_seconds: int
    memory_mb: int
    nofile: int
    restart_max: int


# Per-bridge risk categorisation (#3229 issue table).
_HIGH_RISK = frozenset({"filesystem_mcp", "browser_mcp", "vnc_mcp"})
_ALWAYS_INPROCESS = frozenset({"knowledge_mcp", "sequential_thinking_mcp", "structured_thinking_mcp"})


def _env_int(name: str, default: int) -> int:
    """Return int env var or default on parse failure."""
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _global_mode() -> IsolationMode:
    """Resolve global default isolation mode from env."""
    raw = config.mcp_isolation_mode.lower()
    try:
        return IsolationMode(raw)
    except ValueError:
        return IsolationMode.INPROCESS


def resolve_mode(bridge: str) -> IsolationMode:
    """Return effective isolation mode for *bridge*.

    Precedence: per-bridge env override -> always-inprocess list ->
    high-risk default (subprocess) -> global default.
    """
    override = os.environ.get(
        f"MCP_ISOLATION_MODE_{bridge.upper()}"
    )  # ssot-config-exempt: dynamic env var name (f-string)
    if override:
        try:
            return IsolationMode(override.lower())
        except ValueError:
            pass
    if bridge in _ALWAYS_INPROCESS:
        return IsolationMode.INPROCESS
    if bridge in _HIGH_RISK:
        return IsolationMode.SUBPROCESS
    return _global_mode()


def policy_for(bridge: str) -> BridgePolicy:
    """Return the full BridgePolicy for *bridge*."""
    upper = bridge.upper()
    return BridgePolicy(
        bridge=bridge,
        mode=resolve_mode(bridge),
        cpu_seconds=_env_int(
            f"MCP_BRIDGE_CPU_LIMIT_{upper}",
            _env_int("MCP_BRIDGE_CPU_LIMIT", 30),
        ),
        memory_mb=_env_int(
            f"MCP_BRIDGE_MEM_LIMIT_MB_{upper}",
            _env_int("MCP_BRIDGE_MEM_LIMIT_MB", 512),
        ),
        nofile=_env_int(
            f"MCP_BRIDGE_NOFILE_LIMIT_{upper}",
            _env_int("MCP_BRIDGE_NOFILE_LIMIT", 256),
        ),
        restart_max=_env_int("MCP_BRIDGE_RESTART_MAX", 5),
    )


def all_policies(bridges: List[str]) -> Dict[str, BridgePolicy]:
    """Return policies for a list of bridge names."""
    return {b: policy_for(b) for b in bridges}
