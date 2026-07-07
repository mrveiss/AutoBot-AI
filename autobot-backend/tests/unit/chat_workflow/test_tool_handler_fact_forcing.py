# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dispatch-level fact-forcing enforcement (GH#11178).

Proves the fact-forcing gate (#11149) — previously only in the dead `AgentLoop`
path — now fires on the real production tool-dispatch seam
(`ToolHandlerMixin._dispatch_tool_call` via `_enforce_fact_forcing`), using a
turn-scoped investigated-files set on `ctx.context`. An edit to an existing
unread file is blocked; reading it first (same ctx) clears it; new files pass;
off unless `AUTOBOT_FACT_FORCING` is set.
"""

from types import SimpleNamespace

import pytest

from chat_workflow.tool_handler import ToolHandlerMixin


def _mixin() -> ToolHandlerMixin:
    return ToolHandlerMixin.__new__(ToolHandlerMixin)


def _ctx() -> SimpleNamespace:
    """A per-turn context stand-in — only `.context` (a dict) is touched."""
    return SimpleNamespace(context={})


@pytest.fixture(autouse=True)
def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOBOT_FACT_FORCING", "1")


def test_blocks_edit_to_existing_unread_file(tmp_path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    results: list[dict] = []
    msg = _mixin()._enforce_fact_forcing(
        {"name": "edit_file", "params": {"file_path": str(target)}}, _ctx(), results
    )
    assert msg is not None
    assert msg.type == "error"
    assert msg.metadata.get("fact_forcing") is True
    assert results and results[0]["fact_forcing"] is True
    assert "fact-forcing" in msg.content.lower()


def test_read_then_edit_same_ctx_is_allowed(tmp_path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    mixin = _mixin()
    ctx = _ctx()
    # Read first (records into ctx.context)...
    assert mixin._enforce_fact_forcing(
        {"name": "read_file", "params": {"file_path": str(target)}}, ctx, []
    ) is None
    # ...then edit is allowed through the same ctx.
    assert mixin._enforce_fact_forcing(
        {"name": "edit_file", "params": {"file_path": str(target)}}, ctx, []
    ) is None


def test_new_file_write_is_allowed(tmp_path) -> None:
    new_file = tmp_path / "brand_new.py"  # does not exist
    msg = _mixin()._enforce_fact_forcing(
        {"name": "write_file", "params": {"file_path": str(new_file)}}, _ctx(), []
    )
    assert msg is None


def test_disabled_without_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOBOT_FACT_FORCING", raising=False)
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    msg = _mixin()._enforce_fact_forcing(
        {"name": "edit_file", "params": {"file_path": str(target)}}, _ctx(), []
    )
    assert msg is None


def test_no_ctx_is_noop(tmp_path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    msg = _mixin()._enforce_fact_forcing(
        {"name": "edit_file", "params": {"file_path": str(target)}}, None, []
    )
    assert msg is None


def test_reads_via_arguments_key(tmp_path) -> None:
    """MCP tools carry the path in `arguments` rather than `params`."""
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    mixin = _mixin()
    ctx = _ctx()
    mixin._enforce_fact_forcing(
        {"name": "read_file", "arguments": {"file_path": str(target)}}, ctx, []
    )
    assert mixin._enforce_fact_forcing(
        {"name": "edit_file", "arguments": {"file_path": str(target)}}, ctx, []
    ) is None
