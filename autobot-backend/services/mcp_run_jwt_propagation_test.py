# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for run-JWT propagation to isolated MCP bridge workers (#13265).

Before this change ``mcp_dispatch._call_bridge`` called ``call_tool()`` without
``run_jwt``, and the worker could not read one from its environment either
(``_WORKER_ENV_ALLOW`` excludes ``MCP_RUN_JWT`` by design), so every
subprocess-routed tool call failed closed once ``MCP_RUN_JWT_ENFORCE=1``.

Coverage:
- _call_bridge forwards a valid run JWT on every isolated call
- The forwarded token is scoped to the bridge being called
- A subprocess-routed call is accepted by the worker with enforcement ON
- It is still rejected when the token is absent, or expired
- A worker with a scrubbed environment can still resolve the signing secret
- A missing signing secret fails the request closed instead of crashing the
  worker's serve loop
"""

from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.auth.jwt_core import JWTDecodeError
from autobot_shared.ssot_config import config
from services.mcp_dispatch import MCPDispatcher
from services.run_jwt import mint_run_jwt

TEST_JWT_SECRET = "unit-test-run-jwt-signing-secret-0123456789"


@pytest.fixture(autouse=True)
def _signing_secret(monkeypatch):
    """Provide a signing secret and keep the Redis denylist out of unit tests."""
    monkeypatch.setenv("RUN_JWT_SECRET", TEST_JWT_SECRET)
    with patch("services.run_jwt._is_denied", AsyncMock(return_value=False)):
        yield


def _mint(scope=None, ttl=300):
    """Mint a token for the tests, honouring a custom TTL."""
    with patch("services.run_jwt._ttl", return_value=ttl):
        return mint_run_jwt(
            run_id="run-1",
            task_id="task-1",
            agent_id="agent-1",
            tenant_id="default",
            scope=scope or ["mcp:filesystem"],
        )


# ---------------------------------------------------------------------------
# Dispatcher forwards the token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_bridge_forwards_run_jwt_to_isolated_worker():
    """#13265: the isolated path must supply run_jwt; it previously never did."""
    dispatcher = MCPDispatcher()
    isolated = AsyncMock()
    isolated.call_tool = AsyncMock(return_value={"success": True, "result": "ok", "bridge": "filesystem_mcp"})
    registry = AsyncMock()
    registry.get_or_create = AsyncMock(return_value=isolated)

    with patch("services.mcp_isolated_runtime.get_isolated_registry", return_value=registry):
        await dispatcher._call_bridge("read_file", "filesystem_mcp", "http://unused", {"path": "/tmp/x"})

    _, kwargs = isolated.call_tool.call_args
    assert kwargs.get("run_jwt"), "no run JWT forwarded to the isolated worker"


@pytest.mark.asyncio
async def test_forwarded_token_is_scoped_to_the_bridge():
    """Minimum privilege: a filesystem bridge call does not carry web_fetch scope."""
    from services.run_jwt import validate_run_jwt

    dispatcher = MCPDispatcher()
    isolated = AsyncMock()
    isolated.call_tool = AsyncMock(return_value={"success": True, "result": "ok", "bridge": "filesystem_mcp"})
    registry = AsyncMock()
    registry.get_or_create = AsyncMock(return_value=isolated)

    with patch("services.mcp_isolated_runtime.get_isolated_registry", return_value=registry):
        await dispatcher._call_bridge("read_file", "filesystem_mcp", "http://unused", {})

    claims = await validate_run_jwt(isolated.call_tool.call_args.kwargs["run_jwt"])
    assert claims["scope"] == ["mcp:filesystem"]


def test_mint_failure_is_logged_and_does_not_raise(monkeypatch):
    """No signing secret must not crash dispatch; the worker rejects instead."""
    monkeypatch.delenv("RUN_JWT_SECRET", raising=False)
    monkeypatch.delenv("AUTOBOT_JWT_SECRET", raising=False)
    with patch.object(config.misc, "run_jwt_secret", ""), patch.object(config.misc, "jwt_secret", ""):
        assert MCPDispatcher._mint_bridge_jwt("filesystem_mcp", "read_file") is None


