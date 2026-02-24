"""
Unit tests for Prometheus metrics integration.

Tests cover workflow, GitHub, and task metrics recording methods.
Target coverage: ≥90%
"""

import pytest
from monitoring.prometheus_metrics import PrometheusMetricsManager, get_metrics_manager
from prometheus_client import CollectorRegistry


class TestPrometheusMetricsManager:
    """Test suite for PrometheusMetricsManager"""

    @pytest.fixture
    def metrics_manager(self):
        """Create a fresh metrics manager with isolated registry"""
        registry = CollectorRegistry()
        return PrometheusMetricsManager(registry=registry)

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the global metrics instance before each test"""
        import autobot_shared.monitoring.prometheus_metrics as pm

        pm._metrics_instance = None
        yield
        pm._metrics_instance = None

    # ===== Initialization Tests =====

    def test_initialization(self, metrics_manager):
        """Test that all metrics are initialized"""
        assert metrics_manager.registry is not None

        # Verify timeout metrics
        assert hasattr(metrics_manager, "timeout_total")
        assert hasattr(metrics_manager, "operation_duration")
        assert hasattr(metrics_manager, "timeout_rate")

        # Verify connection metrics
        assert hasattr(metrics_manager, "pool_connections")
        assert hasattr(metrics_manager, "pool_saturation")

        # Verify circuit breaker metrics
        assert hasattr(metrics_manager, "circuit_breaker_events")
        assert hasattr(metrics_manager, "circuit_breaker_state")
        assert hasattr(metrics_manager, "circuit_breaker_failures")

        # Verify request metrics
        assert hasattr(metrics_manager, "requests_total")
        assert hasattr(metrics_manager, "success_rate")

        # Verify workflow metrics
        assert hasattr(metrics_manager, "workflow_executions_total")
        assert hasattr(metrics_manager, "workflow_duration")
        assert hasattr(metrics_manager, "workflow_steps_executed")
        assert hasattr(metrics_manager, "active_workflows")
        assert hasattr(metrics_manager, "workflow_approvals")

        # Verify GitHub metrics
        assert hasattr(metrics_manager, "github_operations_total")
        assert hasattr(metrics_manager, "github_api_duration")
        assert hasattr(metrics_manager, "github_rate_limit_remaining")
        assert hasattr(metrics_manager, "github_commits")
        assert hasattr(metrics_manager, "github_pull_requests")
        assert hasattr(metrics_manager, "github_issues")

        # Verify task metrics
        assert hasattr(metrics_manager, "tasks_executed_total")
        assert hasattr(metrics_manager, "task_duration")
        assert hasattr(metrics_manager, "active_tasks")
        assert hasattr(metrics_manager, "task_queue_size")
        assert hasattr(metrics_manager, "task_retries")

    # ===== Workflow Metrics Tests =====

    def test_record_workflow_execution_success(self, metrics_manager):
        """Test recording successful workflow execution"""
        metrics_manager.record_workflow_execution(
            workflow_type="code_review", status="success", duration=45.2
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'workflow_type="code_review"' in metrics_output
        assert 'status="success"' in metrics_output

    def test_record_workflow_execution_failed(self, metrics_manager):
        """Test recording failed workflow execution"""
        metrics_manager.record_workflow_execution(
            workflow_type="deployment", status="failed", duration=12.5
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'workflow_type="deployment"' in metrics_output
        assert 'status="failed"' in metrics_output

    def test_record_workflow_execution_without_duration(self, metrics_manager):
        """Test recording workflow execution without duration"""
        metrics_manager.record_workflow_execution(
            workflow_type="test_workflow", status="success"
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'workflow_type="test_workflow"' in metrics_output

    def test_record_workflow_step(self, metrics_manager):
        """Test recording workflow step execution"""
        metrics_manager.record_workflow_step(
            workflow_type="code_review", step_type="analysis", status="completed"
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'workflow_type="code_review"' in metrics_output
        assert 'step_type="analysis"' in metrics_output
        assert 'status="completed"' in metrics_output

    def test_update_active_workflows(self, metrics_manager):
        """Test updating active workflows count"""
        metrics_manager.update_active_workflows("code_review", 5)

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'workflow_type="code_review"' in metrics_output

    def test_record_workflow_approval(self, metrics_manager):
        """Test recording workflow approval"""
        metrics_manager.record_workflow_approval(
            workflow_type="deployment", decision="approved"
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'workflow_type="deployment"' in metrics_output
        assert 'decision="approved"' in metrics_output

    # ===== GitHub Metrics Tests =====

    def test_record_github_operation_success(self, metrics_manager):
        """Test recording successful GitHub operation"""
        metrics_manager.record_github_operation(
            operation="create_commit", status="success", duration=1.2
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'operation="create_commit"' in metrics_output
        assert 'status="success"' in metrics_output

    def test_record_github_operation_failed(self, metrics_manager):
        """Test recording failed GitHub operation"""
        metrics_manager.record_github_operation(
            operation="create_pr", status="failed", duration=0.5
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'operation="create_pr"' in metrics_output
        assert 'status="failed"' in metrics_output

    def test_record_github_operation_without_duration(self, metrics_manager):
        """Test recording GitHub operation without duration"""
        metrics_manager.record_github_operation(
            operation="list_issues", status="success"
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'operation="list_issues"' in metrics_output

    def test_update_github_rate_limit(self, metrics_manager):
        """Test updating GitHub rate limit"""
        metrics_manager.update_github_rate_limit(resource_type="core", remaining=4500)

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'resource_type="core"' in metrics_output

    def test_record_github_commit(self, metrics_manager):
        """Test recording GitHub commit"""
        metrics_manager.record_github_commit(repository="owner/repo", status="created")

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'repository="owner/repo"' in metrics_output
        assert 'status="created"' in metrics_output

    def test_record_github_pull_request(self, metrics_manager):
        """Test recording GitHub pull request"""
        metrics_manager.record_github_pull_request(
            repository="owner/repo", action="create", status="success"
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'repository="owner/repo"' in metrics_output
        assert 'action="create"' in metrics_output
        assert 'status="success"' in metrics_output

    def test_record_github_issue(self, metrics_manager):
        """Test recording GitHub issue"""
        metrics_manager.record_github_issue(
            repository="owner/repo", action="update", status="success"
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'repository="owner/repo"' in metrics_output
        assert 'action="update"' in metrics_output

    # ===== Task Metrics Tests =====

    def test_record_task_execution_success(self, metrics_manager):
        """Test recording successful task execution"""
        metrics_manager.record_task_execution(
            task_type="code_analysis",
            agent_type="code-reviewer",
            status="success",
            duration=120.5,
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'task_type="code_analysis"' in metrics_output
        assert 'agent_type="code-reviewer"' in metrics_output
        assert 'status="success"' in metrics_output

    def test_record_task_execution_failed(self, metrics_manager):
        """Test recording failed task execution"""
        metrics_manager.record_task_execution(
            task_type="deployment",
            agent_type="devops-engineer",
            status="failed",
            duration=30.2,
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'task_type="deployment"' in metrics_output
        assert 'agent_type="devops-engineer"' in metrics_output
        assert 'status="failed"' in metrics_output

    def test_record_task_execution_without_duration(self, metrics_manager):
        """Test recording task execution without duration"""
        metrics_manager.record_task_execution(
            task_type="test_task", agent_type="test-agent", status="success"
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'task_type="test_task"' in metrics_output

    def test_update_active_tasks(self, metrics_manager):
        """Test updating active tasks count"""
        metrics_manager.update_active_tasks("code_analysis", "code-reviewer", 3)

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'task_type="code_analysis"' in metrics_output
        assert 'agent_type="code-reviewer"' in metrics_output

    def test_update_task_queue_size(self, metrics_manager):
        """Test updating task queue size"""
        metrics_manager.update_task_queue_size("high", 10)
        metrics_manager.update_task_queue_size("normal", 25)
        metrics_manager.update_task_queue_size("low", 5)

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'priority="high"' in metrics_output
        assert 'priority="normal"' in metrics_output
        assert 'priority="low"' in metrics_output

    def test_record_task_retry(self, metrics_manager):
        """Test recording task retry"""
        metrics_manager.record_task_retry(task_type="code_analysis", reason="timeout")

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'task_type="code_analysis"' in metrics_output
        assert 'reason="timeout"' in metrics_output

    # ===== Legacy Metrics Tests (Redis/Performance) =====

    def test_record_timeout(self, metrics_manager):
        """Test recording timeout event"""
        metrics_manager.record_timeout(
            operation_type="redis_get", database="main", timed_out=True
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'operation_type="redis_get"' in metrics_output
        assert 'database="main"' in metrics_output
        assert 'status="timeout"' in metrics_output

    def test_record_operation_duration(self, metrics_manager):
        """Test recording operation duration"""
        metrics_manager.record_operation_duration(
            operation_type="redis_get", database="main", duration=0.015
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'operation_type="redis_get"' in metrics_output
        assert 'database="main"' in metrics_output

    def test_record_circuit_breaker_event(self, metrics_manager):
        """Test recording circuit breaker event"""
        metrics_manager.record_circuit_breaker_event(
            database="main", event="opened", reason="too_many_failures"
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'database="main"' in metrics_output
        assert 'event="opened"' in metrics_output
        assert 'reason="too_many_failures"' in metrics_output

    def test_update_circuit_breaker_state(self, metrics_manager):
        """Test updating circuit breaker state"""
        metrics_manager.update_circuit_breaker_state(
            database="main", state="open", failure_count=5
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'database="main"' in metrics_output

    def test_update_connection_pool(self, metrics_manager):
        """Test updating connection pool metrics"""
        metrics_manager.update_connection_pool(
            database="main", active=10, idle=5, max_connections=20
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'database="main"' in metrics_output
        assert 'state="active"' in metrics_output
        assert 'state="idle"' in metrics_output
        assert 'state="total"' in metrics_output

    def test_record_request_success(self, metrics_manager):
        """Test recording successful request"""
        metrics_manager.record_request(database="main", operation="get", success=True)

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'database="main"' in metrics_output
        assert 'operation="get"' in metrics_output
        assert 'status="success"' in metrics_output

    def test_record_request_failure(self, metrics_manager):
        """Test recording failed request"""
        metrics_manager.record_request(database="main", operation="set", success=False)

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'status="failure"' in metrics_output

    # ===== Integration Tests =====

    def test_get_metrics_format(self, metrics_manager):
        """Test that get_metrics returns Prometheus text format"""
        metrics_manager.record_workflow_execution(
            "test_workflow", "success", duration=10.0
        )
        metrics_manager.record_github_commit("owner/repo", "created")
        metrics_manager.record_task_execution(
            "test_task", "test-agent", "success", duration=5.0
        )

        metrics_data = metrics_manager.get_metrics()

        # Verify it's bytes
        assert isinstance(metrics_data, bytes)

        # Verify Prometheus format
        metrics_str = metrics_data.decode("utf-8")
        assert "# HELP" in metrics_str
        assert "# TYPE" in metrics_str

        # Verify our metrics are present
        assert "autobot_workflow_executions_total" in metrics_str
        assert "autobot_github_commits_total" in metrics_str
        assert "autobot_tasks_executed_total" in metrics_str

    def test_multiple_recordings(self, metrics_manager):
        """Test recording multiple metrics of same type"""
        # Record multiple workflow executions
        for i in range(5):
            metrics_manager.record_workflow_execution(
                "code_review", "success", 10.0 + i
            )

        for i in range(3):
            metrics_manager.record_workflow_execution("code_review", "failed", 5.0 + i)

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'workflow_type="code_review"' in metrics_output

    def test_get_metrics_manager_singleton(self):
        """Test that get_metrics_manager returns singleton"""
        manager1 = get_metrics_manager()
        manager2 = get_metrics_manager()

        assert manager1 is manager2

    def test_custom_registry(self):
        """Test creating manager with custom registry"""
        custom_registry = CollectorRegistry()
        manager = PrometheusMetricsManager(registry=custom_registry)

        assert manager.registry is custom_registry

    # ===== Edge Cases =====

    def test_workflow_execution_zero_duration(self, metrics_manager):
        """Test recording workflow with zero duration"""
        metrics_manager.record_workflow_execution(
            "fast_workflow", "success", duration=0.0
        )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'workflow_type="fast_workflow"' in metrics_output

    def test_github_rate_limit_zero(self, metrics_manager):
        """Test updating GitHub rate limit to zero"""
        metrics_manager.update_github_rate_limit("core", 0)

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'resource_type="core"' in metrics_output

    def test_task_queue_empty(self, metrics_manager):
        """Test recording empty task queue"""
        metrics_manager.update_task_queue_size("high", 0)

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'priority="high"' in metrics_output

    def test_active_workflows_zero(self, metrics_manager):
        """Test setting active workflows to zero"""
        metrics_manager.update_active_workflows("code_review", 0)

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        assert 'workflow_type="code_review"' in metrics_output

    # ===== Label Validation Tests =====

    def test_workflow_labels_bounded(self, metrics_manager):
        """Test that workflow labels use bounded value sets"""
        valid_types = [
            "code_review",
            "deployment",
            "testing",
            "analysis",
            "refactoring",
        ]
        valid_statuses = ["success", "failed", "timeout", "cancelled"]

        for wf_type in valid_types:
            for status in valid_statuses:
                metrics_manager.record_workflow_execution(
                    wf_type, status, duration=10.0
                )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        for wf_type in valid_types:
            assert f'workflow_type="{wf_type}"' in metrics_output

    def test_task_labels_bounded(self, metrics_manager):
        """Test that task labels use bounded value sets"""
        valid_agents = [
            "code-reviewer",
            "testing-engineer",
            "devops-engineer",
            "frontend-engineer",
            "senior-backend-engineer",
        ]

        for agent in valid_agents:
            metrics_manager.record_task_execution(
                "code_analysis", agent, "success", duration=60.0
            )

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        for agent in valid_agents:
            assert f'agent_type="{agent}"' in metrics_output

    def test_github_operation_types(self, metrics_manager):
        """Test various GitHub operation types"""
        operations = [
            "create_commit",
            "create_pr",
            "merge_pr",
            "create_issue",
            "update_issue",
            "list_commits",
        ]

        for op in operations:
            metrics_manager.record_github_operation(op, "success", duration=1.0)

        metrics_output = metrics_manager.get_metrics().decode("utf-8")
        for op in operations:
            assert f'operation="{op}"' in metrics_output


# ===== Performance Tests =====


class TestPrometheusMetricsPerformance:
    """Performance tests for metrics recording"""

    @pytest.fixture
    def metrics_manager(self):
        """Create metrics manager"""
        registry = CollectorRegistry()
        return PrometheusMetricsManager(registry=registry)

    @pytest.mark.skip(
        reason="Requires pytest-benchmark plugin (optional performance test)"
    )
    def test_batch_recording_performance(self, metrics_manager, benchmark):
        """Test performance of recording metrics in batch"""

        def record_batch():
            for i in range(100):
                metrics_manager.record_workflow_execution(
                    "code_review", "success", 10.0
                )
                metrics_manager.record_github_commit("owner/repo", "created")
                metrics_manager.record_task_execution(
                    "code_analysis", "code-reviewer", "success", 60.0
                )

        # Should complete in reasonable time (benchmark handles timing)
        benchmark(record_batch)

    @pytest.mark.skip(
        reason="Requires pytest-benchmark plugin (optional performance test)"
    )
    def test_get_metrics_performance(self, metrics_manager, benchmark):
        """Test performance of get_metrics call"""
        # Pre-populate with data
        for i in range(100):
            metrics_manager.record_workflow_execution("code_review", "success", 10.0)

        def get_metrics():
            return metrics_manager.get_metrics()

        benchmark(get_metrics)


# ===== Integration with Monitoring API =====


class TestPrometheusMetricsIntegration:
    """Integration tests with monitoring API"""

    def test_metrics_endpoint_accessibility(self):
        """Test that metrics can be accessed via API"""
        manager = get_metrics_manager()
        manager.record_workflow_execution("test", "success", 1.0)

        metrics_data = manager.get_metrics()
        assert len(metrics_data) > 0
        assert b"autobot" in metrics_data

    def test_prometheus_text_format_compliance(self):
        """Test that output complies with Prometheus text format"""
        manager = get_metrics_manager()
        manager.record_workflow_execution("test", "success", 1.0)

        metrics_data = manager.get_metrics().decode("utf-8")
        lines = metrics_data.split("\n")

        # Should have HELP and TYPE comments
        has_help = any(line.startswith("# HELP") for line in lines)
        has_type = any(line.startswith("# TYPE") for line in lines)

        assert has_help, "Missing HELP comments"
        assert has_type, "Missing TYPE comments"

        # Should have metric data
        has_data = any(
            line and not line.startswith("#") and "autobot" in line for line in lines
        )
        assert has_data, "Missing metric data"
