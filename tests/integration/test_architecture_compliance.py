#!/usr/bin/env python3
"""
Architecture Compliance Tests
=============================

Tests to ensure AutoBot's distributed architecture is properly configured
and services are running on their designated VMs.

This replaces manual architecture fix scripts with automated validation.
"""

import pytest
import redis
import socket
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import unified_config_manager
from src.constants.network_constants import NetworkConstants
from src.utils.redis_client import get_redis_client


class TestServiceDistribution:
    """Test that services are running on correct VMs"""

    def test_redis_on_vm3_only(self):
        """Ensure Redis runs only on VM3 (Redis VM)"""
        redis_config = unified_config_manager.get_redis_config()
        redis_host = redis_config.get("host")

        assert redis_host == NetworkConstants.REDIS_VM_IP, (
            f"Redis must run on VM3 ({NetworkConstants.REDIS_VM_IP}), currently configured for: {redis_host}"
        )

    def test_backend_on_main_machine(self):
        """Ensure backend runs on main machine"""
        backend_config = unified_config_manager.get_backend_config()
        backend_host = backend_config.get("host")

        assert backend_host in [NetworkConstants.MAIN_MACHINE_IP, "0.0.0.0"], (
            f"Backend must run on main machine ({NetworkConstants.MAIN_MACHINE_IP}), currently configured for: {backend_host}"
        )

    def test_frontend_on_vm1(self):
        """Ensure frontend runs on VM1 (Frontend VM)"""
        services_config = unified_config_manager.get_distributed_services_config()
        frontend_config = services_config.get("frontend", {})
        frontend_host = frontend_config.get("host")

        assert frontend_host == NetworkConstants.FRONTEND_VM_IP, (
            f"Frontend must run on VM1 ({NetworkConstants.FRONTEND_VM_IP}), currently configured for: {frontend_host}"
        )

    def test_npu_worker_on_vm2(self):
        """Ensure NPU worker runs on VM2 (NPU Worker VM)"""
        services_config = unified_config_manager.get_distributed_services_config()
        npu_config = services_config.get("npu_worker", {})
        npu_host = npu_config.get("host")

        assert npu_host == NetworkConstants.NPU_WORKER_VM_IP, (
            f"NPU worker must run on VM2 (NPU Worker VM), currently configured for: {npu_host}"
        )

    def test_ai_stack_on_vm4(self):
        """Ensure AI stack runs on VM4 (AI Stack VM)"""
        services_config = unified_config_manager.get_distributed_services_config()
        ai_config = services_config.get("ai_stack", {})
        ai_host = ai_config.get("host")

        assert ai_host == NetworkConstants.AI_STACK_VM_IP, (
            f"AI stack must run on VM4 (AI Stack VM), currently configured for: {ai_host}"
        )

    def test_browser_service_on_vm5(self):
        """Ensure browser service runs on VM5 (Browser VM)"""
        services_config = unified_config_manager.get_distributed_services_config()
        browser_config = services_config.get("browser_service", {})
        browser_host = browser_config.get("host")

        assert browser_host == NetworkConstants.BROWSER_VM_IP, (
            f"Browser service must run on VM5 (Browser VM), currently configured for: {browser_host}"
        )


class TestNetworkConfiguration:
    """Test network configuration compliance"""

    def test_no_localhost_in_distributed_services(self):
        """Ensure no services use localhost in distributed configuration"""
        services_config = unified_config_manager.get_distributed_services_config()

        for service_name, service_config in services_config.items():
            if isinstance(service_config, dict):
                host = service_config.get("host")
                if host:
                    assert host not in ["localhost", "127.0.0.1"], (
                        f"Service '{service_name}' uses localhost ({host}), must use actual IP"
                    )

    def test_backend_binds_to_all_interfaces(self):
        """Ensure backend binds to 0.0.0.0 for network accessibility"""
        backend_config = unified_config_manager.get_backend_config()
        backend_host = backend_config.get("host")

        # Backend should bind to 0.0.0.0 to be accessible from VMs
        assert backend_host in ["0.0.0.0", NetworkConstants.MAIN_MACHINE_IP], (
            f"Backend must bind to 0.0.0.0 or {NetworkConstants.MAIN_MACHINE_IP}, currently: {backend_host}"
        )

    def test_redis_uses_standard_port(self):
        """Ensure Redis uses standard port 6379"""
        redis_config = unified_config_manager.get_redis_config()
        redis_port = redis_config.get("port")

        assert redis_port == 6379, (
            f"Redis must use standard port 6379, currently configured for: {redis_port}"
        )


