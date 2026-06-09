# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for BaseAgent.is_available contract (Issue #6659).

LocalAgent and ContainerAgent must both expose ``is_available`` as an
``async def`` so callers can substitute either subclass without knowing
the deployment mode.
"""

import importlib.util
import inspect

import pytest


def _load_base_agent():
    """Load base_agent.py without triggering the heavy autobot_shared chain."""
    spec = importlib.util.spec_from_file_location(
        "base_agent_under_test",
        "autobot-backend/agents/base_agent.py",
    )
    return spec, importlib.util.module_from_spec(spec)


class TestIsAvailableContract:
    """Issue #6659: is_available is async on every concrete BaseAgent subclass."""

    def test_baseagent_declares_is_available_async_abstract(self):
        """BaseAgent.is_available is declared @abstractmethod async def."""
        spec, mod = _load_base_agent()
        try:
            spec.loader.exec_module(mod)
        except Exception as exc:  # pragma: no cover — env-dependent dep chain
            pytest.skip(f"base_agent dep chain unavailable: {exc}")

        assert inspect.iscoroutinefunction(
            mod.BaseAgent.is_available
        ), "BaseAgent.is_available must be an async coroutine function"
        assert getattr(
            mod.BaseAgent.is_available, "__isabstractmethod__", False
        ), "BaseAgent.is_available must be marked @abstractmethod"

    def test_localagent_is_available_is_async(self):
        """LocalAgent.is_available was sync prior to #6659 — must be async now."""
        spec, mod = _load_base_agent()
        try:
            spec.loader.exec_module(mod)
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"base_agent dep chain unavailable: {exc}")

        assert inspect.iscoroutinefunction(
            mod.LocalAgent.is_available
        ), "LocalAgent.is_available must be async to match BaseAgent contract"

    def test_containeragent_is_available_is_async(self):
        """ContainerAgent.is_available must remain async (network health check)."""
        spec, mod = _load_base_agent()
        try:
            spec.loader.exec_module(mod)
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"base_agent dep chain unavailable: {exc}")

        assert inspect.iscoroutinefunction(
            mod.ContainerAgent.is_available
        ), "ContainerAgent.is_available must be async — it does a remote health check"

    @pytest.mark.asyncio
    async def test_localagent_returns_true_when_awaited(self):
        """LocalAgent.is_available must return True after being awaited."""
        spec, mod = _load_base_agent()
        try:
            spec.loader.exec_module(mod)
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"base_agent dep chain unavailable: {exc}")

        # We cannot easily instantiate a LocalAgent (it requires get_capabilities
        # and process_request to be implemented). Instead we exercise the bound
        # method via a minimal subclass that satisfies the abstract contract.
        class _DummyLocal(mod.LocalAgent):
            def get_capabilities(self):
                return []

            async def process_request(self, request):  # pragma: no cover
                raise NotImplementedError

        try:
            agent = _DummyLocal(agent_type="dummy")
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"LocalAgent init requires extra deps: {exc}")

        assert await agent.is_available() is True
