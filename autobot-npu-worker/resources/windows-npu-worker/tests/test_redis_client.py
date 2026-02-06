# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Windows NPU Worker Redis Client Utility (Issue #151)

Tests the standalone Redis client implementation with connection pooling,
retry logic, and health monitoring for the Windows NPU worker.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# Add app directory to path for imports
app_dir = Path(__file__).parent.parent / "app"
sys.path.insert(0, str(app_dir))


class TestRedisConnectionManager:
    """Tests for RedisConnectionManager class"""

    @pytest.fixture
    def sample_config(self):
        """Sample configuration for testing"""
        return {
            "redis": {
                "host": "172.16.168.23",
                "port": 6379,
                "password": None,
                "db": 0,
                "max_connections": 20,
                "socket_timeout": 5,
                "socket_connect_timeout": 2,
                "retry_on_timeout": True,
            }
        }

    @pytest.fixture
    def config_with_password(self):
        """Configuration with password authentication"""
        return {
            "redis": {
                "host": "172.16.168.23",
                "port": 6379,
                "password": "secret_password",
                "db": 1,
                "max_connections": 10,
                "socket_timeout": 3,
                "socket_connect_timeout": 1,
                "retry_on_timeout": True,
            }
        }

    @pytest.fixture
    def config_no_retry(self):
        """Configuration without retry logic"""
        return {
            "redis": {
                "host": "localhost",
                "port": 6379,
                "password": None,
                "db": 0,
                "max_connections": 5,
                "socket_timeout": 5,
                "socket_connect_timeout": 2,
                "retry_on_timeout": False,
            }
        }

    @pytest.mark.asyncio
    async def test_connection_manager_initialization(self, sample_config):
        """Test that connection manager initializes correctly"""
        from utils.redis_client import RedisConnectionManager

        manager = RedisConnectionManager(sample_config)

        assert manager.config == sample_config
        assert manager.redis_config == sample_config["redis"]
        assert manager._connection_pool is None
        assert manager._client is None

    @pytest.mark.asyncio
    async def test_create_connection_pool_with_config(self, sample_config):
        """Test connection pool creation uses config values"""
        from utils.redis_client import RedisConnectionManager

        manager = RedisConnectionManager(sample_config)
        pool = manager._create_connection_pool()

        # Verify pool is created with correct config
        assert pool is not None
        assert pool.connection_kwargs["host"] == "172.16.168.23"
        assert pool.connection_kwargs["port"] == 6379
        assert pool.connection_kwargs["db"] == 0
        assert pool.max_connections == 20
        assert pool.connection_kwargs["socket_timeout"] == 5
        assert pool.connection_kwargs["socket_connect_timeout"] == 2

    @pytest.mark.asyncio
    async def test_create_connection_pool_with_password(self, config_with_password):
        """Test connection pool creation with password authentication"""
        from utils.redis_client import RedisConnectionManager

        manager = RedisConnectionManager(config_with_password)
        pool = manager._create_connection_pool()

        assert pool.connection_kwargs["password"] == "secret_password"
        assert pool.connection_kwargs["db"] == 1

    @pytest.mark.asyncio
    async def test_create_connection_pool_without_retry(self, config_no_retry):
        """Test connection pool creation without retry logic"""
        from utils.redis_client import RedisConnectionManager

        manager = RedisConnectionManager(config_no_retry)
        pool = manager._create_connection_pool()

        # Pool should be created without retry
        assert pool is not None
        assert pool.connection_kwargs["retry_on_timeout"] is False

    @pytest.mark.asyncio
    async def test_get_client_success(self, sample_config):
        """Test successful client retrieval"""
        from utils.redis_client import RedisConnectionManager

        with patch("utils.redis_client.async_redis.Redis") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_redis.return_value = mock_client

            manager = RedisConnectionManager(sample_config)
            client = await manager.get_client()

            # Should return mock client
            assert client is not None
            mock_client.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_client_connection_failure(self, sample_config):
        """Test client returns None on connection failure"""
        from utils.redis_client import RedisConnectionManager

        with patch("utils.redis_client.async_redis.Redis") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(side_effect=Exception("Connection refused"))
            mock_redis.return_value = mock_client

            manager = RedisConnectionManager(sample_config)
            client = await manager.get_client()

            # Should return None on failure (graceful degradation)
            assert client is None

    @pytest.mark.asyncio
    async def test_get_client_caching(self, sample_config):
        """Test that client is cached after first retrieval"""
        from utils.redis_client import RedisConnectionManager

        with patch("utils.redis_client.async_redis.Redis") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_redis.return_value = mock_client

            manager = RedisConnectionManager(sample_config)

            # First call creates client
            client1 = await manager.get_client()

            # Second call returns cached client
            client2 = await manager.get_client()

            assert client1 is client2
            # Redis constructor should only be called once
            assert mock_redis.call_count == 1

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, sample_config):
        """Test health check returns True when Redis is healthy"""
        from utils.redis_client import RedisConnectionManager

        manager = RedisConnectionManager(sample_config)
        manager._client = AsyncMock()
        manager._client.ping = AsyncMock(return_value=True)

        result = await manager.health_check()

        assert result is True
        manager._client.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_no_client(self, sample_config):
        """Test health check returns False when no client"""
        from utils.redis_client import RedisConnectionManager

        manager = RedisConnectionManager(sample_config)
        # No client initialized

        result = await manager.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_ping_failure(self, sample_config):
        """Test health check returns False when ping fails"""
        from utils.redis_client import RedisConnectionManager

        manager = RedisConnectionManager(sample_config)
        manager._client = AsyncMock()
        manager._client.ping = AsyncMock(side_effect=Exception("Connection lost"))

        result = await manager.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_close_cleanup(self, sample_config):
        """Test close properly cleans up resources"""
        from utils.redis_client import RedisConnectionManager

        manager = RedisConnectionManager(sample_config)
        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()
        manager._client = mock_client
        manager._connection_pool = MagicMock()

        await manager.close()

        mock_client.aclose.assert_called_once()
        assert manager._client is None
        assert manager._connection_pool is None


