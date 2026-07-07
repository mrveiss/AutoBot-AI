# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dispatch-level config-protection enforcement (GH#11177).

Proves the config-protection guard (#11148) — previously only in the dead
`AgentLoop` path — now fires on the real production tool-dispatch seam
(`ToolHandlerMixin._dispatch_tool_call` via `_enforce_config_protection`). A
write to a linter/formatter config is blocked before any handler runs; ordinary
writes pass; `AUTOBOT_ALLOW_CONFIG_EDITS=1` opts out.
"""

import pytest

from chat_workflow.tool_handler import ToolHandlerMixin


def _mixin() -> ToolHandlerMixin:
    return ToolHandlerMixin.__new__(ToolHandlerMixin)


@pytest.fixture(autouse=True)
def _no_optout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOBOT_ALLOW_CONFIG_EDITS", raising=False)


def test_blocks_write_to_config_via_params() -> None:
    """Built-in write tools carry the path in `params`."""
    results: list[dict] = []
    msg = _mixin()._enforce_config_protection(
        {"name": "write_file", "params": {"file_path": "frontend/.eslintrc.json"}}, results
    )
    assert msg is not None
    assert msg.type == "error"
    assert msg.metadata.get("config_protection") is True
    assert results and results[0]["config_protection"] is True
    assert results[0]["status"] == "error"


def test_blocks_write_to_config_via_arguments() -> None:
    """MCP tools carry the path in `arguments`."""
    results: list[dict] = []
    msg = _mixin()._enforce_config_protection({"name": "edit_file", "arguments": {"path": "ruff.toml"}}, results)
    assert msg is not None
    assert "config-protection" in msg.content.lower()


def test_allows_ordinary_write() -> None:
    results: list[dict] = []
    msg = _mixin()._enforce_config_protection({"name": "write_file", "params": {"file_path": "src/app.ts"}}, results)
    assert msg is None
    assert results == []


def test_allows_read_of_config() -> None:
    results: list[dict] = []
    msg = _mixin()._enforce_config_protection({"name": "read_file", "params": {"file_path": ".eslintrc.json"}}, results)
    assert msg is None


def test_mixed_purpose_manifest_not_blocked() -> None:
    results: list[dict] = []
    msg = _mixin()._enforce_config_protection(
        {"name": "write_file", "params": {"file_path": "pyproject.toml"}}, results
    )
    assert msg is None


def test_env_optout_allows_config_write(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOBOT_ALLOW_CONFIG_EDITS", "1")
    results: list[dict] = []
    msg = _mixin()._enforce_config_protection({"name": "write_file", "params": {"file_path": ".prettierrc"}}, results)
    assert msg is None
