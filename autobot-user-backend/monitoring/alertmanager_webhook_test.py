# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for AlertManager Webhook Integration.

Tests cover:
- Webhook payload parsing and validation
- Alert processing and WebSocket broadcast
- Circuit breaker alert handling (Issue #69)
- Redis/NPU component alert handling
- Health check endpoint

Target coverage: ≥90%
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestAlertManagerWebhook:
    """Test suite for AlertManager webhook endpoint"""

    @pytest.fixture
    def sample_circuit_breaker_alert(self):
        """Sample circuit breaker OPEN alert payload"""
        return {
            "version": "4",
            "groupKey": '{}:{alertname="CircuitBreakerOpen"}',
            "truncatedAlerts": 0,
            "status": "firing",
            "receiver": "circuit-breaker-alerts",
            "groupLabels": {"alertname": "CircuitBreakerOpen", "severity": "critical"},
            "commonLabels": {
                "alertname": "CircuitBreakerOpen",
                "severity": "critical",
                "component": "circuit_breaker",
                "database": "redis_main",
            },
            "commonAnnotations": {
                "summary": "Circuit Breaker OPEN: redis_main",
                "description": "Circuit breaker for redis_main has opened with 5 failures",
                "recommendation": "Check redis_main service health, logs, and connectivity",
            },
            "externalURL": "http://localhost:9093",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "CircuitBreakerOpen",
                        "severity": "critical",
                        "component": "circuit_breaker",
                        "database": "redis_main",
                    },
                    "annotations": {
                        "summary": "Circuit Breaker OPEN: redis_main",
                        "description": "Circuit breaker for redis_main has opened with 5 failures",
                        "recommendation": "Check redis_main service health, logs, and connectivity",
                    },
                    "startsAt": "2025-01-01T12:00:00.000Z",
                    "endsAt": None,
                    "generatorURL": "http://localhost:9090/graph",
                    "fingerprint": "abc123def456",
                }
            ],
        }

    @pytest.fixture
    def sample_redis_alert(self):
        """Sample Redis server down alert payload"""
        return {
            "version": "4",
            "groupKey": '{}:{alertname="RedisServerDown"}',
            "truncatedAlerts": 0,
            "status": "firing",
            "receiver": "redis-alerts",
            "groupLabels": {"alertname": "RedisServerDown", "severity": "critical"},
            "commonLabels": {
                "alertname": "RedisServerDown",
                "severity": "critical",
                "component": "redis",
                "service": "redis",
                "database": "main",
            },
            "commonAnnotations": {
                "summary": "Redis Server Down: main",
                "description": "Redis server main is unavailable",
                "recommendation": "Check Redis service on VM3 (172.16.168.23:6379)",
            },
            "externalURL": "http://localhost:9093",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "RedisServerDown",
                        "severity": "critical",
                        "component": "redis",
                        "service": "redis",
                        "database": "main",
                    },
                    "annotations": {
                        "summary": "Redis Server Down: main",
                        "description": "Redis server main is unavailable",
                        "recommendation": "Check Redis service on VM3 (172.16.168.23:6379)",
                    },
                    "startsAt": "2025-01-01T12:00:00.000Z",
                    "endsAt": None,
                    "generatorURL": "http://localhost:9090/graph",
                    "fingerprint": "redis123",
                }
            ],
        }

    @pytest.fixture
    def sample_npu_alert(self):
        """Sample NPU circuit breaker alert payload"""
        return {
            "version": "4",
            "groupKey": '{}:{alertname="NPUCircuitBreakerOpen"}',
            "truncatedAlerts": 0,
            "status": "firing",
            "receiver": "npu-alerts",
            "groupLabels": {
                "alertname": "NPUCircuitBreakerOpen",
                "severity": "critical",
            },
            "commonLabels": {
                "alertname": "NPUCircuitBreakerOpen",
                "severity": "critical",
                "component": "npu",
                "service": "npu_worker",
            },
            "commonAnnotations": {
                "summary": "NPU Circuit Breaker OPEN",
                "description": "NPU worker circuit breaker opened - hardware acceleration unavailable",
                "recommendation": "Check NPU Worker VM2 (172.16.168.22:8081) and OpenVINO status",
            },
            "externalURL": "http://localhost:9093",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "NPUCircuitBreakerOpen",
                        "severity": "critical",
                        "component": "npu",
                        "service": "npu_worker",
                    },
                    "annotations": {
                        "summary": "NPU Circuit Breaker OPEN",
                        "description": "NPU worker circuit breaker opened - hardware acceleration unavailable",
                        "recommendation": "Check NPU Worker VM2 (172.16.168.22:8081) and OpenVINO status",
                    },
                    "startsAt": "2025-01-01T12:00:00.000Z",
                    "endsAt": None,
                    "generatorURL": "http://localhost:9090/graph",
                    "fingerprint": "npu123",
                }
            ],
        }

    @pytest.fixture
    def sample_resolved_alert(self):
        """Sample resolved alert payload"""
        return {
            "version": "4",
            "groupKey": '{}:{alertname="CircuitBreakerOpen"}',
            "truncatedAlerts": 0,
            "status": "resolved",
            "receiver": "circuit-breaker-alerts",
            "groupLabels": {"alertname": "CircuitBreakerOpen", "severity": "critical"},
            "commonLabels": {
                "alertname": "CircuitBreakerOpen",
                "severity": "critical",
                "component": "circuit_breaker",
                "database": "redis_main",
            },
            "commonAnnotations": {
                "summary": "Circuit Breaker OPEN: redis_main",
                "description": "Circuit breaker for redis_main has opened",
            },
            "externalURL": "http://localhost:9093",
            "alerts": [
                {
                    "status": "resolved",
                    "labels": {
                        "alertname": "CircuitBreakerOpen",
                        "severity": "critical",
                        "component": "circuit_breaker",
                        "database": "redis_main",
                    },
                    "annotations": {
                        "summary": "Circuit Breaker OPEN: redis_main",
                        "description": "Circuit breaker for redis_main has opened",
                    },
                    "startsAt": "2025-01-01T12:00:00.000Z",
                    "endsAt": "2025-01-01T12:05:00.000Z",
                    "generatorURL": "http://localhost:9090/graph",
                    "fingerprint": "abc123def456",
                }
            ],
        }

    @pytest.fixture
    def sample_security_alert(self):
        """Sample security violation alert payload"""
        return {
            "version": "4",
            "groupKey": '{}:{alertname="SecurityViolation"}',
            "truncatedAlerts": 0,
            "status": "firing",
            "receiver": "security-alerts",
            "groupLabels": {"alertname": "SecurityViolation", "severity": "critical"},
            "commonLabels": {
                "alertname": "SecurityViolation",
                "severity": "critical",
                "component": "security",
            },
            "commonAnnotations": {
                "summary": "Security Violation Detected",
                "description": "Security errors detected in api: 5 events",
                "recommendation": "Investigate security logs immediately",
            },
            "externalURL": "http://localhost:9093",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "SecurityViolation",
                        "severity": "critical",
                        "component": "security",
                    },
                    "annotations": {
                        "summary": "Security Violation Detected",
                        "description": "Security errors detected in api: 5 events",
                        "recommendation": "Investigate security logs immediately",
                    },
                    "startsAt": "2025-01-01T12:00:00.000Z",
                    "endsAt": None,
                    "generatorURL": "http://localhost:9090/graph",
                    "fingerprint": "security123",
                }
            ],
        }

    # ===== Pydantic Model Tests =====

    def test_alert_instance_model_validation(self):
        """Test AlertInstance Pydantic model validation"""
        from api.alertmanager_webhook import AlertInstance

        alert = AlertInstance(
            status="firing",
            labels={"alertname": "TestAlert", "severity": "high"},
            annotations={"summary": "Test", "description": "Test description"},
            startsAt="2025-01-01T12:00:00.000Z",
            endsAt=None,
            generatorURL="http://localhost:9090",
            fingerprint="test123",
        )

        assert alert.status == "firing"
        assert alert.labels["alertname"] == "TestAlert"
        assert alert.fingerprint == "test123"

    def test_alertmanager_webhook_model_validation(self):
        """Test AlertManagerWebhook Pydantic model validation"""
        from api.alertmanager_webhook import AlertInstance, AlertManagerWebhook

        alert = AlertInstance(
            status="firing",
            labels={"alertname": "TestAlert"},
            annotations={"summary": "Test"},
            startsAt="2025-01-01T12:00:00.000Z",
            generatorURL="http://localhost:9090",
            fingerprint="test123",
        )

        webhook = AlertManagerWebhook(
            version="4",
            groupKey="test",
            status="firing",
            receiver="default",
            groupLabels={"alertname": "TestAlert"},
            commonLabels={"alertname": "TestAlert"},
            commonAnnotations={"summary": "Test"},
            externalURL="http://localhost:9093",
            alerts=[alert],
        )

        assert webhook.version == "4"
        assert webhook.status == "firing"
        assert len(webhook.alerts) == 1

    # ===== Alert Processing Tests =====

    @pytest.mark.asyncio
    async def test_process_circuit_breaker_alert(self, sample_circuit_breaker_alert):
        """Test processing circuit breaker OPEN alert"""
        from api.alertmanager_webhook import AlertInstance, _process_alert

        with patch("backend.api.alertmanager_webhook.ws_manager") as mock_ws:
            mock_ws.broadcast_update = AsyncMock()

            alert_data = sample_circuit_breaker_alert["alerts"][0]
            alert = AlertInstance(**alert_data)

            await _process_alert(alert, "firing")

            # Verify broadcast was called
            mock_ws.broadcast_update.assert_called_once()

            # Verify alert data structure
            call_args = mock_ws.broadcast_update.call_args[0][0]
            assert call_args["type"] == "system_alert"
            assert call_args["data"]["rule_name"] == "CircuitBreakerOpen"
            assert call_args["data"]["severity"] == "critical"
            assert call_args["data"]["component"] == "circuit_breaker"
            assert "recommendation" in call_args["data"]

    @pytest.mark.asyncio
    async def test_process_redis_alert(self, sample_redis_alert):
        """Test processing Redis server down alert"""
        from api.alertmanager_webhook import AlertInstance, _process_alert

        with patch("backend.api.alertmanager_webhook.ws_manager") as mock_ws:
            mock_ws.broadcast_update = AsyncMock()

            alert_data = sample_redis_alert["alerts"][0]
            alert = AlertInstance(**alert_data)

            await _process_alert(alert, "firing")

            call_args = mock_ws.broadcast_update.call_args[0][0]
            assert call_args["data"]["rule_name"] == "RedisServerDown"
            assert call_args["data"]["component"] == "redis"
            assert call_args["data"]["service"] == "redis"

    @pytest.mark.asyncio
    async def test_process_npu_alert(self, sample_npu_alert):
        """Test processing NPU circuit breaker alert"""
        from api.alertmanager_webhook import AlertInstance, _process_alert

        with patch("backend.api.alertmanager_webhook.ws_manager") as mock_ws:
            mock_ws.broadcast_update = AsyncMock()

            alert_data = sample_npu_alert["alerts"][0]
            alert = AlertInstance(**alert_data)

            await _process_alert(alert, "firing")

            call_args = mock_ws.broadcast_update.call_args[0][0]
            assert call_args["data"]["rule_name"] == "NPUCircuitBreakerOpen"
            assert call_args["data"]["component"] == "npu"
            assert call_args["data"]["service"] == "npu_worker"

    @pytest.mark.asyncio
    async def test_process_security_alert(self, sample_security_alert):
        """Test processing security violation alert"""
        from api.alertmanager_webhook import AlertInstance, _process_alert

        with patch("backend.api.alertmanager_webhook.ws_manager") as mock_ws:
            mock_ws.broadcast_update = AsyncMock()

            alert_data = sample_security_alert["alerts"][0]
            alert = AlertInstance(**alert_data)

            await _process_alert(alert, "firing")

            call_args = mock_ws.broadcast_update.call_args[0][0]
            assert call_args["data"]["rule_name"] == "SecurityViolation"
            assert call_args["data"]["component"] == "security"
            assert call_args["data"]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_process_resolved_alert(self, sample_resolved_alert):
        """Test processing resolved alert"""
        from api.alertmanager_webhook import AlertInstance, _process_alert

        with patch("backend.api.alertmanager_webhook.ws_manager") as mock_ws:
            mock_ws.broadcast_update = AsyncMock()

            alert_data = sample_resolved_alert["alerts"][0]
            alert = AlertInstance(**alert_data)

            await _process_alert(alert, "resolved")

            call_args = mock_ws.broadcast_update.call_args[0][0]
            assert call_args["type"] == "alert_recovery"
            assert call_args["data"]["status"] == "resolved"
            assert call_args["data"]["ends_at"] == "2025-01-01T12:05:00.000Z"

    @pytest.mark.asyncio
    async def test_process_alert_with_missing_optional_fields(self):
        """Test processing alert with minimal fields"""
        from api.alertmanager_webhook import AlertInstance, _process_alert

        with patch("backend.api.alertmanager_webhook.ws_manager") as mock_ws:
            mock_ws.broadcast_update = AsyncMock()

            alert = AlertInstance(
                status="firing",
                labels={"alertname": "MinimalAlert"},
                annotations={"summary": "Minimal"},
                startsAt="2025-01-01T12:00:00.000Z",
                generatorURL="http://localhost:9090",
                fingerprint="minimal123",
            )

            await _process_alert(alert, "firing")

            call_args = mock_ws.broadcast_update.call_args[0][0]
            assert call_args["data"]["rule_name"] == "MinimalAlert"
            assert call_args["data"]["severity"] == "unknown"
            assert call_args["data"]["component"] == "unknown"

    @pytest.mark.asyncio
    async def test_process_alert_handles_broadcast_error(self):
        """Test that alert processing handles WebSocket errors gracefully"""
        from api.alertmanager_webhook import AlertInstance, _process_alert

        with patch("backend.api.alertmanager_webhook.ws_manager") as mock_ws:
            mock_ws.broadcast_update = AsyncMock(side_effect=Exception("WS Error"))

            alert = AlertInstance(
                status="firing",
                labels={"alertname": "TestAlert"},
                annotations={"summary": "Test"},
                startsAt="2025-01-01T12:00:00.000Z",
                generatorURL="http://localhost:9090",
                fingerprint="test123",
            )

            # Should not raise - errors are logged but not propagated
            await _process_alert(alert, "firing")

    # ===== Alert Severity Tests =====

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "severity,expected_type",
        [
            ("critical", "system_alert"),
            ("high", "system_alert"),
            ("medium", "system_alert"),
            ("warning", "system_alert"),
            ("low", "system_alert"),
        ],
    )
    async def test_alert_severity_levels(self, severity, expected_type):
        """Test different severity levels are handled correctly"""
        from api.alertmanager_webhook import AlertInstance, _process_alert

        with patch("backend.api.alertmanager_webhook.ws_manager") as mock_ws:
            mock_ws.broadcast_update = AsyncMock()

            alert = AlertInstance(
                status="firing",
                labels={"alertname": "TestAlert", "severity": severity},
                annotations={"summary": "Test"},
                startsAt="2025-01-01T12:00:00.000Z",
                generatorURL="http://localhost:9090",
                fingerprint="test123",
            )

            await _process_alert(alert, "firing")

            call_args = mock_ws.broadcast_update.call_args[0][0]
            assert call_args["type"] == expected_type
            assert call_args["data"]["severity"] == severity

    # ===== Tag Generation Tests =====

    @pytest.mark.asyncio
    async def test_alert_tags_generation(self):
        """Test that alert tags are correctly generated from labels"""
        from api.alertmanager_webhook import AlertInstance, _process_alert

        with patch("backend.api.alertmanager_webhook.ws_manager") as mock_ws:
            mock_ws.broadcast_update = AsyncMock()

            alert = AlertInstance(
                status="firing",
                labels={
                    "alertname": "TestAlert",
                    "severity": "high",
                    "component": "redis",
                    "resource": "memory",
                },
                annotations={"summary": "Test"},
                startsAt="2025-01-01T12:00:00.000Z",
                generatorURL="http://localhost:9090",
                fingerprint="test123",
            )

            await _process_alert(alert, "firing")

            call_args = mock_ws.broadcast_update.call_args[0][0]
            tags = call_args["data"]["tags"]
            assert "high" in tags
            assert "redis" in tags
            assert "memory" in tags

    # ===== Multiple Alerts Tests =====

    @pytest.mark.asyncio
    async def test_process_multiple_alerts_in_batch(self, sample_circuit_breaker_alert):
        """Test processing multiple alerts in a single webhook call"""
        from api.alertmanager_webhook import AlertManagerWebhook, _process_alert

        with patch("backend.api.alertmanager_webhook.ws_manager") as mock_ws:
            mock_ws.broadcast_update = AsyncMock()

            # Add second alert to payload
            sample_circuit_breaker_alert["alerts"].append(
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "CircuitBreakerHighFailures",
                        "severity": "warning",
                        "component": "circuit_breaker",
                        "database": "redis_knowledge",
                    },
                    "annotations": {
                        "summary": "Circuit Breaker High Failures: redis_knowledge",
                        "description": "redis_knowledge has 3 failures",
                    },
                    "startsAt": "2025-01-01T12:01:00.000Z",
                    "endsAt": None,
                    "generatorURL": "http://localhost:9090/graph",
                    "fingerprint": "xyz789",
                }
            )

            webhook = AlertManagerWebhook(**sample_circuit_breaker_alert)

            from api.alertmanager_webhook import AlertInstance

            for alert_data in sample_circuit_breaker_alert["alerts"]:
                alert = AlertInstance(**alert_data)
                await _process_alert(alert, webhook.status)

            # Verify both alerts were broadcast
            assert mock_ws.broadcast_update.call_count == 2


