"""
Integration tests for complete AutoBot system workflows
Tests how different system components work together end-to-end
"""

# Import system components
from app_factory import create_app
from fastapi.testclient import TestClient


class TestAutoBootSystemIntegration:
    """Test complete AutoBot system integration"""

    def setup_method(self):
        """Set up test fixtures"""
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_system_health_check(self):
        """Test system health and basic API availability"""
        # Test basic API endpoints are available
        endpoints_to_test = [
            "/api/hello",
            "/api/version",
            "/api/system/health",
            "/api/security/status",
        ]

        for endpoint in endpoints_to_test:
            response = self.client.get(endpoint)
            # Should either work (200) or be found but have issues (4xx/5xx)
            # 404 would indicate routing problem
            assert (
                response.status_code != 404
            ), f"Endpoint {endpoint} not found (routing issue)"

    def test_system_component_initialization(self):
        """Test that core system components are initialized"""
        # Check app state has core components
        # Note: Some may not be initialized until lifespan events

        expected_components = [
            "enhanced_security_layer",  # Should always be present
        ]

        for component in expected_components:
            # Use getattr to check if component exists
            component_exists = hasattr(self.app.state, component)
            if not component_exists:
                # Try to trigger initialization by calling an endpoint
                self.client.get("/api/security/status")
                component_exists = hasattr(self.app.state, component)

            assert component_exists, f"Component {component} not initialized"

    def test_api_error_handling_consistency(self):
        """Test consistent error handling across API endpoints"""
        # Test various endpoints with invalid requests
        error_tests = [
            ("GET", "/api/security/nonexistent", 404),
            ("POST", "/api/security/approve-command", 422),  # Missing body
            (
                "GET",
                "/api/security/command-history?limit=invalid",
                422,
            ),  # Invalid param
        ]

        for method, endpoint, expected_status in error_tests:
            if method == "GET":
                response = self.client.get(endpoint)
            elif method == "POST":
                response = self.client.post(endpoint)

            assert response.status_code == expected_status

            # Check error response format
            if response.status_code >= 400:
                data = response.json()
                assert "detail" in data  # FastAPI standard error format


class TestWorkflowIntegration:
    """Test multi-component workflow integration"""

    def setup_method(self):
        """Set up test fixtures"""
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_security_workflow_integration(self):
        """Test security workflow across multiple endpoints"""
        # 1. Get initial security status
        status_response = self.client.get("/api/security/status")
        assert status_response.status_code == 200
        status_data = status_response.json()

        # 2. Check command history (should be empty initially)
        history_response = self.client.get("/api/security/command-history")
        assert history_response.status_code == 200
        history_data = history_response.json()

        # 3. Check pending approvals
        pending_response = self.client.get("/api/security/pending-approvals")
        assert pending_response.status_code == 200
        pending_data = pending_response.json()

        # All should be consistent with system state
        assert isinstance(status_data["command_security_enabled"], bool)
        assert isinstance(history_data["count"], int)
        assert isinstance(pending_data["count"], int)

    def test_agent_security_integration(self):
        """Test integration between agent endpoints and security"""
        # Test that agent endpoints respect security configuration

        # Try to get agent status (if available)
        agent_response = self.client.get("/api/agent")

        # Should either work or give structured error
        if agent_response.status_code == 404:
            # Endpoint might not exist, that's ok
            pass
        else:
            # If it exists, should give proper response
            assert agent_response.status_code in [200, 405, 422, 500]

    def test_terminal_security_integration(self):
        """Test terminal and security integration"""
        # Test terminal endpoints are available
        terminal_endpoints = [
            "/api/terminal/sessions",
        ]

        for endpoint in terminal_endpoints:
            response = self.client.get(endpoint)
            # Should not be 404 (routing issue)
            assert response.status_code != 404


class TestDataFlowIntegration:
    """Test data flow between different system components"""

    def setup_method(self):
        """Set up test fixtures"""
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_audit_data_flow(self):
        """Test audit data flow through security system"""
        # Get initial audit log state
        audit_response = self.client.get("/api/security/audit-log")
        assert audit_response.status_code == 200
        initial_data = audit_response.json()

        initial_count = initial_data.get("count", 0)

        # Trigger some activity that should create audit entries
        # (Just accessing security endpoints should create some audit entries)
        self.client.get("/api/security/status")
        self.client.get("/api/security/pending-approvals")

        # Check if audit log has grown
        audit_response = self.client.get("/api/security/audit-log")
        assert audit_response.status_code == 200
        final_data = audit_response.json()

        # Should have same or more entries (system might log access)
        final_count = final_data.get("count", 0)
        assert final_count >= initial_count

    def test_security_status_consistency(self):
        """Test security status consistency across calls"""
        # Call security status multiple times
        responses = []
        for i in range(3):
            response = self.client.get("/api/security/status")
            assert response.status_code == 200
            responses.append(response.json())

        # All responses should be consistent
        for i in range(1, len(responses)):
            # Key settings should be the same
            assert responses[i]["security_enabled"] == responses[0]["security_enabled"]
            assert (
                responses[i]["command_security_enabled"]
                == responses[0]["command_security_enabled"]
            )
            assert (
                responses[i]["docker_sandbox_enabled"]
                == responses[0]["docker_sandbox_enabled"]
            )


