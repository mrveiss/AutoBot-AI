# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Error Isolation Module

Issue #4342: Component failures should not cascade.
Tests verify that isolated errors are handled gracefully.
"""

import asyncio

import pytest

from services.resilience.error_isolation import (
    IsolatedError,
    isolate_errors,
)


class TestErrorIsolation:
    """Test suite for error isolation."""

    def test_sync_function_success(self):
        """Test that successful sync function executes normally."""

        @isolate_errors(component="test_component")
        def success_func():
            return "success"

        result = success_func()
        assert result == "success"

    def test_sync_function_failure_without_fallback(self):
        """Test that sync function failure raises IsolatedError."""

        @isolate_errors(component="test_component")
        def failing_func():
            raise ValueError("Test error")

        with pytest.raises(IsolatedError) as exc_info:
            failing_func()

        assert exc_info.value.component == "test_component"
        assert isinstance(exc_info.value.original_error, ValueError)

    def test_sync_function_failure_with_fallback_value(self):
        """Test that sync function returns fallback value on failure."""

        @isolate_errors(
            component="test_component",
            fallback="fallback_value",
        )
        def failing_func():
            raise ValueError("Test error")

        result = failing_func()
        assert result == "fallback_value"

    def test_sync_function_failure_with_fallback_callable(self):
        """Test that sync function calls fallback on failure."""

        def fallback_handler():
            return {"default": "data"}

        @isolate_errors(
            component="test_component",
            fallback=fallback_handler,
        )
        def failing_func():
            raise ValueError("Test error")

        result = failing_func()
        assert result == {"default": "data"}

    @pytest.mark.asyncio
    async def test_async_function_success(self):
        """Test that successful async function executes normally."""

        @isolate_errors(component="test_component")
        async def success_func():
            await asyncio.sleep(0.01)
            return "async_success"

        result = await success_func()
        assert result == "async_success"

    @pytest.mark.asyncio
    async def test_async_function_failure_without_fallback(self):
        """Test that async function failure raises IsolatedError."""

        @isolate_errors(component="test_component")
        async def failing_func():
            await asyncio.sleep(0.01)
            raise RuntimeError("Async test error")

        with pytest.raises(IsolatedError) as exc_info:
            await failing_func()

        assert exc_info.value.component == "test_component"
        assert isinstance(exc_info.value.original_error, RuntimeError)

    @pytest.mark.asyncio
    async def test_async_function_failure_with_fallback(self):
        """Test that async function returns fallback value on failure."""

        @isolate_errors(
            component="test_component",
            fallback=["default"],
        )
        async def failing_func():
            await asyncio.sleep(0.01)
            raise RuntimeError("Async test error")

        result = await failing_func()
        assert result == ["default"]

    @pytest.mark.asyncio
    async def test_async_function_failure_with_async_fallback(self):
        """Test that async function calls async fallback on failure."""

        async def async_fallback():
            await asyncio.sleep(0.01)
            return {"async": "fallback"}

        @isolate_errors(
            component="test_component",
            fallback=async_fallback,
        )
        async def failing_func():
            raise RuntimeError("Async test error")

        result = await failing_func()
        assert result == {"async": "fallback"}

    def test_error_isolation_preserves_function_name(self):
        """Test that error isolation preserves original function name."""

        @isolate_errors(component="test_component")
        def my_function():
            return "result"

        assert my_function.__name__ == "my_function"

    def test_isolated_error_with_args(self):
        """Test that error isolation works with function arguments."""

        @isolate_errors(component="test_component", fallback="default")
        def func_with_args(x, y, z=None):
            if z is None:
                raise ValueError("z is required")
            return x + y + z

        # Success case
        result = func_with_args(1, 2, z=3)
        assert result == 6

        # Failure case
        result = func_with_args(1, 2)
        assert result == "default"


class TestComponentIsolation:
    """Test that component failures don't cascade."""

    def test_multiple_isolated_components(self):
        """Test that failure in one component doesn't affect others."""

        @isolate_errors(component="component_a", fallback="default_a")
        def component_a():
            raise RuntimeError("A fails")

        @isolate_errors(component="component_b")
        def component_b():
            return "b_success"

        result_a = component_a()
        result_b = component_b()

        assert result_a == "default_a"
        assert result_b == "b_success"

    @pytest.mark.asyncio
    async def test_async_component_isolation(self):
        """Test async component failure isolation."""

        @isolate_errors(component="redis_service", fallback={})
        async def fetch_from_redis():
            await asyncio.sleep(0.01)
            raise ConnectionError("Redis unavailable")

        @isolate_errors(component="core_processor")
        async def process_data():
            await asyncio.sleep(0.01)
            return "processed"

        redis_result = await fetch_from_redis()
        core_result = await process_data()

        assert redis_result == {}
        assert core_result == "processed"


class TestSkillFailureIsolation:
    """Test that skill failures don't halt agent."""

    def test_skill_failure_doesnt_halt_agent(self):
        """Test that failed skill returns fallback without halting."""

        @isolate_errors(
            component="skill_service",
            fallback={"status": "skill_failed"},
        )
        def run_skill():
            raise RuntimeError("Skill execution failed")

        @isolate_errors(component="agent_orchestrator")
        def run_agent():
            try:
                skill_result = run_skill()
            except IsolatedError:
                skill_result = {"status": "skill_failed"}

            return f"Agent continues: {skill_result}"

        result = run_agent()
        assert "Agent continues" in result
