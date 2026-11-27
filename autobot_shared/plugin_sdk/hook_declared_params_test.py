# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A subscriber must take what the hook's declared signature passes, checked at registration (#20888)."""

import pytest

from plugin_sdk.hooks import Hook, HookRegistry


def test_a_subscriber_requiring_an_undeclared_parameter_is_refused_at_registration() -> None:
    """It would raise TypeError on every call; the plugin and hook are named at registration instead."""
    hr = HookRegistry()
    hr.clear()

    async def needs_agent_id(agent_id: str, **kwargs) -> None:  # the declaration has no agent_id
        return None

    with pytest.raises(TypeError, match="agent_id"):
        hr.register_hook(Hook.ON_AGENT_EXECUTE.value, needs_agent_id, plugin_name="mismatch")


def test_a_subscriber_taking_only_declared_parameters_registers() -> None:
    hr = HookRegistry()
    hr.clear()

    async def fine(agent_name: str, extra: int = 0, **kwargs) -> None:
        return None

    hr.register_hook(Hook.ON_AGENT_EXECUTE.value, fine, plugin_name="fine")
    hr.clear()