class TestSystemResilience:
    """Test system resilience and error recovery"""

    def setup_method(self):
        """Set up test fixtures"""
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_system_graceful_degradation(self):
        """Test system graceful degradation when components fail"""
        # Test that API endpoints still respond even if some components fail

        # Try to break the security layer and see if system still responds
        if hasattr(self.app.state, "enhanced_security_layer"):
            # Temporarily break audit logging
            original_audit_file = self.app.state.enhanced_security_layer.audit_log_file
            self.app.state.enhanced_security_layer.audit_log_file = (
                "/invalid/path/audit.log"
            )

            # System should still respond
            response = self.client.get("/api/security/status")
            assert response.status_code == 200

            # Restore original path
            self.app.state.enhanced_security_layer.audit_log_file = original_audit_file

    def test_concurrent_request_handling(self):
        """Test system handles concurrent requests properly"""
        import threading

        results = []
        errors = []

        def make_request():
            try:
                response = self.client.get("/api/security/status")
                results.append(response.status_code)
            except Exception as e:
                errors.append(str(e))

        # Create multiple threads making concurrent requests
        threads = []
        for i in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=10)

        # All requests should have succeeded
        assert len(errors) == 0, f"Errors in concurrent requests: {errors}"
        assert len(results) == 5, "Not all requests completed"
        assert all(status == 200 for status in results), f"Non-200 responses: {results}"

    def test_large_request_handling(self):
        """Test system handles large requests appropriately"""
        # Test command history with large limit
        response = self.client.get("/api/security/command-history?limit=1000")
        assert response.status_code == 200

        data = response.json()
        assert "count" in data
        assert data["count"] >= 0

        # Should not crash or hang
        assert len(str(data)) > 0


class TestSystemPerformance:
    """Test system performance characteristics"""

    def setup_method(self):
        """Set up test fixtures"""
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_api_response_times(self):
        """Test API response times are reasonable"""
        import time

        endpoints = [
            "/api/security/status",
            "/api/security/pending-approvals",
            "/api/security/command-history",
            "/api/security/audit-log",
        ]

        for endpoint in endpoints:
            start_time = time.time()
            response = self.client.get(endpoint)
            end_time = time.time()

            duration = end_time - start_time

            # API calls should be fast (under 1 second)
            assert duration < 1.0, f"Endpoint {endpoint} took {duration:.2f}s"
            assert (
                response.status_code == 200
            ), f"Endpoint {endpoint} failed with {response.status_code}"

    def test_memory_usage_stability(self):
        """Test memory usage doesn't grow excessively"""
        import gc
        import os

        import psutil

        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Make many API calls
        for i in range(100):
            response = self.client.get("/api/security/status")
            assert response.status_code == 200

        # Force garbage collection
        gc.collect()

        # Check final memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory

        # Memory growth should be reasonable (less than 50MB for 100 calls)
        assert memory_growth < 50, f"Memory grew by {memory_growth:.1f}MB"


class TestSystemCompatibility:
    """Test system compatibility and standards compliance"""

    def setup_method(self):
        """Set up test fixtures"""
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_http_standards_compliance(self):
        """Test HTTP standards compliance"""
        # Test CORS headers
        response = self.client.options("/api/security/status")
        # Should handle OPTIONS request properly
        assert response.status_code in [200, 204, 405]

        # Test proper HTTP methods
        # GET should work
        get_response = self.client.get("/api/security/status")
        assert get_response.status_code == 200

        # POST should not work on GET endpoints
        post_response = self.client.post("/api/security/status")
        assert post_response.status_code == 405  # Method Not Allowed

    def test_json_response_format(self):
        """Test JSON response format consistency"""
        endpoints = [
            "/api/security/status",
            "/api/security/pending-approvals",
            "/api/security/command-history",
            "/api/security/audit-log",
        ]

        for endpoint in endpoints:
            response = self.client.get(endpoint)
            assert response.status_code == 200

            # Should be valid JSON
            data = response.json()
            assert isinstance(data, dict)

            # Should have consistent structure
            if "success" in data:
                assert isinstance(data["success"], bool)
            if "count" in data:
                assert isinstance(data["count"], int)

    def test_api_versioning_readiness(self):
        """Test API is ready for versioning"""
        # All API endpoints should be under /api/ prefix
        response = self.client.get("/api/version")

        if response.status_code == 200:
            data = response.json()
            assert "version_no" in data or "version" in data

        # Security endpoints should be properly namespaced
        response = self.client.get("/api/security/status")
        assert response.status_code == 200


# Helper function to run all integration tests
def run_integration_tests():
    """Run all integration tests with proper reporting"""
    import subprocess
    import sys

    print("🔄 Running AutoBot System Integration Tests")  # noqa: print
    print("=" * 60)  # noqa: print

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                __file__,
                "-v",
                "--tb=short",
                "-x",  # Stop on first failure
            ],
            timeout=120,
        )

        if result.returncode == 0:
            print("✅ All integration tests passed!")  # noqa: print
        else:
            print("❌ Some integration tests failed.")  # noqa: print

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print("⏰ Integration tests timed out")  # noqa: print
        return False
    except Exception as e:
        print(f"❌ Error running integration tests: {e}")  # noqa: print
        return False


if __name__ == "__main__":
    success = run_integration_tests()
    exit(0 if success else 1)