class TestAlertManagerHealth:
    """Test suite for AlertManager webhook health endpoint"""

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy(self):
        """Test health check returns healthy status"""
        from api.alertmanager_webhook import alertmanager_webhook_health

        with patch("backend.api.alertmanager_webhook.ws_manager") as mock_ws:
            mock_ws.__bool__ = lambda self: True

            result = await alertmanager_webhook_health()

            assert result["status"] == "healthy"
            assert result["endpoint"] == "/api/webhook/alertmanager"
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_health_check_with_unavailable_ws(self):
        """Test health check when WebSocket manager is unavailable"""
        from api.alertmanager_webhook import alertmanager_webhook_health

        with patch("backend.api.alertmanager_webhook.ws_manager", None):
            result = await alertmanager_webhook_health()

            assert result["status"] == "healthy"
            assert result["websocket_manager"] == "unavailable"


class TestAlertRulesYaml:
    """Test suite for AlertManager rules YAML configuration"""

    @pytest.fixture
    def alert_rules_content(self):
        """Load alert rules YAML content"""
        import yaml

        with open(
            "/home/kali/Desktop/AutoBot/config/prometheus/alertmanager_rules.yml", "r"
        ) as f:
            return yaml.safe_load(f)

    def test_circuit_breaker_rules_exist(self, alert_rules_content):
        """Verify circuit breaker alert rules are defined"""
        groups = {g["name"]: g for g in alert_rules_content["groups"]}

        assert "autobot_circuit_breaker" in groups
        cb_rules = {r["alert"]: r for r in groups["autobot_circuit_breaker"]["rules"]}

        assert "CircuitBreakerOpen" in cb_rules
        assert "CircuitBreakerHalfOpen" in cb_rules
        assert "CircuitBreakerHighFailures" in cb_rules
        assert "CircuitBreakerEventSpike" in cb_rules

    def test_redis_rules_exist(self, alert_rules_content):
        """Verify Redis alert rules are defined"""
        groups = {g["name"]: g for g in alert_rules_content["groups"]}

        assert "autobot_redis_alerts" in groups
        redis_rules = {r["alert"]: r for r in groups["autobot_redis_alerts"]["rules"]}

        assert "RedisServerDown" in redis_rules
        assert "RedisConnectionErrors" in redis_rules
        assert "RedisHighMemory" in redis_rules
        assert "RedisPoolExhausted" in redis_rules
        assert "RedisHighLatency" in redis_rules

    def test_npu_rules_exist(self, alert_rules_content):
        """Verify NPU alert rules are defined"""
        groups = {g["name"]: g for g in alert_rules_content["groups"]}

        assert "autobot_npu_alerts" in groups
        npu_rules = {r["alert"]: r for r in groups["autobot_npu_alerts"]["rules"]}

        assert "NPUCircuitBreakerOpen" in npu_rules
        assert "NPUHighFailureRate" in npu_rules

    def test_security_rules_exist(self, alert_rules_content):
        """Verify security alert rules are defined"""
        groups = {g["name"]: g for g in alert_rules_content["groups"]}

        assert "autobot_security_alerts" in groups
        security_rules = {
            r["alert"]: r for r in groups["autobot_security_alerts"]["rules"]
        }

        assert "SecurityViolation" in security_rules
        assert "UnusualErrorPattern" in security_rules

    def test_circuit_breaker_open_rule_configuration(self, alert_rules_content):
        """Verify CircuitBreakerOpen rule has correct configuration"""
        groups = {g["name"]: g for g in alert_rules_content["groups"]}
        cb_rules = {r["alert"]: r for r in groups["autobot_circuit_breaker"]["rules"]}

        rule = cb_rules["CircuitBreakerOpen"]

        # Check expression
        assert rule["expr"] == "autobot_circuit_breaker_state == 1"

        # Check labels
        assert rule["labels"]["severity"] == "critical"
        assert rule["labels"]["component"] == "circuit_breaker"

        # Check annotations
        assert "summary" in rule["annotations"]
        assert "description" in rule["annotations"]
        assert "recommendation" in rule["annotations"]

    def test_all_rules_have_required_fields(self, alert_rules_content):
        """Verify all rules have required fields"""
        for group in alert_rules_content["groups"]:
            for rule in group["rules"]:
                assert (
                    "alert" in rule
                ), f"Rule missing 'alert' field in group {group['name']}"
                assert (
                    "expr" in rule
                ), f"Rule {rule.get('alert', 'unknown')} missing 'expr' field"
                assert "labels" in rule, f"Rule {rule['alert']} missing 'labels' field"
                assert (
                    "annotations" in rule
                ), f"Rule {rule['alert']} missing 'annotations' field"
                assert (
                    "severity" in rule["labels"]
                ), f"Rule {rule['alert']} missing 'severity' label"
                assert (
                    "summary" in rule["annotations"]
                ), f"Rule {rule['alert']} missing 'summary' annotation"