# ---------------------------------------------------------------------------
# Worker-side enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_accepts_forwarded_token_with_enforcement_on():
    """#13265: a subprocess-routed call succeeds with MCP_RUN_JWT_ENFORCE=1."""
    from services.mcp_bridge_workers import worker_entrypoint

    with patch.object(worker_entrypoint, "_JWT_ENFORCE", True):
        claims = await worker_entrypoint._validate_run_jwt_param({"run_jwt": _mint()})

    assert claims["scope"] == ["mcp:filesystem"]


@pytest.mark.asyncio
async def test_worker_rejects_missing_token_with_enforcement_on():
    """Absent token still fails closed."""
    from services.mcp_bridge_workers import worker_entrypoint

    with patch.object(worker_entrypoint, "_JWT_ENFORCE", True), patch.object(config.misc, "mcp_run_jwt", ""):
        with pytest.raises(PermissionError, match="no token provided"):
            await worker_entrypoint._validate_run_jwt_param({})


@pytest.mark.asyncio
async def test_worker_rejects_expired_token_with_enforcement_on():
    """Expired token still fails closed."""
    from services.mcp_bridge_workers import worker_entrypoint

    expired = _mint(ttl=-60)
    with patch.object(worker_entrypoint, "_JWT_ENFORCE", True):
        with pytest.raises(PermissionError, match="expired"):
            await worker_entrypoint._validate_run_jwt_param({"run_jwt": expired})


@pytest.mark.asyncio
async def test_worker_rejects_token_signed_with_another_secret(monkeypatch):
    """A forged token is rejected rather than accepted on scope alone."""
    from services.mcp_bridge_workers import worker_entrypoint

    token = _mint()
    monkeypatch.setenv("RUN_JWT_SECRET", "a-completely-different-secret-value-99")
    with patch.object(worker_entrypoint, "_JWT_ENFORCE", True):
        with pytest.raises(PermissionError, match="invalid token"):
            await worker_entrypoint._validate_run_jwt_param({"run_jwt": token})


@pytest.mark.asyncio
async def test_missing_secret_fails_the_request_not_the_worker(monkeypatch):
    """#13265: RuntimeError from _secret() would escape _handle_request and kill the serve loop."""
    from services.mcp_bridge_workers import worker_entrypoint

    token = _mint()
    monkeypatch.delenv("RUN_JWT_SECRET", raising=False)
    monkeypatch.delenv("AUTOBOT_JWT_SECRET", raising=False)
    with patch.object(worker_entrypoint, "_JWT_ENFORCE", True), patch.object(
        config.misc, "run_jwt_secret", ""
    ), patch.object(config.misc, "jwt_secret", ""):
        with pytest.raises(PermissionError, match="cannot verify token"):
            await worker_entrypoint._validate_run_jwt_param({"run_jwt": token})


# ---------------------------------------------------------------------------
# Scrubbed-environment secret resolution
# ---------------------------------------------------------------------------


def test_secret_resolves_from_config_when_environment_is_scrubbed(monkeypatch):
    """#13265: workers run without RUN_JWT_SECRET in os.environ (_WORKER_ENV_ALLOW)."""
    from services.run_jwt import _secret

    monkeypatch.delenv("RUN_JWT_SECRET", raising=False)
    monkeypatch.delenv("AUTOBOT_JWT_SECRET", raising=False)
    with patch.object(config.misc, "run_jwt_secret", "from-dot-env-file"):
        assert _secret() == "from-dot-env-file"


def test_environment_keeps_priority_over_config(monkeypatch):
    """Existing deployments that export the variable are unaffected."""
    from services.run_jwt import _secret

    monkeypatch.setenv("RUN_JWT_SECRET", "from-environment")
    with patch.object(config.misc, "run_jwt_secret", "from-dot-env-file"):
        assert _secret() == "from-environment"


def test_run_jwt_secret_has_no_default():
    """No shipped credential: the field must default to empty (#13263 precedent)."""
    field = type(config.misc).model_fields["run_jwt_secret"]
    assert field.default == ""


def test_worker_env_allow_still_excludes_the_token(monkeypatch):
    """#13265 passes run_jwt per request; it must not become a long-lived env var."""
    from services.mcp_isolated_runtime import _WORKER_ENV_ALLOW

    assert "MCP_RUN_JWT" not in _WORKER_ENV_ALLOW
    assert "RUN_JWT_SECRET" not in _WORKER_ENV_ALLOW
