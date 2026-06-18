# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for per-run credential injection (GH#9037)."""

import asyncio

import pytest

from llm_shared.provider_registry import (
    RunCredentialContext,
    get_run_credentials,
    set_run_credentials,
)


def test_credential_context_creation():
    """Test creating a RunCredentialContext."""
    ctx = RunCredentialContext(
        provider_credentials={
            "anthropic": {"api_key": "sk-test123"},
            "openai": {"api_key": "sk-openai456"},
        }
    )

    assert ctx.get_credentials("anthropic") == {"api_key": "sk-test123"}
    assert ctx.get_credentials("openai") == {"api_key": "sk-openai456"}
    assert ctx.get_credentials("unknown") is None


def test_credential_context_repr_redacted():
    """Test that repr redacts credentials."""
    ctx = RunCredentialContext(
        provider_credentials={
            "anthropic": {"api_key": "sk-secret-key-12345"},
        }
    )

    repr_str = repr(ctx)
    assert "sk-secret" not in repr_str
    assert "anthropic" in repr_str


@pytest.mark.asyncio
async def test_context_var_isolation():
    """Test that credentials are isolated per async task."""

    async def task_a():
        ctx_a = RunCredentialContext(provider_credentials={"provider_a": {"api_key": "key_a"}})
        set_run_credentials(ctx_a)
        await asyncio.sleep(0.01)  # Let other task run
        retrieved = get_run_credentials()
        assert retrieved is ctx_a
        assert retrieved.get_credentials("provider_a") == {"api_key": "key_a"}

    async def task_b():
        ctx_b = RunCredentialContext(provider_credentials={"provider_b": {"api_key": "key_b"}})
        set_run_credentials(ctx_b)
        await asyncio.sleep(0.01)
        retrieved = get_run_credentials()
        assert retrieved is ctx_b
        assert retrieved.get_credentials("provider_b") == {"api_key": "key_b"}

    # Run both tasks concurrently
    await asyncio.gather(task_a(), task_b())


@pytest.mark.asyncio
async def test_context_cleared():
    """Test that context can be cleared."""
    ctx = RunCredentialContext(provider_credentials={"test": {"api_key": "xyz"}})
    set_run_credentials(ctx)

    assert get_run_credentials() is ctx

    set_run_credentials(None)
    assert get_run_credentials() is None


def test_inject_runtime_credentials_sets_context():
    """inject_runtime_credentials installs a RunCredentialContext (GH#9037)."""
    from llm_shared.run_credential_loader import inject_runtime_credentials

    try:
        inject_runtime_credentials({"anthropic": {"api_key": "sk-run-only"}})
        ctx = get_run_credentials()
        assert ctx is not None
        assert ctx.get_credentials("anthropic") == {"api_key": "sk-run-only"}
    finally:
        set_run_credentials(None)


@pytest.mark.asyncio
async def test_per_run_override_beats_registered_provider():
    """A per-run credential builds an ephemeral provider instead of the registered one (GH#9037)."""
    from llm_shared.provider_registry import ProviderRegistry

    registry = ProviderRegistry()

    class _Registered:
        provider_name = "anthropic"

        async def is_available(self) -> bool:
            return True

    registry._providers["anthropic"] = _Registered()

    sentinel = object()
    ephemeral_args: dict = {}

    def _fake_ephemeral(name, creds):
        ephemeral_args["name"] = name
        ephemeral_args["creds"] = creds
        return sentinel

    registry._create_ephemeral_provider = _fake_ephemeral  # type: ignore[assignment]

    try:
        set_run_credentials(RunCredentialContext(provider_credentials={"anthropic": {"api_key": "sk-run"}}))
        provider = await registry.get_provider("anthropic")
        assert provider is sentinel  # ephemeral, NOT the registered instance
        assert ephemeral_args["creds"] == {"api_key": "sk-run"}
    finally:
        set_run_credentials(None)


@pytest.mark.asyncio
async def test_absent_override_falls_back_to_registered_provider():
    """With no per-run credentials, the registered provider is used (GH#9037)."""
    from llm_shared.provider_registry import ProviderRegistry

    registry = ProviderRegistry()

    class _Registered:
        provider_name = "anthropic"

        async def is_available(self) -> bool:
            return True

    registered = _Registered()
    registry._providers["anthropic"] = registered

    set_run_credentials(None)
    provider = await registry.get_provider("anthropic")
    assert provider is registered
