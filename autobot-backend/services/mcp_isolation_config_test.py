# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for mcp_isolation_config and mcp_isolated_runtime (#3229)."""

from __future__ import annotations

import os
from unittest.mock import patch

from services.mcp_isolation_config import (
    BridgePolicy,
    IsolationMode,
    all_policies,
    policy_for,
    resolve_mode,
)


class TestResolveMode:
    """Policy resolution precedence."""

    def test_high_risk_defaults_to_subprocess(self) -> None:
        """filesystem/browser/vnc are subprocess by default."""
        with patch.dict(os.environ, {}, clear=True):
            assert resolve_mode("filesystem_mcp") == IsolationMode.SUBPROCESS
            assert resolve_mode("browser_mcp") == IsolationMode.SUBPROCESS
            assert resolve_mode("vnc_mcp") == IsolationMode.SUBPROCESS

    def test_pure_bridges_always_inprocess(self) -> None:
        """Pure/in-memory bridges ignore global override."""
        with patch.dict(os.environ, {"MCP_ISOLATION_MODE": "subprocess"}, clear=True):
            assert resolve_mode("knowledge_mcp") == IsolationMode.INPROCESS
            assert resolve_mode("sequential_thinking_mcp") == IsolationMode.INPROCESS
            assert resolve_mode("structured_thinking_mcp") == IsolationMode.INPROCESS

    def test_per_bridge_env_override(self) -> None:
        """Per-bridge env var wins over category defaults."""
        with patch.dict(
            os.environ,
            {"MCP_ISOLATION_MODE_FILESYSTEM_MCP": "inprocess"},
            clear=True,
        ):
            assert resolve_mode("filesystem_mcp") == IsolationMode.INPROCESS

    def test_invalid_override_falls_through(self) -> None:
        """Garbage env override is ignored."""
        with patch.dict(
            os.environ,
            {"MCP_ISOLATION_MODE_BROWSER_MCP": "nonsense"},
            clear=True,
        ):
            assert resolve_mode("browser_mcp") == IsolationMode.SUBPROCESS

    def test_unknown_bridge_uses_global(self) -> None:
        """Bridges not in either set follow global default."""
        with patch.dict(os.environ, {"MCP_ISOLATION_MODE": "subprocess"}, clear=True):
            assert resolve_mode("http_client_mcp") == IsolationMode.SUBPROCESS
        with patch.dict(os.environ, {}, clear=True):
            assert resolve_mode("http_client_mcp") == IsolationMode.INPROCESS


class TestPolicyFor:
    """Resource limit resolution."""

    def test_defaults(self) -> None:
        """With no env vars, defaults are applied."""
        with patch.dict(os.environ, {}, clear=True):
            p = policy_for("filesystem_mcp")
            assert p.cpu_seconds == 30
            assert p.memory_mb == 512
            assert p.nofile == 256
            assert p.restart_max == 5

    def test_global_cpu_limit(self) -> None:
        """MCP_BRIDGE_CPU_LIMIT overrides default for all bridges."""
        with patch.dict(os.environ, {"MCP_BRIDGE_CPU_LIMIT": "60"}, clear=True):
            assert policy_for("browser_mcp").cpu_seconds == 60

    def test_per_bridge_memory_override(self) -> None:
        """Per-bridge memory override wins over global."""
        env = {
            "MCP_BRIDGE_MEM_LIMIT_MB": "256",
            "MCP_BRIDGE_MEM_LIMIT_MB_BROWSER_MCP": "1024",
        }
        with patch.dict(os.environ, env, clear=True):
            assert policy_for("browser_mcp").memory_mb == 1024
            assert policy_for("filesystem_mcp").memory_mb == 256

    def test_all_policies_returns_dict(self) -> None:
        """all_policies returns one entry per bridge."""
        bridges = ["filesystem_mcp", "browser_mcp", "knowledge_mcp"]
        result = all_policies(bridges)
        assert set(result.keys()) == set(bridges)
        assert all(isinstance(p, BridgePolicy) for p in result.values())