class TestConfigurationSource:
    """Test that configuration comes from unified_config_manager"""

    def test_no_hardcoded_ips_in_redis_helper(self):
        """Ensure redis_helper uses unified_config_manager"""
        from src.utils.redis_helper import REDIS_HOST

        # These should come from configuration, not be hardcoded
        assert REDIS_HOST != NetworkConstants.REDIS_VM_IP or (
            hasattr(redis_helper, 'redis_config') and redis_helper.redis_config is not None
        ), "redis_helper should use configuration, not hardcoded IP"

    def test_service_discovery_has_defaults(self):
        """Ensure service_discovery_defaults section exists"""
        defaults = unified_config_manager.get_config_section("service_discovery_defaults")

        assert defaults is not None, "service_discovery_defaults section must exist"
        assert "redis_host" in defaults, "redis_host must be in defaults"
        assert "redis_port" in defaults, "redis_port must be in defaults"
        assert "backend_host" in defaults, "backend_host must be in defaults"
        assert "backend_port" in defaults, "backend_port must be in defaults"


class TestRedisConnection:
    """Test Redis connection configuration"""

    @pytest.mark.integration
    def test_redis_connectivity(self):
        """Test that Redis is accessible at configured host"""
        try:
            # Use canonical get_redis_client() pattern for consistency
            client = get_redis_client(async_client=False, database="main")
            client.ping()
            assert True, "Redis connection successful"
        except (redis.ConnectionError, socket.timeout) as e:
            pytest.skip(f"Redis not available (expected in CI): {e}")

    @pytest.mark.integration
    def test_redis_timeout_configuration(self):
        """Test that Redis connections have proper timeout settings"""
        from src.utils.redis_helper import TIMEOUT_CONFIG

        assert TIMEOUT_CONFIG['socket_timeout'] > 0, "socket_timeout must be positive"
        assert TIMEOUT_CONFIG['socket_connect_timeout'] > 0, "socket_connect_timeout must be positive"
        assert TIMEOUT_CONFIG['retry_on_timeout'] is True, "retry_on_timeout should be enabled"
        assert TIMEOUT_CONFIG['max_retries'] > 0, "max_retries must be positive"


class TestPortConfiguration:
    """Test port assignments"""

    def test_standard_port_assignments(self):
        """Ensure services use their standard ports"""
        backend_config = unified_config_manager.get_backend_config()
        redis_config = unified_config_manager.get_redis_config()
        services_config = unified_config_manager.get_distributed_services_config()

        # Backend
        assert backend_config.get("port") == 8001, "Backend must use port 8001"

        # Redis
        assert redis_config.get("port") == 6379, "Redis must use port 6379"

        # Frontend
        frontend_port = services_config.get("frontend", {}).get("port")
        assert frontend_port == 5173, "Frontend must use port 5173"

        # NPU Worker
        npu_port = services_config.get("npu_worker", {}).get("port")
        assert npu_port == 8081, "NPU worker must use port 8081"

        # AI Stack
        ai_port = services_config.get("ai_stack", {}).get("port")
        assert ai_port == 8080, "AI stack must use port 8080"

        # Browser Service
        browser_port = services_config.get("browser_service", {}).get("port")
        assert browser_port == 3000, "Browser service must use port 3000"


class TestSingleFrontendServer:
    """Test that only one frontend server is configured"""

    def test_only_one_frontend_instance(self):
        """Ensure frontend only runs on VM1, not on main machine"""
        services_config = unified_config_manager.get_distributed_services_config()
        frontend_config = services_config.get("frontend", {})
        frontend_host = frontend_config.get("host")

        # Frontend must ONLY be on VM1
        assert frontend_host == NetworkConstants.FRONTEND_VM_IP, (
            f"Frontend must run ONLY on VM1 ({NetworkConstants.FRONTEND_VM_IP}), found: {frontend_host}"
        )

        # Backend should NOT be configured to run frontend
        backend_config = unified_config_manager.get_backend_config()
        backend_host = backend_config.get("host")
        assert backend_host != NetworkConstants.FRONTEND_VM_IP, (
            "Backend must not run on frontend VM"
        )


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