class TestGetRedisClient:
    """Tests for get_redis_client module function"""

    @pytest.fixture
    def sample_config(self):
        return {
            "redis": {
                "host": "172.16.168.23",
                "port": 6379,
                "db": 0,
                "max_connections": 20,
                "socket_timeout": 5,
                "socket_connect_timeout": 2,
                "retry_on_timeout": True,
            }
        }

    @pytest.mark.asyncio
    async def test_get_redis_client_creates_manager(self, sample_config):
        """Test get_redis_client creates connection manager"""
        # Reset global state
        import utils.redis_client as redis_module

        redis_module._connection_manager = None

        with patch.object(
            redis_module.RedisConnectionManager, "get_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_get_client.return_value = AsyncMock()

            await redis_module.get_redis_client(sample_config)

            assert redis_module._connection_manager is not None
            mock_get_client.assert_called_once()

        # Cleanup
        redis_module._connection_manager = None

    @pytest.mark.asyncio
    async def test_close_redis_client(self, sample_config):
        """Test close_redis_client cleans up manager"""
        import utils.redis_client as redis_module

        # Setup mock manager
        mock_manager = AsyncMock()
        mock_manager.close = AsyncMock()
        redis_module._connection_manager = mock_manager

        await redis_module.close_redis_client()

        mock_manager.close.assert_called_once()
        assert redis_module._connection_manager is None


class TestConfigDefaults:
    """Tests for configuration defaults"""

    @pytest.mark.asyncio
    async def test_empty_config_uses_defaults(self):
        """Test that empty config uses sensible defaults"""
        from utils.redis_client import RedisConnectionManager

        # Config with minimal/missing values
        minimal_config = {"redis": {}}

        manager = RedisConnectionManager(minimal_config)
        pool = manager._create_connection_pool()

        # Verify defaults are used
        assert pool.connection_kwargs["host"] == "localhost"
        assert pool.connection_kwargs["port"] == 6379
        assert pool.connection_kwargs["db"] == 0
        assert pool.max_connections == 20

    @pytest.mark.asyncio
    async def test_missing_redis_section(self):
        """Test handling of missing redis config section"""
        from utils.redis_client import RedisConnectionManager

        # Config without redis section
        empty_config = {}

        manager = RedisConnectionManager(empty_config)
        pool = manager._create_connection_pool()

        # Should use all defaults
        assert pool is not None
        assert pool.connection_kwargs["host"] == "localhost"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
