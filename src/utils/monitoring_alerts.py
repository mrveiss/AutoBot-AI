#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced Monitoring Alerts and Notifications System
Monitors system metrics and sends alerts when thresholds are exceeded

DEPRECATED (Phase 3, Issue #346): This module is being replaced by Prometheus AlertManager.
All alert rules have been migrated to config/prometheus/alertmanager_rules.yml.
This module will be REMOVED in Phase 5.

Use Prometheus AlertManager instead:
    - Alert rules: config/prometheus/alertmanager_rules.yml
    - AlertManager config: config/prometheus/alertmanager.yml
    - WebSocket integration: backend/api/alertmanager_webhook.py
    - AlertManager UI: http://localhost:9093
"""

import warnings
warnings.warn(
    "monitoring_alerts module is deprecated and will be removed in Phase 5. "
    "Use Prometheus AlertManager with alertmanager_webhook.py instead.",
    DeprecationWarning,
    stacklevel=2
)

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.constants.threshold_constants import TimingConstants
from src.unified_config_manager import UnifiedConfigManager

# Create singleton config instance
config = UnifiedConfigManager()

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for status conversion (Issue #315)
STATUS_TO_NUMERIC = {
    "online": 1.0,
    "offline": 0.0,
    "error": 0.0,
    "warning": 0.5,
}


def _get_list_item(data: list, key: str) -> Any:
    """Get item from list by index key (Issue #315: extracted).

    Args:
        data: List to access
        key: String index (will be converted to int)

    Returns:
        List item or None if invalid index
    """
    try:
        idx = int(key)
        return data[idx]
    except (ValueError, IndexError):
        return None


def _convert_status_to_numeric(value: Any) -> float | None:
    """Convert string status or value to numeric (Issue #315: extracted).

    Args:
        value: Value to convert (string status or numeric)

    Returns:
        Float value or None
    """
    if value is None:
        return None

    if isinstance(value, str):
        return STATUS_TO_NUMERIC.get(value)

    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class AlertSeverity(Enum):
    """Alert severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Alert status tracking"""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


@dataclass
class AlertRule:
    """Configuration for an alert rule"""

    id: str
    name: str
    metric_path: str  # e.g., "vm0.stats.cpu_usage"
    threshold: float
    operator: str  # "gt", "lt", "eq", "gte", "lte"
    severity: AlertSeverity
    duration: int = 300  # Seconds condition must persist
    cooldown: int = 1800  # Seconds before re-alerting
    description: str = ""
    enabled: bool = True
    tags: List[str] = field(default_factory=list)


@dataclass
class Alert:
    """Active alert instance"""

    rule_id: str
    rule_name: str
    metric_path: str
    current_value: float
    threshold: float
    severity: AlertSeverity
    status: AlertStatus
    message: str
    created_at: datetime
    updated_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_redis_alert_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Redis pub/sub alert (Issue #372 - reduces feature envy).

        Returns:
            Dictionary containing alert data for Redis channel.
        """
        return {
            "type": "alert",
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "message": self.message,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "metric_path": self.metric_path,
            "created_at": self.created_at.isoformat(),
            "tags": self.tags,
            "metadata": self.metadata,
        }

    def to_redis_recovery_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Redis pub/sub recovery (Issue #372 - reduces feature envy).

        Returns:
            Dictionary containing recovery data for Redis channel.
        """
        return {
            "type": "recovery",
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "resolved_at": (
                self.resolved_at.isoformat()
                if self.resolved_at
                else datetime.now().isoformat()
            ),
            "tags": self.tags,
        }

    def to_websocket_alert_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for WebSocket alert message (Issue #372 - reduces feature envy).

        Returns:
            Dictionary containing alert data for WebSocket broadcast.
        """
        return {
            "type": "system_alert",
            "data": {
                "rule_id": self.rule_id,
                "rule_name": self.rule_name,
                "severity": self.severity.value,
                "message": self.message,
                "current_value": self.current_value,
                "threshold": self.threshold,
                "metric_path": self.metric_path,
                "created_at": self.created_at.isoformat(),
                "tags": self.tags,
                "status": self.status.value,
            },
        }

    def to_websocket_recovery_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for WebSocket recovery message (Issue #372 - reduces feature envy).

        Returns:
            Dictionary containing recovery data for WebSocket broadcast.
        """
        return {
            "type": "alert_recovery",
            "data": {
                "rule_id": self.rule_id,
                "rule_name": self.rule_name,
                "severity": self.severity.value,
                "resolved_at": (
                    self.resolved_at.isoformat()
                    if self.resolved_at
                    else datetime.now().isoformat()
                ),
                "tags": self.tags,
            },
        }

    def get_log_message(self) -> str:
        """Get formatted log message for alert (Issue #372 - reduces feature envy).

        Returns:
            Formatted string for logging.
        """
        return (
            f"{self.rule_name}: {self.message} "
            f"(Value: {self.current_value}, Threshold: {self.threshold})"
        )

    def to_response_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response (Issue #372 - reduces feature envy).

        Returns:
            Dictionary containing all alert data for API response.
        """
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "metric_path": self.metric_path,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "severity": self.severity.value,
            "status": self.status.value,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "acknowledged_at": (
                self.acknowledged_at.isoformat() if self.acknowledged_at else None
            ),
            "acknowledged_by": self.acknowledged_by,
            "tags": self.tags,
        }

    def copy(self) -> "Alert":
        """Create a deep copy of this alert (Issue #372 - reduces feature envy).

        Returns:
            New Alert instance with copied data.
        """
        return Alert(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            metric_path=self.metric_path,
            current_value=self.current_value,
            threshold=self.threshold,
            severity=self.severity,
            status=self.status,
            message=self.message,
            created_at=self.created_at,
            updated_at=self.updated_at,
            acknowledged_at=self.acknowledged_at,
            resolved_at=self.resolved_at,
            acknowledged_by=self.acknowledged_by,
            tags=list(self.tags),
            metadata=dict(self.metadata),
        )


class AlertNotificationChannel:
    """Base class for notification channels"""

    def __init__(self, name: str, config: Dict[str, Any]):
        """Initialize notification channel with name and configuration."""
        self.name = name
        self.config = config
        self.enabled = config.get("enabled", True)

    async def send_alert(self, alert: Alert) -> bool:
        """Send alert notification. Returns True if successful."""
        raise NotImplementedError

    async def send_recovery(self, alert: Alert) -> bool:
        """Send recovery notification. Returns True if successful."""
        raise NotImplementedError


class LogNotificationChannel(AlertNotificationChannel):
    """Log-based notification channel"""

    # Severity emoji mapping
    _SEVERITY_EMOJI = {
        AlertSeverity.LOW: "ℹ️",
        AlertSeverity.MEDIUM: "⚠️",
        AlertSeverity.HIGH: "🚨",
        AlertSeverity.CRITICAL: "🔥",
    }

    async def send_alert(self, alert: Alert) -> bool:
        """Log the alert to the application logger (Issue #372 - uses model method)."""
        try:
            emoji = self._SEVERITY_EMOJI.get(alert.severity, "⚠️")
            logger.warning(
                "%s ALERT [%s] %s",
                emoji, alert.severity.value.upper(), alert.get_log_message()
            )
            return True
        except Exception as e:
            logger.error("Failed to send log alert: %s", e)
            return False

    async def send_recovery(self, alert: Alert) -> bool:
        """Log the alert recovery to the application logger."""
        try:
            logger.info(
                "✅ RESOLVED [%s] %s: Alert resolved",
                alert.severity.value.upper(), alert.rule_name
            )
            return True
        except Exception as e:
            logger.error("Failed to send log recovery: %s", e)
            return False


class RedisNotificationChannel(AlertNotificationChannel):
    """Redis pub/sub notification channel"""

    def __init__(self, name: str, config: Dict[str, Any]):
        """Initialize Redis notification channel with pub/sub configuration."""
        super().__init__(name, config)
        self.redis_client = None
        self._initialize_redis()

    def _initialize_redis(self):
        """Initialize Redis connection using canonical utility"""
        try:
            # Use canonical Redis utility following CLAUDE.md "🔴 REDIS CLIENT USAGE" policy
            from src.utils.redis_client import get_redis_client

            self.redis_client = get_redis_client(database="metrics")
            if self.redis_client is None:
                logger.warning(
                    "Redis client initialization returned None (Redis disabled?)"
                )
        except Exception as e:
            logger.warning("Could not initialize Redis for alerts: %s", e)

    async def send_alert(self, alert: Alert) -> bool:
        """Publish alert to Redis channel (Issue #372 - uses model method)."""
        try:
            if not self.redis_client:
                return False

            channel = self.config.get("alert_channel", "system_alerts")
            # Issue #361: Execute sync Redis publish in thread pool
            # Issue #372: Use model method for serialization
            await asyncio.to_thread(
                self.redis_client.publish, channel, json.dumps(alert.to_redis_alert_dict())
            )
            return True
        except Exception as e:
            logger.error("Failed to send Redis alert: %s", e)
            return False

    async def send_recovery(self, alert: Alert) -> bool:
        """Publish recovery to Redis channel (Issue #372 - uses model method).

        Issue #361: Uses asyncio.to_thread() to avoid blocking event loop.
        """
        try:
            if not self.redis_client:
                return False

            channel = self.config.get("recovery_channel", "system_recoveries")
            # Issue #361: Execute sync Redis publish in thread pool
            # Issue #372: Use model method for serialization
            await asyncio.to_thread(
                self.redis_client.publish, channel, json.dumps(alert.to_redis_recovery_dict())
            )
            return True
        except Exception as e:
            logger.error("Failed to send Redis recovery: %s", e)
            return False


class WebSocketNotificationChannel(AlertNotificationChannel):
    """WebSocket notification channel for real-time frontend alerts"""

    def __init__(self, name: str, config: Dict[str, Any]):
        """Initialize WebSocket notification channel for real-time alerts."""
        super().__init__(name, config)
        self.websocket_manager = None

    def set_websocket_manager(self, manager):
        """Set WebSocket manager for broadcasting"""
        self.websocket_manager = manager

    async def send_alert(self, alert: Alert) -> bool:
        """Send alert via WebSocket to connected clients (Issue #372 - uses model method)."""
        try:
            if not self.websocket_manager:
                return False

            await self.websocket_manager.broadcast(
                json.dumps(alert.to_websocket_alert_dict())
            )
            return True
        except Exception as e:
            logger.error("Failed to send WebSocket alert: %s", e)
            return False

    async def send_recovery(self, alert: Alert) -> bool:
        """Send recovery via WebSocket to connected clients (Issue #372 - uses model method)."""
        try:
            if not self.websocket_manager:
                return False

            await self.websocket_manager.broadcast(
                json.dumps(alert.to_websocket_recovery_dict())
            )
            return True
        except Exception as e:
            logger.error("Failed to send WebSocket recovery: %s", e)
            return False


class MonitoringAlertsManager:
    """Advanced monitoring alerts and notifications manager"""

    def __init__(self):
        """Initialize alerts manager with rules, channels, and Redis storage."""
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.notification_channels: Dict[str, AlertNotificationChannel] = {}
        self.metric_history: Dict[str, List[Tuple[float, float]]] = (
            {}
        )  # metric_path -> [(timestamp, value)]
        self.redis_client = None
        self.running = False
        self.check_interval = 30  # seconds

        # Rate limiting for alert spam prevention
        self._alert_rate_limits = {}  # rule_id -> last_alert_time
        self._alert_rate_limit_interval = 300  # 5 minutes between same alerts

        # Lock for thread-safe access to shared mutable state
        self._lock = asyncio.Lock()

        self._initialize_redis()
        self._load_default_rules()
        self._setup_default_channels()

    def _initialize_redis(self):
        """Initialize Redis connection for alert storage using canonical utility"""
        try:
            # Use canonical Redis utility following CLAUDE.md "🔴 REDIS CLIENT USAGE" policy
            from src.utils.redis_client import get_redis_client

            self.redis_client = get_redis_client(database="metrics")
            if self.redis_client is None:
                logger.warning(
                    "Redis client initialization returned None (Redis disabled?)"
                )
        except Exception as e:
            logger.warning("Could not initialize Redis for alert storage: %s", e)

    def _setup_default_channels(self):
        """Setup default notification channels"""
        # Log channel (always enabled)
        self.notification_channels["log"] = LogNotificationChannel(
            "log", {"enabled": True}
        )

        # Redis pub/sub channel
        self.notification_channels["redis"] = RedisNotificationChannel(
            "redis",
            {
                "enabled": True,
                "alert_channel": "system_alerts",
                "recovery_channel": "system_recoveries",
            },
        )

        # WebSocket channel (will be enabled when WebSocket manager is available)
        self.notification_channels["websocket"] = WebSocketNotificationChannel(
            "websocket", {"enabled": False}
        )

    def _load_default_rules(self):
        """Load default alert rules based on system configuration (Issue #281 - uses helpers)."""
        default_rules = (
            self._get_cpu_alert_rules()
            + self._get_memory_alert_rules()
            + self._get_disk_alert_rules()
            + self._get_load_alert_rules()
            + self._get_service_health_rules()
        )

        for rule in default_rules:
            self.alert_rules[rule.id] = rule

        logger.info("Loaded %d default alert rules", len(default_rules))

    def _get_cpu_alert_rules(self) -> List[AlertRule]:
        """Get CPU usage alert rules (Issue #281 - extracted helper)."""
        return [
            AlertRule(
                id="vm0_high_cpu",
                name="VM0 High CPU Usage",
                metric_path="vm0.stats.cpu_usage",
                threshold=80.0,
                operator="gt",
                severity=AlertSeverity.HIGH,
                duration=300,
                description="VM0 CPU usage exceeds 80%",
                tags=["cpu", "performance", "vm0"],
            ),
            AlertRule(
                id="vm0_critical_cpu",
                name="VM0 Critical CPU Usage",
                metric_path="vm0.stats.cpu_usage",
                threshold=95.0,
                operator="gt",
                severity=AlertSeverity.CRITICAL,
                duration=120,
                description="VM0 CPU usage exceeds 95%",
                tags=["cpu", "performance", "vm0", "critical"],
            ),
        ]

    def _get_memory_alert_rules(self) -> List[AlertRule]:
        """Get memory usage alert rules (Issue #281 - extracted helper)."""
        return [
            AlertRule(
                id="vm0_high_memory",
                name="VM0 High Memory Usage",
                metric_path="vm0.stats.memory_percent",
                threshold=85.0,
                operator="gt",
                severity=AlertSeverity.HIGH,
                duration=600,
                description="VM0 memory usage exceeds 85%",
                tags=["memory", "performance", "vm0"],
            ),
            AlertRule(
                id="vm0_critical_memory",
                name="VM0 Critical Memory Usage",
                metric_path="vm0.stats.memory_percent",
                threshold=95.0,
                operator="gt",
                severity=AlertSeverity.CRITICAL,
                duration=180,
                description="VM0 memory usage exceeds 95%",
                tags=["memory", "performance", "vm0", "critical"],
            ),
        ]

    def _get_disk_alert_rules(self) -> List[AlertRule]:
        """Get disk usage alert rules (Issue #281 - extracted helper)."""
        return [
            AlertRule(
                id="vm0_high_disk",
                name="VM0 High Disk Usage",
                metric_path="vm0.stats.disk_percent",
                threshold=85.0,
                operator="gt",
                severity=AlertSeverity.MEDIUM,
                duration=3600,
                description="VM0 disk usage exceeds 85%",
                tags=["disk", "storage", "vm0"],
            ),
            AlertRule(
                id="vm0_critical_disk",
                name="VM0 Critical Disk Usage",
                metric_path="vm0.stats.disk_percent",
                threshold=95.0,
                operator="gt",
                severity=AlertSeverity.CRITICAL,
                duration=900,
                description="VM0 disk usage exceeds 95%",
                tags=["disk", "storage", "vm0", "critical"],
            ),
        ]

    def _get_load_alert_rules(self) -> List[AlertRule]:
        """Get load average alert rules (Issue #281 - extracted helper)."""
        return [
            AlertRule(
                id="vm0_high_load",
                name="VM0 High Load Average",
                metric_path="vm0.stats.cpu_load_1m",
                threshold=4.0,
                operator="gt",
                severity=AlertSeverity.MEDIUM,
                duration=600,
                description="VM0 1-minute load average exceeds 4.0",
                tags=["load", "performance", "vm0"],
            ),
        ]

    def _get_service_health_rules(self) -> List[AlertRule]:
        """Get service health alert rules (Issue #281 - extracted helper)."""
        return [
            AlertRule(
                id="backend_api_down",
                name="Backend API Unavailable",
                metric_path="vm0.services.core.backend_api.status",
                threshold=0,
                operator="eq",
                severity=AlertSeverity.CRITICAL,
                duration=60,
                description="Backend API is not responding",
                tags=["service", "api", "critical"],
            ),
            AlertRule(
                id="redis_down",
                name="Redis Database Unavailable",
                metric_path="vm0.services.database.redis.status",
                threshold=0,
                operator="eq",
                severity=AlertSeverity.CRITICAL,
                duration=60,
                description="Redis database is not accessible",
                tags=["service", "database", "critical"],
            ),
            AlertRule(
                id="ollama_down",
                name="Ollama LLM Service Down",
                metric_path="vm0.services.application.ollama.status",
                threshold=0,
                operator="eq",
                severity=AlertSeverity.HIGH,
                duration=120,
                description="Ollama LLM service is not responding",
                tags=["service", "llm", "high"],
            ),
        ]

    async def add_alert_rule(self, rule: AlertRule):
        """Add or update an alert rule (thread-safe)"""
        async with self._lock:
            self.alert_rules[rule.id] = rule
        logger.info("Added alert rule: %s (%s)", rule.name, rule.id)

    async def remove_alert_rule(self, rule_id: str):
        """Remove an alert rule (thread-safe)"""
        async with self._lock:
            if rule_id not in self.alert_rules:
                return
            rule = self.alert_rules.pop(rule_id)
            has_active_alert = rule_id in self.active_alerts

        logger.info("Removed alert rule: %s (%s)", rule.name, rule_id)

        # Also resolve any active alerts for this rule (outside lock)
        if has_active_alert:
            await self._resolve_alert(rule_id)

    async def add_notification_channel(self, channel: AlertNotificationChannel):
        """Add a notification channel (thread-safe)"""
        async with self._lock:
            self.notification_channels[channel.name] = channel
        logger.info("Added notification channel: %s", channel.name)

    async def set_websocket_manager(self, websocket_manager):
        """Set WebSocket manager for real-time notifications (thread-safe)"""
        async with self._lock:
            if "websocket" in self.notification_channels:
                self.notification_channels["websocket"].set_websocket_manager(
                    websocket_manager
                )
                self.notification_channels["websocket"].enabled = True
        logger.info("Enabled WebSocket notifications")

    # Operator dispatch table (Issue #315 - extracted to class constant)
    _OPERATOR_DISPATCH = {
        "gt": lambda v, t: v > t,
        "gte": lambda v, t: v >= t,
        "lt": lambda v, t: v < t,
        "lte": lambda v, t: v <= t,
        "eq": lambda v, t: v == t,
    }

    def _evaluate_operator(
        self, current_value: float, threshold: float, operator: str
    ) -> bool:
        """Evaluate if condition is met based on operator (Issue #315 - uses dispatch)"""
        evaluator = self._OPERATOR_DISPATCH.get(operator)
        if evaluator is None:
            logger.warning("Unknown operator: %s", operator)
            return False
        return evaluator(current_value, threshold)

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Optional[float]:
        """Get nested value from dict using dot notation path.
        Issue #315: Refactored to use helpers for reduced nesting.
        """
        try:
            current = data
            for key in path.split("."):
                current = self._traverse_path_key(current, key)
                if current is None:
                    return None

            return _convert_status_to_numeric(current)
        except (KeyError, ValueError, TypeError) as e:
            logger.debug("Could not get value for path %s: %s", path, e)
            return None

    def _traverse_path_key(self, current: Any, key: str) -> Any:
        """Traverse one key in a nested path (Issue #315: extracted).

        Args:
            current: Current position in data structure
            key: Key to traverse

        Returns:
            Value at key or None if not found
        """
        if isinstance(current, dict):
            return current.get(key)
        if isinstance(current, list):
            return _get_list_item(current, key)
        return None

    async def _should_trigger_alert(self, rule: AlertRule, current_value: float) -> bool:
        """Check if alert should be triggered based on duration (thread-safe)"""
        current_time = time.time()

        # Track metric history for duration checking under lock
        async with self._lock:
            if rule.metric_path not in self.metric_history:
                self.metric_history[rule.metric_path] = []

            history = self.metric_history[rule.metric_path]
            history.append((current_time, current_value))

            # Keep only relevant history (duration + buffer)
            cutoff_time = current_time - (rule.duration + 300)  # Add 5 min buffer
            self.metric_history[rule.metric_path] = [
                (t, v) for t, v in history if t > cutoff_time
            ]

            # Copy history for processing
            history_copy = list(history)

        # Check if condition has been met for the required duration (outside lock)
        condition_start_time = None
        for timestamp, value in reversed(history_copy):
            if self._evaluate_operator(value, rule.threshold, rule.operator):
                condition_start_time = timestamp
            else:
                break

        if condition_start_time is not None:
            duration_met = (current_time - condition_start_time) >= rule.duration
            return duration_met

        return False

    async def _should_suppress_alert(self, rule: AlertRule) -> bool:
        """Check if alert should be suppressed due to cooldown (thread-safe)"""
        async with self._lock:
            if rule.id in self.active_alerts:
                alert = self.active_alerts[rule.id]
                if alert.status == AlertStatus.ACTIVE:
                    last_alert_time = alert.updated_at.timestamp()
                    return (time.time() - last_alert_time) < rule.cooldown
        return False

    async def _create_alert(self, rule: AlertRule, current_value: float) -> Alert:
        """Create a new alert (thread-safe)"""
        alert = Alert(
            rule_id=rule.id,
            rule_name=rule.name,
            metric_path=rule.metric_path,
            current_value=current_value,
            threshold=rule.threshold,
            severity=rule.severity,
            status=AlertStatus.ACTIVE,
            message=f"{rule.description} (Current: {current_value}, Threshold: {rule.threshold})",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=rule.tags.copy(),
        )

        # Store alert under lock
        async with self._lock:
            self.active_alerts[rule.id] = alert

        # Store in Redis if available (outside lock)
        if self.redis_client:
            try:
                alert_data = {
                    "rule_id": alert.rule_id,
                    "rule_name": alert.rule_name,
                    "severity": alert.severity.value,
                    "status": alert.status.value,
                    "message": alert.message,
                    "current_value": str(alert.current_value),
                    "threshold": str(alert.threshold),
                    "created_at": alert.created_at.isoformat(),
                    "tags": ",".join(alert.tags) if alert.tags else "",
                }
                # Issue #361 - avoid blocking
                await asyncio.to_thread(
                    self.redis_client.hset, f"alert:{rule.id}", mapping=alert_data
                )
                await asyncio.to_thread(
                    self.redis_client.expire, f"alert:{rule.id}", 86400 * 7
                )  # 7 days
            except Exception as e:
                logger.warning("Could not store alert in Redis: %s", e)

        # Send notifications
        await self._send_alert_notifications(alert)

        # Apply rate limiting to alert logging to prevent spam (under lock)
        current_time = time.time()
        async with self._lock:
            last_alert_time = self._alert_rate_limits.get(rule.id, 0)
            should_log = current_time - last_alert_time >= self._alert_rate_limit_interval
            if should_log:
                self._alert_rate_limits[rule.id] = current_time

        if should_log:
            logger.warning("🚨 Alert created: %s - %s", alert.rule_name, alert.message)

        return alert

    async def _resolve_alert(self, rule_id: str):
        """Resolve an active alert (thread-safe)"""
        # Get and update alert under lock
        async with self._lock:
            if rule_id not in self.active_alerts:
                return
            alert = self.active_alerts[rule_id]
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now()
            alert.updated_at = datetime.now()
            # Issue #372: Use copy() method to reduce feature envy
            alert_copy = alert.copy()
            # Remove from active alerts
            del self.active_alerts[rule_id]

        # Update in Redis (outside lock)
        if self.redis_client:
            try:
                # Issue #361 - avoid blocking
                await asyncio.to_thread(
                    self.redis_client.hset,
                    f"alert:{rule_id}",
                    mapping={
                        "status": alert_copy.status.value,
                        "resolved_at": alert_copy.resolved_at.isoformat(),
                        "updated_at": alert_copy.updated_at.isoformat(),
                    },
                )
            except Exception as e:
                logger.warning("Could not update alert in Redis: %s", e)

        # Send recovery notifications (outside lock)
        await self._send_recovery_notifications(alert_copy)

        logger.info("✅ Alert resolved: %s", alert_copy.rule_name)

    async def _send_alert_notifications(self, alert: Alert):
        """Send alert to all enabled notification channels (thread-safe)"""
        # Copy channels list under lock
        async with self._lock:
            channels = [
                (name, channel)
                for name, channel in self.notification_channels.items()
                if channel.enabled
            ]

        # Send notifications outside lock
        for channel_name, channel in channels:
            try:
                success = await channel.send_alert(alert)
                if success:
                    logger.debug("Alert sent via %s", channel_name)
                else:
                    logger.warning("Failed to send alert via %s", channel_name)
            except Exception as e:
                logger.error("Error sending alert via %s: %s", channel_name, e)

    async def _send_recovery_notifications(self, alert: Alert):
        """Send recovery notification to all enabled notification channels (thread-safe)"""
        # Copy channels list under lock
        async with self._lock:
            channels = [
                (name, channel)
                for name, channel in self.notification_channels.items()
                if channel.enabled
            ]

        # Send notifications outside lock
        for channel_name, channel in channels:
            try:
                success = await channel.send_recovery(alert)
                if success:
                    logger.debug("Recovery sent via %s", channel_name)
                else:
                    logger.warning("Failed to send recovery via %s", channel_name)
            except Exception as e:
                logger.error("Error sending recovery via %s: %s", channel_name, e)

    async def _handle_condition_met(
        self, rule_id: str, rule, current_value: Any
    ) -> None:
        """Handle when alert condition is met (Issue #315 - extracted helper)."""
        if not await self._should_trigger_alert(rule, current_value):
            return
        if await self._should_suppress_alert(rule):
            return

        # Check and update under lock
        async with self._lock:
            if rule_id in self.active_alerts:
                # Update existing alert
                alert = self.active_alerts[rule_id]
                alert.current_value = current_value
                alert.updated_at = datetime.now()
                return

        # Create new alert (outside lock to avoid holding it during I/O)
        await self._create_alert(rule, current_value)

    async def _handle_condition_not_met(self, rule_id: str) -> None:
        """Handle when alert condition is not met (Issue #315 - extracted helper)."""
        async with self._lock:
            has_active = rule_id in self.active_alerts
        if has_active:
            await self._resolve_alert(rule_id)

    async def check_metrics(self, infrastructure_data: Dict[str, Any]):
        """Check all metrics against alert rules (Issue #315: depth 7→3)"""
        # Copy rules under lock
        async with self._lock:
            rules_copy = [(rule_id, rule) for rule_id, rule in self.alert_rules.items()]

        for rule_id, rule in rules_copy:
            if not rule.enabled:
                continue

            try:
                current_value = self._get_nested_value(
                    infrastructure_data, rule.metric_path
                )
                if current_value is None:
                    logger.debug("No value found for metric path: %s", rule.metric_path)
                    continue

                condition_met = self._evaluate_operator(
                    current_value, rule.threshold, rule.operator
                )

                if condition_met:
                    await self._handle_condition_met(rule_id, rule, current_value)
                else:
                    await self._handle_condition_not_met(rule_id)

            except Exception as e:
                logger.error("Error checking rule %s: %s", rule_id, e)

    async def start_monitoring(self):
        """Start the monitoring loop"""
        if self.running:
            logger.warning("Monitoring already running")
            return

        self.running = True
        logger.info("🔍 Started monitoring alerts system")

        while self.running:
            try:
                # Import here to avoid circular dependency
                from backend.api.infrastructure_monitor import monitor

                # Get infrastructure status
                machines = await monitor.get_infrastructure_status()

                # Convert to dict format for metric checking
                infrastructure_data = {}
                for machine in machines:
                    machine_data = {
                        "stats": {
                            "cpu_usage": (
                                machine.stats.cpu_usage if machine.stats else None
                            ),
                            "memory_percent": (
                                machine.stats.memory_percent if machine.stats else None
                            ),
                            "disk_percent": (
                                machine.stats.disk_percent if machine.stats else None
                            ),
                            "cpu_load_1m": (
                                machine.stats.cpu_load_1m if machine.stats else None
                            ),
                        },
                        "services": {
                            "core": {
                                service.name.lower().replace(" ", "_"): {
                                    "status": service.status
                                }
                                for service in machine.services.core
                            },
                            "database": {
                                service.name.lower().replace(" ", "_"): {
                                    "status": service.status
                                }
                                for service in machine.services.database
                            },
                            "application": {
                                service.name.lower().replace(" ", "_"): {
                                    "status": service.status
                                }
                                for service in machine.services.application
                            },
                        },
                    }
                    infrastructure_data[machine.id] = machine_data

                # Check metrics against alert rules
                await self.check_metrics(infrastructure_data)

                await asyncio.sleep(self.check_interval)

            except Exception as e:
                logger.error("Error in monitoring loop: %s", e)
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_LONG_DELAY)  # Wait longer on error

    def stop_monitoring(self):
        """Stop the monitoring loop"""
        self.running = False
        logger.info("⏹️ Stopped monitoring alerts system")

    async def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts (thread-safe)"""
        async with self._lock:
            return list(self.active_alerts.values())

    async def get_alert_rules(self) -> List[AlertRule]:
        """Get all alert rules (thread-safe)"""
        async with self._lock:
            return list(self.alert_rules.values())

    async def acknowledge_alert(
        self, rule_id: str, acknowledged_by: str = "system"
    ) -> bool:
        """Acknowledge an active alert (thread-safe)"""
        # Get and update alert under lock
        async with self._lock:
            if rule_id not in self.active_alerts:
                return False
            alert = self.active_alerts[rule_id]
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = datetime.now()
            alert.acknowledged_by = acknowledged_by
            alert.updated_at = datetime.now()
            # Copy data for Redis update
            alert_rule_name = alert.rule_name
            acknowledged_at_str = alert.acknowledged_at.isoformat()
            updated_at_str = alert.updated_at.isoformat()
            status_value = alert.status.value

        # Update in Redis (outside lock)
        if self.redis_client:
            try:
                # Issue #361 - avoid blocking
                await asyncio.to_thread(
                    self.redis_client.hset,
                    f"alert:{rule_id}",
                    mapping={
                        "status": status_value,
                        "acknowledged_at": acknowledged_at_str,
                        "acknowledged_by": acknowledged_by,
                        "updated_at": updated_at_str,
                    },
                )
            except Exception as e:
                logger.warning(
                    "Could not update alert acknowledgment in Redis: %s", e
                )

        logger.info("👤 Alert acknowledged: %s by %s", alert_rule_name, acknowledged_by)
        return True


# Global instance
alerts_manager = MonitoringAlertsManager()


def get_alerts_manager() -> MonitoringAlertsManager:
    """Get the global alerts manager instance"""
    return alerts_manager