class TestAlertManagerConfig:
    """Test suite for AlertManager configuration"""

    @pytest.fixture
    def alertmanager_config(self):
        """Load AlertManager config YAML"""
        import yaml

        with open(
            "/home/kali/Desktop/AutoBot/config/prometheus/alertmanager.yml", "r"
        ) as f:
            return yaml.safe_load(f)

    def test_receivers_defined(self, alertmanager_config):
        """Verify required receivers are defined"""
        receivers = {r["name"]: r for r in alertmanager_config["receivers"]}

        required_receivers = [
            "default",
            "critical-alerts",
            "high-alerts",
            "medium-alerts",
            "circuit-breaker-alerts",
            "redis-alerts",
            "npu-alerts",
            "security-alerts",
            "service-alerts",
            "error-alerts",
        ]

        for receiver_name in required_receivers:
            assert receiver_name in receivers, f"Missing receiver: {receiver_name}"

    def test_routes_defined(self, alertmanager_config):
        """Verify routes are defined for components"""
        routes = alertmanager_config["route"]["routes"]
        route_components = [r.get("match", {}).get("component") for r in routes]

        assert "circuit_breaker" in route_components
        assert "redis" in route_components
        assert "npu" in route_components
        assert "security" in route_components

    def test_webhook_configs_have_correct_url(self, alertmanager_config):
        """Verify webhook URLs are correct"""
        for receiver in alertmanager_config["receivers"]:
            if "webhook_configs" in receiver:
                for webhook in receiver["webhook_configs"]:
                    assert "172.16.168.20:8001" in webhook["url"]
                    assert "/api/webhook/alertmanager" in webhook["url"]

    def test_inhibition_rules_defined(self, alertmanager_config):
        """Verify circuit breaker inhibition rules are defined"""
        inhibit_rules = alertmanager_config.get("inhibit_rules", [])

        # Find circuit breaker inhibition rules
        cb_inhibitions = [
            r
            for r in inhibit_rules
            if r.get("source_match", {}).get("alertname") == "CircuitBreakerOpen"
        ]

        assert len(cb_inhibitions) >= 3, "Missing circuit breaker inhibition rules"

    def test_redis_inhibition_rules(self, alertmanager_config):
        """Verify Redis inhibition rules are defined"""
        inhibit_rules = alertmanager_config.get("inhibit_rules", [])

        # Find Redis inhibition rules
        redis_inhibitions = [
            r
            for r in inhibit_rules
            if r.get("source_match", {}).get("alertname") == "RedisServerDown"
        ]

        assert len(redis_inhibitions) >= 1, "Missing Redis inhibition rules"


class TestEnvironmentVariables:
    """Test suite for alert environment variables"""

    def test_env_example_has_alert_config(self):
        """Verify .env.example has alert configuration section"""
        with open("/home/kali/Desktop/AutoBot/.env.example", "r") as f:
            content = f.read()

        assert "ALERT NOTIFICATION CONFIGURATION" in content
        assert "ALERT_ERROR_RATE_THRESHOLD" in content
        assert "ALERT_COOLDOWN_SECONDS" in content
        assert "ALERT_CIRCUIT_BREAKER_FAILURE_WARNING" in content

    def test_env_example_has_email_config(self):
        """Verify .env.example has email notification config"""
        with open("/home/kali/Desktop/AutoBot/.env.example", "r") as f:
            content = f.read()

        assert "ALERT_EMAIL_USERNAME" in content
        assert "ALERT_EMAIL_PASSWORD" in content
        assert "ALERT_EMAIL_TO" in content

    def test_env_example_has_slack_config(self):
        """Verify .env.example has Slack notification config"""
        with open("/home/kali/Desktop/AutoBot/.env.example", "r") as f:
            content = f.read()

        assert "ALERT_SLACK_WEBHOOK_URL" in content
