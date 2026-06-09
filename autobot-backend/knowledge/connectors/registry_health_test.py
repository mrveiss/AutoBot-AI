# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for ConnectorRegistry.health_check_all() — Issue #4420.

Covers:
  - empty registry returns empty lists
  - all connectors healthy
  - mixed healthy / unhealthy
  - one connector raises → captured in errors
  - concurrent execution (total runtime << sum of individual delays)
  - label format: {connector_type}:{name}
"""

import os
import sys
import time
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

# ---------------------------------------------------------------------------
# Ensure the autobot-backend package root is on sys.path
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.registry import ConnectorRegistry
from tests.helpers.fake_connector import FakeConnector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(connector_id: str, connector_type: str, name: str) -> ConnectorConfig:
    return ConnectorConfig(
        connector_id=connector_id,
        connector_type=connector_type,
        name=name,
        config={},
    )


@pytest.fixture(autouse=True)
def _clear_registry():
    """Guarantee clean registry state between tests (Issue #4420)."""
    ConnectorRegistry._instances.clear()
    yield
    ConnectorRegistry._instances.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_registry_returns_empty_structure():
    result = await ConnectorRegistry.health_check_all()
    assert result["healthy"] == []
    assert result["unavailable"] == []
    assert result["errors"] == {}
    assert "checked_at" in result
    # Validate timestamp parses as ISO 8601 UTC
    parsed = datetime.fromisoformat(result["checked_at"])
    assert parsed.tzinfo is not None


@pytest.mark.asyncio
async def test_all_connectors_healthy():
    for i in range(3):
        cfg = _make_config(f"id-{i}", "file_server", f"src-{i}")
        ConnectorRegistry.add_instance(FakeConnector(cfg, result=True))

    result = await ConnectorRegistry.health_check_all()
    assert sorted(result["healthy"]) == [
        "file_server:src-0",
        "file_server:src-1",
        "file_server:src-2",
    ]
    assert result["unavailable"] == []
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_mixed_healthy_and_unhealthy():
    ConnectorRegistry.add_instance(FakeConnector(_make_config("a", "file_server", "docs-nfs"), result=True))
    ConnectorRegistry.add_instance(FakeConnector(_make_config("b", "web_crawler", "internal-wiki"), result=True))
    ConnectorRegistry.add_instance(FakeConnector(_make_config("c", "notion", "workspace-1"), result=False))

    result = await ConnectorRegistry.health_check_all()
    assert result["healthy"] == ["file_server:docs-nfs", "web_crawler:internal-wiki"]
    assert result["unavailable"] == ["notion:workspace-1"]
    # False (not exception) → no error string
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_connector_exception_captured_in_errors():
    ConnectorRegistry.add_instance(FakeConnector(_make_config("a", "file_server", "good"), result=True))
    ConnectorRegistry.add_instance(
        FakeConnector(
            _make_config("b", "notion", "workspace-1"),
            result=RuntimeError("401 Unauthorized"),
        )
    )

    result = await ConnectorRegistry.health_check_all()
    assert result["healthy"] == ["file_server:good"]
    assert result["unavailable"] == ["notion:workspace-1"]
    assert "notion:workspace-1" in result["errors"]
    assert "401 Unauthorized" in result["errors"]["notion:workspace-1"]


@pytest.mark.asyncio
async def test_one_failure_does_not_block_others():
    """Verify asyncio.gather(return_exceptions=False) path: _check_one never raises."""
    ConnectorRegistry.add_instance(FakeConnector(_make_config("a", "t", "one"), result=ValueError("boom")))
    ConnectorRegistry.add_instance(FakeConnector(_make_config("b", "t", "two"), result=True))
    ConnectorRegistry.add_instance(FakeConnector(_make_config("c", "t", "three"), result=True))

    result = await ConnectorRegistry.health_check_all()
    assert sorted(result["healthy"]) == ["t:three", "t:two"]
    assert result["unavailable"] == ["t:one"]
    assert "boom" in result["errors"]["t:one"]


@pytest.mark.asyncio
async def test_checks_run_concurrently():
    """Total runtime should be ~max(delays), not sum(delays) (Issue #4420)."""
    delay = 0.15
    for i in range(5):
        cfg = _make_config(f"id-{i}", "slow", f"n-{i}")
        ConnectorRegistry.add_instance(FakeConnector(cfg, result=True, delay=delay))

    start = time.monotonic()
    result = await ConnectorRegistry.health_check_all()
    elapsed = time.monotonic() - start

    assert len(result["healthy"]) == 5
    # Sequential would be 5 * 0.15 = 0.75s. Concurrent should be ~0.15s.
    # Allow generous overhead but still catch sequential execution.
    assert elapsed < 0.5, f"health_check_all took {elapsed:.3f}s — not concurrent"


@pytest.mark.asyncio
async def test_label_falls_back_to_connector_id_when_name_missing():
    cfg = _make_config("only-id", "file_server", "")
    ConnectorRegistry.add_instance(FakeConnector(cfg, result=True))

    result = await ConnectorRegistry.health_check_all()
    assert result["healthy"] == ["file_server:only-id"]


@pytest.mark.asyncio
async def test_async_mock_connector():
    """Verify health check works against AsyncMock-style connectors too."""
    cfg = _make_config("am", "file_server", "mock")
    instance = FakeConnector(cfg, result=True)
    instance.test_connection = AsyncMock(return_value=True)
    ConnectorRegistry.add_instance(instance)

    result = await ConnectorRegistry.health_check_all()
    assert result["healthy"] == ["file_server:mock"]
    instance.test_connection.assert_awaited_once()
