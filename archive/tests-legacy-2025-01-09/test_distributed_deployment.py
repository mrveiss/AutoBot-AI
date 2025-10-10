#!/usr/bin/env python3
"""
Integration Tests for Distributed Deployment
============================================

Tests the Service Registry and distributed deployment functionality
across different deployment modes and configurations.
"""

import asyncio
import os

# Add project root to path
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.service_registry import (
    DeploymentMode,
    ServiceConfig,
    ServiceRegistry,
    ServiceStatus,
    get_service_registry,
    get_service_url,
)


class TestServiceRegistry:
    """Test Service Registry functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.test_config_dir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        if self.test_config_dir.exists():
            shutil.rmtree(self.test_config_dir)

    def create_test_config(self, config_data: dict) -> Path:
        """Create a test configuration file."""
        config_file = self.test_config_dir / "test_config.yml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)
        return config_file

    def test_service_registry_initialization(self):
        """Test Service Registry initialization with default config."""
        registry = ServiceRegistry()

        assert registry.deployment_mode == DeploymentMode.LOCAL
        assert registry.domain == "autobot.local"
        assert len(registry.services) > 0
        assert "redis" in registry.services
        assert "backend" in registry.services

    def test_service_registry_custom_config(self):
        """Test Service Registry with custom configuration."""
        config_data = {
            "deployment_mode": "distributed",
            "domain": "production.autobot.com",
            "services": {
                "redis": {
                    "host": "redis.production.com",
                    "port": 6379,
                    "scheme": "redis",
                },
                "backend": {
                    "host": "api.production.com",
                    "port": 8001,
                    "scheme": "https",
                },
            },
        }

        config_file = self.create_test_config(config_data)
        registry = ServiceRegistry(str(config_file))

        assert registry.deployment_mode == DeploymentMode.DISTRIBUTED
        assert registry.domain == "production.autobot.com"

        redis_config = registry.get_service_config("redis")
        assert redis_config.host == "redis.production.com"
        assert redis_config.port == 6379
        assert redis_config.scheme == "redis"

    def test_get_service_url(self):
        """Test service URL generation."""
        config_data = {
            "deployment_mode": "docker_local",
            "services": {
                "backend": {"host": "autobot-backend", "port": 8001, "scheme": "http"}
            },
        }

        config_file = self.create_test_config(config_data)
        registry = ServiceRegistry(str(config_file))

        # Test basic URL
        url = registry.get_service_url("backend")
        assert url == "http://autobot-backend:8001"

        # Test URL with path
        url_with_path = registry.get_service_url("backend", "/api/health")
        assert url_with_path == "http://autobot-backend:8001/api/health"

    def test_service_not_found(self):
        """Test behavior when service is not found."""
        registry = ServiceRegistry()

        config = registry.get_service_config("nonexistent")
        assert config is None

        with pytest.raises(KeyError):
            registry.get_service_url("nonexistent")

    def test_deployment_mode_validation(self):
        """Test deployment mode validation."""
        config_data = {"deployment_mode": "invalid_mode"}

        config_file = self.create_test_config(config_data)

        # Should fall back to LOCAL mode
        registry = ServiceRegistry(str(config_file))
        assert registry.deployment_mode == DeploymentMode.LOCAL

    @pytest.mark.asyncio
    async def test_service_health_check_success(self):
        """Test successful service health check."""
        registry = ServiceRegistry()

        # Mock successful HTTP response
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None
            mock_get.return_value = mock_response

            health = await registry.check_service_health("backend")
            assert health.status == ServiceStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_service_health_check_failure(self):
        """Test failed service health check."""
        registry = ServiceRegistry()

        # Mock failed HTTP response
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status = 503
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None
            mock_get.return_value = mock_response

            health = await registry.check_service_health("backend")
            assert health.status == ServiceStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_service_health_check_timeout(self):
        """Test service health check with timeout."""
        registry = ServiceRegistry()

        # Mock timeout exception
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.side_effect = asyncio.TimeoutError()

            health = await registry.check_service_health("backend")
            assert health.status == ServiceStatus.UNREACHABLE

    @pytest.mark.asyncio
    async def test_check_all_services_health(self):
        """Test checking health of all services."""
        registry = ServiceRegistry()

        # Mock successful responses for all services
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None
            mock_get.return_value = mock_response

            health_results = await registry.check_all_services_health()

            assert len(health_results) > 0
            for service, health in health_results.items():
                assert health.status == ServiceStatus.HEALTHY

    def test_list_services(self):
        """Test listing all services."""
        registry = ServiceRegistry()
        services = registry.list_services()

        assert isinstance(services, list)
        assert len(services) > 0
        assert "redis" in services
        assert "backend" in services

    def test_get_deployment_info(self):
        """Test getting deployment information."""
        registry = ServiceRegistry()
        info = registry.get_deployment_info()

        assert "deployment_mode" in info
        assert "domain" in info
        assert "services_count" in info
        assert "services" in info

        assert info["deployment_mode"] == "local"
        assert info["services_count"] == len(registry.services)


class TestDistributedDeploymentScenarios:
    """Test different distributed deployment scenarios."""

    def setup_method(self):
        """Set up test environment."""
        self.test_config_dir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        if self.test_config_dir.exists():
            shutil.rmtree(self.test_config_dir)

    def create_test_config(self, config_data: dict) -> Path:
        """Create a test configuration file."""
        config_file = self.test_config_dir / "test_config.yml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)
        return config_file

    def test_local_deployment_config(self):
        """Test local hybrid deployment configuration."""
        registry = ServiceRegistry()

        # Should use localhost for all services
        redis_url = registry.get_service_url("redis")
        backend_url = registry.get_service_url("backend")

        assert "localhost" in redis_url
        assert "localhost" in backend_url

    def test_docker_local_deployment_config(self):
        """Test full Docker local deployment configuration."""
        config_data = {
            "deployment_mode": "docker_local",
            "services": {
                "redis": {"host": "autobot-redis", "port": 6379},
                "backend": {"host": "autobot-backend", "port": 8001},
            },
        }

        config_file = self.create_test_config(config_data)
        registry = ServiceRegistry(str(config_file))

        redis_url = registry.get_service_url("redis")
        backend_url = registry.get_service_url("backend")

        assert "autobot-redis" in redis_url
        assert "autobot-backend" in backend_url

    def test_distributed_deployment_config(self):
        """Test distributed deployment across multiple machines."""
        config_data = {
            "deployment_mode": "distributed",
            "services": {
                "redis": {"host": "redis-server.internal", "port": 6379},
                "ai-stack": {"host": "gpu-node-1.internal", "port": 11434},
                "npu-worker": {"host": "npu-node-1.internal", "port": 8081},
                "backend": {"host": "api-server.internal", "port": 8001},
            },
        }

        config_file = self.create_test_config(config_data)
        registry = ServiceRegistry(str(config_file))

        assert registry.deployment_mode == DeploymentMode.DISTRIBUTED

        redis_url = registry.get_service_url("redis")
        ai_stack_url = registry.get_service_url("ai-stack")
        npu_url = registry.get_service_url("npu-worker")
        backend_url = registry.get_service_url("backend")

        assert "redis-server.internal" in redis_url
        assert "gpu-node-1.internal" in ai_stack_url
        assert "npu-node-1.internal" in npu_url
        assert "api-server.internal" in backend_url

    def test_kubernetes_deployment_config(self):
        """Test Kubernetes deployment configuration."""
        config_data = {
            "deployment_mode": "kubernetes",
            "services": {
                "redis": {"host": "autobot-redis-service", "port": 6379},
                "backend": {"host": "autobot-backend-service", "port": 8001},
            },
        }

        config_file = self.create_test_config(config_data)
        registry = ServiceRegistry(str(config_file))

        assert registry.deployment_mode == DeploymentMode.KUBERNETES

        redis_url = registry.get_service_url("redis")
        backend_url = registry.get_service_url("backend")

        assert "autobot-redis-service" in redis_url
        assert "autobot-backend-service" in backend_url


class TestServiceDiscoveryIntegration:
    """Test service discovery integration across the codebase."""

    @pytest.mark.asyncio
    async def test_redis_database_manager_integration(self):
        """Test Redis database manager uses service registry."""
        from src.utils.redis_database_manager import RedisDatabaseManager

        # Mock service registry
        with patch(
            "src.utils.redis_database_manager.get_service_registry"
        ) as mock_registry:
            mock_config = MagicMock()
            mock_config.host = "test-redis-host"
            mock_config.port = 6379

            mock_registry_instance = MagicMock()
            mock_registry_instance.get_service_config.return_value = mock_config
            mock_registry.return_value = mock_registry_instance

            # Test that Redis manager gets config from service registry
            with patch("redis.asyncio.Redis") as mock_redis:
                manager = RedisDatabaseManager()

                # Verify service registry was called
                mock_registry.assert_called_once()
                mock_registry_instance.get_service_config.assert_called_with("redis")

    def test_llm_interface_uses_service_registry(self):
        """Test LLM interface uses service registry for Ollama."""
        from src.llm_interface_unified import UnifiedLLMInterface

        # Mock service registry to return test Ollama URL
        with patch("src.llm_interface_unified.get_service_url") as mock_get_url:
            mock_get_url.return_value = "http://test-ollama-host:11434"

            # Initialize LLM interface
            llm = UnifiedLLMInterface()

            # Check that it used service registry
            mock_get_url.assert_called()

    def test_npu_integration_uses_service_registry(self):
        """Test NPU integration uses service registry."""
        from src.npu_integration import NPUWorkerClient

        with patch("src.npu_integration.get_service_url") as mock_get_url:
            mock_get_url.return_value = "http://test-npu-host:8081"

            client = NPUWorkerClient()

            mock_get_url.assert_called_with("npu-worker")
            assert client.npu_endpoint == "http://test-npu-host:8081"


class TestDeploymentAutomation:
    """Test deployment automation scripts."""

    def test_deployment_script_exists(self):
        """Test that deployment script exists and is executable."""
        script_path = Path(__file__).parent.parent / "scripts/deploy_autobot.py"
        assert script_path.exists()
        assert os.access(script_path, os.X_OK)

    def test_deployment_wrapper_exists(self):
        """Test that deployment wrapper script exists."""
        wrapper_path = Path(__file__).parent.parent / "deploy.sh"
        assert wrapper_path.exists()
        assert os.access(wrapper_path, os.X_OK)

    def test_docker_compose_files_exist(self):
        """Test that required Docker Compose files exist."""
        compose_dir = Path(__file__).parent.parent / "docker/compose"

        required_files = [
            "docker-compose.hybrid.yml",
            "docker-compose.full.yml",
            "docker-compose.redis.yml",
            "docker-compose.ai-stack.yml",
            "docker-compose.npu-worker.yml",
        ]

        for filename in required_files:
            file_path = compose_dir / filename
            assert file_path.exists(), f"Missing compose file: {filename}"

    def test_deployment_config_files_exist(self):
        """Test that deployment configuration files exist."""
        config_dir = Path(__file__).parent.parent / "config/deployment"

        required_configs = [
            "local.yml",
            "docker_local.yml",
            "distributed.yml",
            "kubernetes.yml",
        ]

        for config_file in required_configs:
            file_path = config_dir / config_file
            assert file_path.exists(), f"Missing config file: {config_file}"


class TestServiceRegistryCLI:
    """Test Service Registry CLI tool."""

    def test_cli_script_exists(self):
        """Test CLI script exists and is executable."""
        cli_path = Path(__file__).parent.parent / "src/utils/service_registry_cli.py"
        assert cli_path.exists()
        assert os.access(cli_path, os.X_OK)

    @pytest.mark.asyncio
    async def test_cli_status_command(self):
        """Test CLI status command functionality."""
        from src.utils.service_registry_cli import cmd_status

        # Mock arguments
        args = MagicMock()
        args.config = None

        # Should not raise exception
        result = cmd_status(args)
        assert result == 0

    @pytest.mark.asyncio
    async def test_cli_health_command(self):
        """Test CLI health command functionality."""
        from src.utils.service_registry_cli import cmd_health

        args = MagicMock()
        args.config = None

        # Mock service health checks
        with patch(
            "src.utils.service_registry.ServiceRegistry.check_all_services_health"
        ) as mock_health:
            mock_health.return_value = {}

            result = await cmd_health(args)
            # May return 1 if no services are healthy, which is expected in test
            assert result in [0, 1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
