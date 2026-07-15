# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for the lightweight-mode badge isolation (#11216).

The ``lightweight_mode_used`` stream-metadata cost indicator used to live on the
shared ``ChatWorkflowManager`` singleton (``self._current_lightweight_mode``), so
two concurrent drivers of ``_execute_llm_continuation_loop`` (e.g. a real
lightweight chat and the internal delegation subagent) could clobber each
other's flag. It now lives in a task-local ``ContextVar``; these tests pin the
read behaviour and the cross-task isolation.
"""

import asyncio

import pytest

import chat_workflow.manager as manager_module
from chat_workflow.manager import ChatWorkflowManager


def _bare_manager() -> ChatWorkflowManager:
    """A manager instance without the heavy ``__init__`` dependencies."""
    return ChatWorkflowManager.__new__(ChatWorkflowManager)


def _badge(manager: ChatWorkflowManager):
    msg = manager._init_streaming_message("assistant_message", "gpt", None, False, None)
    return msg.metadata.get("lightweight_mode_used")


def test_badge_absent_by_default():
    manager = _bare_manager()
    token = manager_module._current_lightweight_mode.set(False)
    try:
        assert _badge(manager) is None
    finally:
        manager_module._current_lightweight_mode.reset(token)


def test_badge_reflects_contextvar():
    manager = _bare_manager()
    token = manager_module._current_lightweight_mode.set(True)
    try:
        assert _badge(manager) is True
    finally:
        manager_module._current_lightweight_mode.reset(token)


@pytest.mark.asyncio
async def test_concurrent_drivers_do_not_clobber_each_other():
    """Two concurrent loop drivers must each see their own lightweight flag (#11216)."""
    manager = _bare_manager()
    seen = {}

    async def driver(name: str, flag: bool) -> None:
        token = manager_module._current_lightweight_mode.set(flag)
        try:
            # Yield so the two tasks interleave between set and read — the exact
            # window where shared instance state used to leak across drivers.
            await asyncio.sleep(0)
            seen[name] = _badge(manager)
        finally:
            manager_module._current_lightweight_mode.reset(token)

    await asyncio.gather(driver("lightweight", True), driver("full", False))

    assert seen["lightweight"] is True
    # Would be True (clobbered) under the old shared-instance-state implementation.
    assert seen["full"] is None
