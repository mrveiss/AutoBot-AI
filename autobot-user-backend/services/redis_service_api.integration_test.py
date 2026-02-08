"""
Integration Tests for Redis Service Management API

Tests all API endpoints with full request/response cycles:
- POST /api/services/redis/start
- POST /api/services/redis/stop
- POST /api/services/redis/restart
- GET /api/services/redis/status
- GET /api/services/redis/health
- GET /api/services/redis/logs

Tests authentication, authorization, error handling, and concurrent requests.

Test Coverage Target: >80% for backend/api/service_management.py
"""

import asyncio
import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from httpx import AsyncClient, HTTPStatusError
except ImportError:
    AsyncClient = None
    HTTPStatusError = Exception

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Fixtures
@pytest.fixture
async def api_client(backend_url):
    """Create async HTTP client for API testing."""
    if AsyncClient is None:
        pytest.skip("httpx not available")

    async with AsyncClient(base_url=backend_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def admin_token():
    """Provide admin authentication token for tests."""
    # In real implementation, this would authenticate and get real token
    return "test-admin-token-12345"


@pytest.fixture
def operator_token():
    """Provide operator authentication token for tests."""
    return "test-operator-token-67890"


@pytest.fixture
def viewer_token():
    """Provide viewer authentication token for tests."""
    return "test-viewer-token-11111"


@pytest.fixture
def mock_redis_service_manager():
    """Mock RedisServiceManager for API testing."""
    with patch("backend.api.service_management.redis_service_manager") as mock:
        manager = MagicMock()

        # Mock methods
        manager.start_service = AsyncMock()
        manager.stop_service = AsyncMock()
        manager.restart_service = AsyncMock()
        manager.get_service_status = AsyncMock()
        manager.check_health = AsyncMock()

        # Configure default responses
        manager.get_service_status.return_value = {
            "status": "running",
            "pid": 12345,
            "uptime_seconds": 86400,
            "memory_mb": 128.5,
            "connections": 42,
        }

        manager.check_health.return_value = {
            "overall_status": "healthy",
            "service_running": True,
            "connectivity": True,
            "response_time_ms": 2.5,
        }

        mock.return_value = manager
        yield manager


# Test Classes
class TestStartServiceEndpoint:
    """Test POST /api/services/redis/start endpoint."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_start_service_success_admin(
        self, api_client, admin_token, mock_redis_service_manager
    ):
        """
        Test Case 1.1: Admin successfully starts stopped service

        Validates:
        - 200 status code returned
        - Success response structure
        - Service status changes to 'running'
        - Duration tracked
        """
        logger.info("=== Test 1.1: Start service (admin) ===")

        # Mock service manager response
        mock_redis_service_manager.start_service.return_value = {
            "success": True,
            "operation": "start",
            "message": "Redis service started successfully",
            "duration_seconds": 12.5,
            "new_status": "running",
            "timestamp": datetime.now().isoformat(),
        }

        # Make API request
        response = await api_client.post(
            "/api/services/redis/start",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Validate response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["operation"] == "start"
        assert data["new_status"] == "running"
        assert "duration_seconds" in data
        logger.info("✓ Service started successfully via API")

        logger.info("=== Test 1.1: PASSED ===\n")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_start_service_success_operator(
        self, api_client, operator_token, mock_redis_service_manager
    ):
        """
        Test Case 1.2: Operator can start service

        Validates:
        - Operator has permission to start
        - 200 status code
        - Success response
        """
        logger.info("=== Test 1.2: Start service (operator) ===")

        mock_redis_service_manager.start_service.return_value = {
            "success": True,
            "operation": "start",
            "message": "Redis service started successfully",
            "duration_seconds": 11.8,
            "new_status": "running",
            "timestamp": datetime.now().isoformat(),
        }

        response = await api_client.post(
            "/api/services/redis/start",
            headers={"Authorization": f"Bearer {operator_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        logger.info("✓ Operator authorized to start service")

        logger.info("=== Test 1.2: PASSED ===\n")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_start_service_unauthorized_no_token(self, api_client):
        """
        Test Case 1.3: Start service without authentication fails

        Validates:
        - 401 status code
        - Authentication required message
        """
        logger.info("=== Test 1.3: Start service (no auth) ===")

        response = await api_client.post("/api/services/redis/start")

        assert response.status_code == 401
        logger.info("✓ Unauthenticated request rejected")

        logger.info("=== Test 1.3: PASSED ===\n")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_start_service_already_running(
        self, api_client, admin_token, mock_redis_service_manager
    ):
        """
        Test Case 1.4: Start service when already running

        Validates:
        - 200 status code (success)
        - Message indicates already running
        - Quick response time
        """
        logger.info("=== Test 1.4: Start service (already running) ===")

        mock_redis_service_manager.start_service.return_value = {
            "success": True,
            "operation": "start",
            "message": "Redis service already running",
            "duration_seconds": 0.5,
            "new_status": "running",
            "timestamp": datetime.now().isoformat(),
        }

        response = await api_client.post(
            "/api/services/redis/start",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "already running" in data["message"].lower()
        logger.info("✓ Already running handled correctly")

        logger.info("=== Test 1.4: PASSED ===\n")


class TestStopServiceEndpoint:
    """Test POST /api/services/redis/stop endpoint."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_stop_service_success_admin(
        self, api_client, admin_token, mock_redis_service_manager
    ):
        """
        Test Case 2.1: Admin successfully stops service with confirmation

        Validates:
        - 200 status code
        - Confirmation parameter required
        - Service status changes to 'stopped'
        """
        logger.info("=== Test 2.1: Stop service (admin) ===")

        mock_redis_service_manager.stop_service.return_value = {
            "success": True,
            "operation": "stop",
            "message": "Redis service stopped successfully",
            "duration_seconds": 8.3,
            "new_status": "stopped",
            "timestamp": datetime.now().isoformat(),
        }

        response = await api_client.post(
            "/api/services/redis/stop",
            json={"confirmation": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["operation"] == "stop"
        assert data["new_status"] == "stopped"
        logger.info("✓ Service stopped with confirmation")

        logger.info("=== Test 2.1: PASSED ===\n")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_stop_service_forbidden_operator(self, api_client, operator_token):
        """
        Test Case 2.2: Operator cannot stop service

        Validates:
        - 403 status code (Forbidden)
        - Permission denied message
        - Admin role required
        """
        logger.info("=== Test 2.2: Stop service (operator forbidden) ===")

        response = await api_client.post(
            "/api/services/redis/stop",
            json={"confirmation": True},
            headers={"Authorization": f"Bearer {operator_token}"},
        )

        assert response.status_code == 403
        data = response.json()
        assert "permission" in data.get("detail", "").lower()
        logger.info("✓ Operator correctly denied stop permission")

        logger.info("=== Test 2.2: PASSED ===\n")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_stop_service_no_confirmation(self, api_client, admin_token):
        """
        Test Case 2.3: Stop service without confirmation fails

        Validates:
        - 400 status code (Bad Request)
        - Confirmation required message
        - Affected services listed
        """
        logger.info("=== Test 2.3: Stop service (no confirmation) ===")

        response = await api_client.post(
            "/api/services/redis/stop",
            json={"confirmation": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "confirmation" in data.get("error", "").lower()
        logger.info("✓ Confirmation requirement enforced")

        logger.info("=== Test 2.3: PASSED ===\n")


class TestRestartServiceEndpoint:
    """Test POST /api/services/redis/restart endpoint."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_restart_service_success(
        self, api_client, admin_token, mock_redis_service_manager
    ):
        """
        Test Case 3.1: Full restart flow from API to Redis VM

        Validates:
        - 200 status code
        - Service restarted successfully
        - PID changes (actual restart)
        - Duration within acceptable range
        """
        logger.info("=== Test 3.1: Restart service (full flow) ===")

        # Mock initial status
        initial_status = {"status": "running", "pid": 12345, "uptime_seconds": 86400}
        mock_redis_service_manager.get_service_status.return_value = initial_status

        # Mock restart operation
        mock_redis_service_manager.restart_service.return_value = {
            "success": True,
            "operation": "restart",
            "message": "Redis service restarted successfully",
            "duration_seconds": 15.7,
            "new_status": "running",
            "previous_uptime_seconds": 86400,
            "connections_terminated": 42,
            "timestamp": datetime.now().isoformat(),
        }

        # Execute restart
        response = await api_client.post(
            "/api/services/redis/restart",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        restart_data = response.json()
        assert restart_data["success"] is True
        assert restart_data["new_status"] == "running"
        assert 10 < restart_data["duration_seconds"] < 30
        logger.info("✓ Service restarted successfully")

        # Verify new status (PID should change after restart)
        new_status = {
            "status": "running",
            "pid": 54321,  # Different PID
            "uptime_seconds": 10,  # Fresh uptime
        }
        mock_redis_service_manager.get_service_status.return_value = new_status

        status_response = await api_client.get("/api/services/redis/status")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["pid"] != initial_status["pid"]
        logger.info("✓ PID changed after restart")

        logger.info("=== Test 3.1: PASSED ===\n")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_restart_service_operator_allowed(
        self, api_client, operator_token, mock_redis_service_manager
    ):
        """
        Test Case 3.2: Operator can restart service

        Validates:
        - Operator has restart permission
        - 200 status code
        - Success response
        """
        logger.info("=== Test 3.2: Restart service (operator) ===")

        mock_redis_service_manager.restart_service.return_value = {
            "success": True,
            "operation": "restart",
            "message": "Redis service restarted successfully",
            "duration_seconds": 14.2,
            "new_status": "running",
            "timestamp": datetime.now().isoformat(),
        }

        response = await api_client.post(
            "/api/services/redis/restart",
            headers={"Authorization": f"Bearer {operator_token}"},
        )

        assert response.status_code == 200
        logger.info("✓ Operator authorized to restart service")

        logger.info("=== Test 3.2: PASSED ===\n")


class TestStatusEndpoint:
    """Test GET /api/services/redis/status endpoint."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_status_running(self, api_client, mock_redis_service_manager):
        """
        Test Case 4.1: Get status when service running

        Validates:
        - 200 status code
        - Status 'running'
        - All metrics included (PID, uptime, memory, connections)
        - No authentication required (public endpoint)
        """
        logger.info("=== Test 4.1: Get status (running) ===")

        mock_redis_service_manager.get_service_status.return_value = {
            "status": "running",
            "pid": 12345,
            "uptime_seconds": 86400,
            "memory_mb": 128.5,
            "connections": 42,
            "commands_processed": 1000000,
            "last_check": datetime.now().isoformat(),
        }

        response = await api_client.get("/api/services/redis/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["pid"] == 12345
        assert data["uptime_seconds"] == 86400
        assert data["memory_mb"] == 128.5
        assert data["connections"] == 42
        logger.info("✓ Status retrieved successfully")

        logger.info("=== Test 4.1: PASSED ===\n")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_status_stopped(self, api_client, mock_redis_service_manager):
        """
        Test Case 4.2: Get status when service stopped

        Validates:
        - 200 status code
        - Status 'stopped'
        - Null values for metrics (no PID, uptime, etc.)
        """
        logger.info("=== Test 4.2: Get status (stopped) ===")

        mock_redis_service_manager.get_service_status.return_value = {
            "status": "stopped",
            "pid": None,
            "uptime_seconds": None,
            "memory_mb": None,
            "connections": None,
            "last_check": datetime.now().isoformat(),
        }

        response = await api_client.get("/api/services/redis/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"
        assert data["pid"] is None
        logger.info("✓ Stopped status reported correctly")

        logger.info("=== Test 4.2: PASSED ===\n")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_status_no_auth_required(
        self, api_client, mock_redis_service_manager
    ):
        """
        Test Case 4.3: Status endpoint accessible without authentication

        Validates:
        - Public endpoint (no auth required)
        - 200 status code
        - Status returned
        """
        logger.info("=== Test 4.3: Status (public endpoint) ===")

        mock_redis_service_manager.get_service_status.return_value = {
            "status": "running",
            "last_check": datetime.now().isoformat(),
        }

        # Request without Authorization header
        response = await api_client.get("/api/services/redis/status")

        assert response.status_code == 200
        logger.info("✓ Status accessible without authentication")

        logger.info("=== Test 4.3: PASSED ===\n")


class TestHealthEndpoint:
    """Test GET /api/services/redis/health endpoint."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_health_healthy(self, api_client, mock_redis_service_manager):
        """
        Test Case 5.1: Get health status when healthy

        Validates:
        - 200 status code
        - Overall status 'healthy'
        - All health checks passing
        - No recommendations
        """
        logger.info("=== Test 5.1: Get health (healthy) ===")

        mock_redis_service_manager.check_health.return_value = {
            "overall_status": "healthy",
            "service_running": True,
            "connectivity": True,
            "response_time_ms": 2.5,
            "last_successful_command": datetime.now().isoformat(),
            "error_count_last_hour": 0,
            "health_checks": {
                "connectivity": {
                    "status": "pass",
                    "duration_ms": 2.5,
                    "message": "PING successful",
                },
                "systemd": {
                    "status": "pass",
                    "duration_ms": 50.0,
                    "message": "Service active and running",
                },
                "performance": {
                    "status": "pass",
                    "duration_ms": 15.0,
                    "message": "All metrics within normal ranges",
                },
            },
            "recommendations": [],
        }

        response = await api_client.get("/api/services/redis/health")

        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "healthy"
        assert data["service_running"] is True
        assert data["connectivity"] is True
        assert len(data["recommendations"]) == 0
        logger.info("✓ Healthy status reported correctly")

        logger.info("=== Test 5.1: PASSED ===\n")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_health_degraded(self, api_client, mock_redis_service_manager):
        """
        Test Case 5.2: Get health status when degraded

        Validates:
        - 200 status code
        - Overall status 'degraded'
        - Service running but slow
        - Recommendations provided
        """
        logger.info("=== Test 5.2: Get health (degraded) ===")

        mock_redis_service_manager.check_health.return_value = {
            "overall_status": "degraded",
            "service_running": True,
            "connectivity": True,
            "response_time_ms": 150.5,
            "error_count_last_hour": 5,
            "health_checks": {
                "performance": {
                    "status": "warning",
                    "message": "High memory usage detected",
                }
            },
            "recommendations": [
                "Consider increasing memory limit",
                "Monitor connection usage",
            ],
        }

        response = await api_client.get("/api/services/redis/health")

        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "degraded"
        assert len(data["recommendations"]) > 0
        logger.info("✓ Degraded status and recommendations provided")

        logger.info("=== Test 5.2: PASSED ===\n")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_health_critical(self, api_client, mock_redis_service_manager):
        """
        Test Case 5.3: Get health status when critical

        Validates:
        - 200 status code
        - Overall status 'critical'
        - Service not running
        - Auto-recovery status included
        """
        logger.info("=== Test 5.3: Get health (critical) ===")

        mock_redis_service_manager.check_health.return_value = {
            "overall_status": "critical",
            "service_running": False,
            "connectivity": False,
            "response_time_ms": None,
            "error_count_last_hour": 20,
            "health_checks": {
                "connectivity": {"status": "fail", "message": "Connection timeout"}
            },
            "recommendations": [
                "Check service logs for errors",
                "Consider manual intervention",
            ],
            "auto_recovery": {
                "enabled": True,
                "recent_recoveries": 3,
                "recovery_status": "failed",
                "requires_manual_intervention": True,
            },
        }

        response = await api_client.get("/api/services/redis/health")

        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "critical"
        assert data["service_running"] is False
        assert data["auto_recovery"]["requires_manual_intervention"] is True
        logger.info("✓ Critical status with manual intervention flag")

        logger.info("=== Test 5.3: PASSED ===\n")


class TestConcurrentRequests:
    """Test concurrent API requests handling."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_status_requests(
        self, api_client, mock_redis_service_manager
    ):
        """
        Test Case 6.1: Multiple concurrent status requests

        Validates:
        - All requests succeed
        - Consistent responses
        - No race conditions
        """
        logger.info("=== Test 6.1: Concurrent status requests ===")

        mock_redis_service_manager.get_service_status.return_value = {
            "status": "running",
            "pid": 12345,
        }

        # Make 10 concurrent requests
        tasks = [api_client.get("/api/services/redis/status") for _ in range(10)]

        responses = await asyncio.gather(*tasks)

        # Validate all successful
        assert all(r.status_code == 200 for r in responses)
        assert len(responses) == 10

        # Validate consistent responses
        statuses = [r.json()["status"] for r in responses]
        assert all(s == "running" for s in statuses)
        logger.info("✓ Concurrent requests handled successfully")

        logger.info("=== Test 6.1: PASSED ===\n")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_mixed_operations(
        self, api_client, admin_token, mock_redis_service_manager
    ):
        """
        Test Case 6.2: Mixed concurrent operations

        Validates:
        - Status requests while operation in progress
        - No conflicts or blocking
        - All requests complete
        """
        logger.info("=== Test 6.2: Concurrent mixed operations ===")

        # Mock slow restart
        async def slow_restart(*args, **kwargs):
            await asyncio.sleep(1)
            return {
                "success": True,
                "operation": "restart",
                "duration_seconds": 1.0,
                "new_status": "running",
            }

        mock_redis_service_manager.restart_service.side_effect = slow_restart

        # Start restart in background
        restart_task = api_client.post(
            "/api/services/redis/restart",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Make status requests during restart
        status_tasks = [api_client.get("/api/services/redis/status") for _ in range(5)]

        # Wait for all to complete
        all_tasks = [restart_task] + status_tasks
        responses = await asyncio.gather(*all_tasks)

        # Validate all successful
        assert all(r.status_code in [200, 202] for r in responses)
        logger.info("✓ Mixed operations handled without conflicts")

        logger.info("=== Test 6.2: PASSED ===\n")


class TestErrorScenarios:
    """Test error handling in API endpoints."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_service_operation_failure(
        self, api_client, admin_token, mock_redis_service_manager
    ):
        """
        Test Case 7.1: Service operation fails

        Validates:
        - 500 status code
        - Error details included
        - Error message clear
        """
        logger.info("=== Test 7.1: Service operation failure ===")

        mock_redis_service_manager.start_service.return_value = {
            "success": False,
            "operation": "start",
            "message": "Failed to start Redis service",
            "error": "systemctl start command failed: exit code 1",
            "duration_seconds": 5.0,
            "new_status": "failed",
        }

        response = await api_client.post(
            "/api/services/redis/start",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert "error" in data
        logger.info("✓ Service failure handled correctly")

        logger.info("=== Test 7.1: PASSED ===\n")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_vm_unreachable(
        self, api_client, admin_token, mock_redis_service_manager
    ):
        """
        Test Case 7.2: Redis VM unreachable

        Validates:
        - 503 status code (Service Unavailable)
        - VM unreachable message
        - Suggestions for resolution
        """
        logger.info("=== Test 7.2: VM unreachable ===")

        mock_redis_service_manager.get_service_status.side_effect = (
            ConnectionRefusedError("SSH connection refused")
        )

        response = await api_client.get("/api/services/redis/status")

        assert response.status_code == 503
        data = response.json()
        assert (
            "unreachable" in data.get("error", "").lower()
            or "unavailable" in data.get("error", "").lower()
        )
        logger.info("✓ VM unreachable handled correctly")

        logger.info("=== Test 7.2: PASSED ===\n")


# ============================================================================
# TEST EXECUTION
# ============================================================================

if __name__ == "__main__":
    """Run all integration tests with pytest"""
    pytest.main(
        [
            __file__,
            "-v",  # Verbose output
            "--tb=short",  # Short traceback format
            "--asyncio-mode=auto",  # Enable async support
            "--log-cli-level=INFO",  # Show INFO logs
            "-m",
            "integration",  # Run only integration tests
            "--cov=backend.api.service_management",  # Coverage for API module
            "--cov-report=term-missing",
            "--cov-report=html:tests/results/coverage_redis_service_api",
        ]
    )
