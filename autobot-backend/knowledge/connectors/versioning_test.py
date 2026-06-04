# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Tests for connector config schema versioning and migration (Issue #8152).
"""

from unittest.mock import AsyncMock, patch

import pytest

from knowledge.connectors.base import AbstractConnector
from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.registry import ConnectorRegistry
from knowledge.connectors.web_crawler import WebCrawlerConnector


def _make_config(connector_type: str = "web_crawler", config: dict | None = None) -> ConnectorConfig:
    return ConnectorConfig(
        connector_id="test-conn-001",
        connector_type=connector_type,
        name="Test Connector",
        config=config or {"urls": ["https://example.com"]},
    )


@pytest.mark.asyncio
async def test_create_no_migration_needed():
    """When stored_version == config_version, no migration is called."""
    cfg = _make_config(config={"urls": ["https://example.com"], "_version": 2, "crawl_depth": 3})
    with patch.object(WebCrawlerConnector, "migrate_config", wraps=WebCrawlerConnector.migrate_config) as mock_migrate:
        instance = await ConnectorRegistry.create(cfg)
    mock_migrate.assert_not_called()
    assert isinstance(instance, WebCrawlerConnector)


@pytest.mark.asyncio
async def test_create_migration_called_on_version_mismatch():
    """When stored_version < config_version, migrate_config() is called."""
    cfg = _make_config(config={"urls": ["https://example.com"], "max_depth": 3, "_version": 1})
    with patch.object(ConnectorRegistry, "_persist_config", new=AsyncMock()) as mock_persist:
        await ConnectorRegistry.create(cfg)
    assert "crawl_depth" in cfg.config
    assert cfg.config.get("crawl_depth") == 3
    assert "max_depth" not in cfg.config
    assert cfg.config.get("_version") == 2
    mock_persist.assert_called_once()


@pytest.mark.asyncio
async def test_create_migration_failure_raises_value_error():
    """When migrate_config() raises, create() raises ValueError."""
    cfg = _make_config(config={"urls": ["https://example.com"], "_version": 1})
    with patch.object(WebCrawlerConnector, "migrate_config", side_effect=RuntimeError("bad config")):
        with pytest.raises(ValueError, match="Config migration failed"):
            await ConnectorRegistry.create(cfg)


@pytest.mark.asyncio
async def test_no_version_key_treated_as_version_1():
    """Configs without _version key are treated as version 1 (backward compat)."""
    cfg = _make_config(config={"urls": ["https://example.com"], "max_depth": 2})
    with patch.object(ConnectorRegistry, "_persist_config", new=AsyncMock()) as mock_persist:
        await ConnectorRegistry.create(cfg)
    assert cfg.config.get("_version") == 2
    assert cfg.config.get("crawl_depth") == 2
    mock_persist.assert_called_once()


@pytest.mark.asyncio
async def test_web_crawler_v1_to_v2_renames_max_depth():
    """WebCrawlerConnector.migrate_config renames max_depth to crawl_depth."""
    config = {"urls": ["https://example.com"], "max_depth": 5}
    result = WebCrawlerConnector.migrate_config(1, config)
    assert "crawl_depth" in result
    assert result["crawl_depth"] == 5
    assert "max_depth" not in result


@pytest.mark.asyncio
async def test_web_crawler_migrate_idempotent_when_crawl_depth_present():
    """migrate_config does not overwrite crawl_depth if already present."""
    config = {"urls": ["https://example.com"], "max_depth": 5, "crawl_depth": 2}
    result = WebCrawlerConnector.migrate_config(1, config)
    assert result["crawl_depth"] == 2
    assert "max_depth" in result


@pytest.mark.asyncio
async def test_persist_config_patches_redis_blob():
    """_persist_config reads, patches config field, and writes back."""
    import json

    cfg = _make_config(config={"urls": ["https://example.com"], "_version": 2})
    existing_blob = json.dumps(
        {
            "connector_id": cfg.connector_id,
            "connector_type": cfg.connector_type,
            "name": cfg.name,
            "config": {"urls": ["https://example.com"], "_version": 1},
        }
    )
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=existing_blob.encode("utf-8"))
    mock_redis.set = AsyncMock()
    with patch("autobot_shared.redis_client.get_async_redis_client", return_value=mock_redis):
        await ConnectorRegistry._persist_config(cfg)
    mock_redis.set.assert_called_once()
    stored = json.loads(mock_redis.set.call_args[0][1])
    assert stored["config"]["_version"] == 2


@pytest.mark.asyncio
async def test_abstract_connector_config_version_defaults_to_1():
    """AbstractConnector.config_version defaults to 1."""
    assert AbstractConnector.config_version == 1


@pytest.mark.asyncio
async def test_abstract_connector_migrate_config_is_noop():
    """AbstractConnector.migrate_config returns config unchanged."""
    config = {"key": "value"}
    result = AbstractConnector.migrate_config(1, config)
    assert result == {"key": "value"}
