# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared test helpers for llc/adapters/tests (GH#9844).

Plain helper functions are preferred over pytest fixtures here because all
callers pass arguments — parametrised fixtures would require indirect= wiring
that adds noise without benefit.  Import directly in test modules.
"""

from unittest.mock import MagicMock


def agent_cfg(agent_id: str = "agent-1", output_dir: str | None = None, **kwargs) -> dict:
    """Build a minimal agent-config dict used across adapter test suites."""
    cfg: dict = {"agent_id": agent_id, "adapter_config": {**kwargs}}
    if output_dir:
        cfg["adapter_config"]["output_dir"] = output_dir
    return cfg


def make_fake_proc(pid: int = 12345) -> MagicMock:
    """Return a MagicMock that mimics an asyncio.subprocess.Process with the given PID."""
    proc = MagicMock()
    proc.pid = pid
    return proc
