#!/usr/bin/env python3
"""
Advanced Monitoring Alerts and Notifications System
Monitors system metrics and sends alerts when thresholds are exceeded
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


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


class AlertNotificationChannel:
    """Base class for notification channels"""

    def __init__(self, name: str, config: Dict[str, Any]):
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

    async def send_alert(self, alert: Alert) -> bool:
        """Log the alert"""
        try:
            severity_emoji = {
                AlertSeverity.LOW: "ℹ️",
                AlertSeverity.MEDIUM: "⚠️",
                AlertSeverity.HIGH: "🚨",
                AlertSeverity.CRITICAL: "🔥",
            }

            emoji = severity_emoji.get(alert.severity, "⚠️")
            logger.warning(
                f"{emoji} ALERT [{alert.severity.value.upper()}] {alert.rule_name}: "
                f"{alert.message} (Value: {alert.current_value}, Threshold: {alert.threshold})"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send log alert: {e}")
            return False

    async def send_recovery(self, alert: Alert) -> bool:
        """Log the recovery"""
        try:
            logger.info(
                f"✅ RESOLVED [{alert.severity.value.upper()}] {alert.rule_name}: Alert resolved"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send log recovery: {e}")
            return False


class RedisNotificationChannel(AlertNotificationChannel):
    """Redis pub/sub notification channel"""

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.redis_client = None
        self._initialize_redis()

    def _initialize_redis(self):
        """Initialize Redis connection"""
        try:
            from autobot_shared.redis_client import get_redis_client

            self.redis_client = get_redis_client(
                async_client=False, database="analytics"
            )
        except Exception as e:
            logger.warning(f"Could not initialize Redis for alerts: {e}")

    async def send_alert(self, alert: Alert) -> bool:
        """Publish alert to Redis channel"""
        try:
            if not self.redis_client:
                return False

            alert_data = {
                "type": "alert",
                "rule_id": alert.rule_id,
                "rule_name": alert.rule_name,
                "severity": alert.severity.value,
                "message": alert.message,
                "current_value": alert.current_value,
                "threshold": alert.threshold,
                "metric_path": alert.metric_path,
                "created_at": alert.created_at.isoformat(),
                "tags": alert.tags,
                "metadata": alert.metadata,
            }

            channel = self.config.get("alert_channel", "system_alerts")
            self.redis_client.publish(channel, json.dumps(alert_data))
            return True
        except Exception as e:
            logger.error(f"Failed to send Redis alert: {e}")
            return False

    async def send_recovery(self, alert: Alert) -> bool:
        """Publish recovery to Redis channel"""
        try:
            if not self.redis_client:
                return False

            recovery_data = {
                "type": "recovery",
                "rule_id": alert.rule_id,
                "rule_name": alert.rule_name,
                "severity": alert.severity.value,
                "resolved_at": (
                    alert.resolved_at.isoformat()
                    if alert.resolved_at
                    else datetime.now().isoformat()
                ),
                "tags": alert.tags,
            }

            channel = self.config.get("recovery_channel", "system_recoveries")
            self.redis_client.publish(channel, json.dumps(recovery_data))
            return True
        except Exception as e:
            logger.error(f"Failed to send Redis recovery: {e}")
            return False


class WebSocketNotificationChannel(AlertNotificationChannel):
    """WebSocket notification channel for real-time frontend alerts"""

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.websocket_manager = None

    def set_websocket_manager(self, manager):
        """Set WebSocket manager for broadcasting"""
        self.websocket_manager = manager

    async def send_alert(self, alert: Alert) -> bool:
        """Send alert via WebSocket to connected clients"""
        try:
            if not self.websocket_manager:
                return False

            alert_message = {
                "type": "system_alert",
                "data": {
                    "rule_id": alert.rule_id,
                    "rule_name": alert.rule_name,
                    "severity": alert.severity.value,
                    "message": alert.message,
                    "current_value": alert.current_value,
                    "threshold": alert.threshold,
                    "metric_path": alert.metric_path,
                    "created_at": alert.created_at.isoformat(),
                    "tags": alert.tags,
                    "status": alert.status.value,
                },
            }

            await self.websocket_manager.broadcast(json.dumps(alert_message))
            return True
        except Exception as e:
            logger.error(f"Failed to send WebSocket alert: {e}")
            return False

    async def send_recovery(self, alert: Alert) -> bool:
        """Send recovery via WebSocket to connected clients"""
        try:
            if not self.websocket_manager:
                return False

            recovery_message = {
                "type": "alert_recovery",
                "data": {
                    "rule_id": alert.rule_id,
                    "rule_name": alert.rule_name,
                    "severity": alert.severity.value,
                    "resolved_at": (
                        alert.resolved_at.isoformat()
                        if alert.resolved_at
                        else datetime.now().isoformat()
                    ),
                    "tags": alert.tags,
                },
            }

            await self.websocket_manager.broadcast(json.dumps(recovery_message))
            return True
        except Exception as e:
            logger.error(f"Failed to send WebSocket recovery: {e}")
            return False


class MonitoringAlertsManager:
    """Advanced monitoring alerts and notifications manager"""

    def __init__(self):
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.notification_channels: Dict[str, AlertNotificationChannel] = {}
        self.metric_history: Dict[
            str, List[Tuple[float, float]]
        ] = {}  # metric_path -> [(timestamp, value)]
        self.redis_client = None
        self.running = False
        self.check_interval = 30  # seconds

        # Rate limiting for alert spam prevention
        self._alert_rate_limits = {}  # rule_id -> last_alert_time
        self._alert_rate_limit_interval = 300  # 5 minutes between same alerts

        self._initialize_redis()
        self._load_default_rules()
        self._setup_default_channels()

    def _initialize_redis(self):
        """Initialize Redis connection for alert storage"""
        try:
            from autobot_shared.redis_client import get_redis_client

            self.redis_client = get_redis_client(
                async_client=False, database="analytics"
            )
        except Exception as e:
            logger.warning(f"Could not initialize Redis for alert storage: {e}")

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

    def _create_cpu_alert_rules(self) -> List[AlertRule]:
        """
        Create CPU usage alert rules for VM0.

        Returns list of AlertRule objects for high and critical CPU thresholds.
        Issue #620.
        """
        return [
            AlertRule(
                id="vm0_high_cpu",
                name="VM0 High CPU Usage",
                metric_path="vm0.stats.cpu_usage",
                threshold=80.0,
                operator="gt",
                severity=AlertSeverity.HIGH,
                duration=300,  # 5 minutes
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
                duration=120,  # 2 minutes
                description="VM0 CPU usage exceeds 95%",
                tags=["cpu", "performance", "vm0", "critical"],
            ),
        ]

    def _create_memory_alert_rules(self) -> List[AlertRule]:
        """
        Create memory usage alert rules for VM0.

        Returns list of AlertRule objects for high and critical memory thresholds.
        Issue #620.
        """
        return [
            AlertRule(
                id="vm0_high_memory",
                name="VM0 High Memory Usage",
                metric_path="vm0.stats.memory_percent",
                threshold=85.0,
                operator="gt",
                severity=AlertSeverity.HIGH,
                duration=600,  # 10 minutes
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
                duration=180,  # 3 minutes
                description="VM0 memory usage exceeds 95%",
                tags=["memory", "performance", "vm0", "critical"],
            ),
        ]

    def _create_disk_alert_rules(self) -> List[AlertRule]:
        """
        Create disk usage alert rules for VM0.

        Returns list of AlertRule objects for high and critical disk thresholds.
        Issue #620.
        """
        return [
            AlertRule(
                id="vm0_high_disk",
                name="VM0 High Disk Usage",
                metric_path="vm0.stats.disk_percent",
                threshold=85.0,
                operator="gt",
                severity=AlertSeverity.MEDIUM,
                duration=3600,  # 1 hour
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
                duration=900,  # 15 minutes
                description="VM0 disk usage exceeds 95%",
                tags=["disk", "storage", "vm0", "critical"],
            ),
        ]

    def _create_load_alert_rules(self) -> List[AlertRule]:
        """
        Create load average alert rules for VM0.

        Returns list of AlertRule objects for high load thresholds.
        Issue #620.
        """
        return [
            AlertRule(
                id="vm0_high_load",
                name="VM0 High Load Average",
                metric_path="vm0.stats.cpu_load_1m",
                threshold=4.0,  # Assuming typical 4-core system
                operator="gt",
                severity=AlertSeverity.MEDIUM,
                duration=600,  # 10 minutes
                description="VM0 1-minute load average exceeds 4.0",
                tags=["load", "performance", "vm0"],
            ),
        ]

    def _create_service_alert_rules(self) -> List[AlertRule]:
        """
        Create service health alert rules.

        Returns list of AlertRule objects for critical service availability monitoring.
        Issue #620.
        """
        return [
            AlertRule(
                id="backend_api_down",
                name="Backend API Unavailable",
                metric_path="vm0.services.core.backend_api.status",
                threshold=0,  # 0 = offline/error, 1 = online
                operator="eq",
                severity=AlertSeverity.CRITICAL,
                duration=60,  # 1 minute
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

    def _load_default_rules(self):
        """
        Load default alert rules based on system configuration.

        Aggregates rules from helper methods for CPU, memory, disk, load,
        and service health monitoring. Issue #620.
        """
        default_rules: List[AlertRule] = []

        # Collect rules from categorized helper methods
        default_rules.extend(self._create_cpu_alert_rules())
        default_rules.extend(self._create_memory_alert_rules())
        default_rules.extend(self._create_disk_alert_rules())
        default_rules.extend(self._create_load_alert_rules())
        default_rules.extend(self._create_service_alert_rules())

        # Add rules to manager
        for rule in default_rules:
            self.alert_rules[rule.id] = rule

        logger.info(f"Loaded {len(default_rules)} default alert rules")

    def add_alert_rule(self, rule: AlertRule):
        """Add or update an alert rule"""
        self.alert_rules[rule.id] = rule
        logger.info(f"Added alert rule: {rule.name} ({rule.id})")

    async def remove_alert_rule(self, rule_id: str):
        """Remove an alert rule"""
        if rule_id in self.alert_rules:
            rule = self.alert_rules.pop(rule_id)
            logger.info(f"Removed alert rule: {rule.name} ({rule_id})")

            # Also resolve any active alerts for this rule
            if rule_id in self.active_alerts:
                await self._resolve_alert(rule_id)

    def add_notification_channel(self, channel: AlertNotificationChannel):
        """Add a notification channel"""
        self.notification_channels[channel.name] = channel
        logger.info(f"Added notification channel: {channel.name}")

    def set_websocket_manager(self, websocket_manager):
        """Set WebSocket manager for real-time notifications"""
        if "websocket" in self.notification_channels:
            self.notification_channels["websocket"].set_websocket_manager(
                websocket_manager
            )
            self.notification_channels["websocket"].enabled = True
            logger.info("Enabled WebSocket notifications")

    def _evaluate_operator(
        self, current_value: float, threshold: float, operator: str
    ) -> bool:
        """Evaluate if condition is met based on operator"""
        if operator == "gt":
            return current_value > threshold
        elif operator == "gte":
            return current_value >= threshold
        elif operator == "lt":
            return current_value < threshold
        elif operator == "lte":
            return current_value <= threshold
        elif operator == "eq":
            return current_value == threshold
        else:
            logger.warning(f"Unknown operator: {operator}")
            return False

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Optional[float]:
        """Get nested value from dict using dot notation path"""
        try:
            keys = path.split(".")
            current = data

            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                elif isinstance(current, list):
                    # Handle list indices
                    try:
                        idx = int(key)
                        current = current[idx]
                    except (ValueError, IndexError):
                        return None
                else:
                    return None

            # Convert service status to numeric for comparison
            if isinstance(current, str):
                if current == "online":
                    return 1.0
                elif current in ["offline", "error"]:
                    return 0.0
                elif current == "warning":
                    return 0.5

            return float(current) if current is not None else None
        except (KeyError, ValueError, TypeError) as e:
            logger.debug(f"Could not get value for path {path}: {e}")
            return None

    def _should_trigger_alert(self, rule: AlertRule, current_value: float) -> bool:
        """Check if alert should be triggered based on duration"""
        current_time = time.time()

        # Track metric history for duration checking
        if rule.metric_path not in self.metric_history:
            self.metric_history[rule.metric_path] = []

        history = self.metric_history[rule.metric_path]
        history.append((current_time, current_value))

        # Keep only relevant history (duration + buffer)
        cutoff_time = current_time - (rule.duration + 300)  # Add 5 min buffer
        self.metric_history[rule.metric_path] = [
            (t, v) for t, v in history if t > cutoff_time
        ]

        # Check if condition has been met for the required duration
        condition_start_time = None
        for timestamp, value in reversed(history):
            if self._evaluate_operator(value, rule.threshold, rule.operator):
                condition_start_time = timestamp
            else:
                break

        if condition_start_time is not None:
            duration_met = (current_time - condition_start_time) >= rule.duration
            return duration_met

        return False

    def _should_suppress_alert(self, rule: AlertRule) -> bool:
        """Check if alert should be suppressed due to cooldown"""
        if rule.id in self.active_alerts:
            alert = self.active_alerts[rule.id]
            if alert.status == AlertStatus.ACTIVE:
                last_alert_time = alert.updated_at.timestamp()
                return (time.time() - last_alert_time) < rule.cooldown
        return False

    async def _create_alert(self, rule: AlertRule, current_value: float) -> Alert:
        """Create a new alert"""
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

        self.active_alerts[rule.id] = alert

        # Store in Redis if available
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
                self.redis_client.hset(f"alert:{rule.id}", mapping=alert_data)
                self.redis_client.expire(f"alert:{rule.id}", 86400 * 7)  # 7 days
            except Exception as e:
                logger.warning(f"Could not store alert in Redis: {e}")

        # Send notifications
        await self._send_alert_notifications(alert)

        # Apply rate limiting to alert logging to prevent spam
        current_time = time.time()
        last_alert_time = self._alert_rate_limits.get(rule.id, 0)

        if current_time - last_alert_time >= self._alert_rate_limit_interval:
            logger.warning(f"🚨 Alert created: {alert.rule_name} - {alert.message}")
            self._alert_rate_limits[rule.id] = current_time

        return alert

    async def _resolve_alert(self, rule_id: str):
        """Resolve an active alert"""
        if rule_id in self.active_alerts:
            alert = self.active_alerts[rule_id]
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now()
            alert.updated_at = datetime.now()

            # Update in Redis
            if self.redis_client:
                try:
                    self.redis_client.hset(
                        f"alert:{rule_id}",
                        mapping={
                            "status": alert.status.value,
                            "resolved_at": alert.resolved_at.isoformat(),
                            "updated_at": alert.updated_at.isoformat(),
                        },
                    )
                except Exception as e:
                    logger.warning(f"Could not update alert in Redis: {e}")

            # Send recovery notifications
            await self._send_recovery_notifications(alert)

            # Remove from active alerts
            del self.active_alerts[rule_id]

            logger.info(f"✅ Alert resolved: {alert.rule_name}")

    async def _send_alert_notifications(self, alert: Alert):
        """Send alert to all enabled notification channels"""
        for channel_name, channel in self.notification_channels.items():
            if channel.enabled:
                try:
                    success = await channel.send_alert(alert)
                    if success:
                        logger.debug(f"Alert sent via {channel_name}")
                    else:
                        logger.warning(f"Failed to send alert via {channel_name}")
                except Exception as e:
                    logger.error(f"Error sending alert via {channel_name}: {e}")

    async def _send_recovery_notifications(self, alert: Alert):
        """Send recovery notification to all enabled notification channels"""
        for channel_name, channel in self.notification_channels.items():
            if channel.enabled:
                try:
                    success = await channel.send_recovery(alert)
                    if success:
                        logger.debug(f"Recovery sent via {channel_name}")
                    else:
                        logger.warning(f"Failed to send recovery via {channel_name}")
                except Exception as e:
                    logger.error(f"Error sending recovery via {channel_name}: {e}")

    async def check_metrics(self, infrastructure_data: Dict[str, Any]):
        """Check all metrics against alert rules"""
        for rule_id, rule in self.alert_rules.items():
            if not rule.enabled:
                continue

            try:
                current_value = self._get_nested_value(
                    infrastructure_data, rule.metric_path
                )

                if current_value is None:
                    logger.debug(f"No value found for metric path: {rule.metric_path}")
                    continue

                condition_met = self._evaluate_operator(
                    current_value, rule.threshold, rule.operator
                )

                if condition_met:
                    # Check if alert should be triggered based on duration
                    if self._should_trigger_alert(rule, current_value):
                        # Check if we're not in cooldown period
                        if not self._should_suppress_alert(rule):
                            if rule_id not in self.active_alerts:
                                await self._create_alert(rule, current_value)
                            else:
                                # Update existing alert
                                alert = self.active_alerts[rule_id]
                                alert.current_value = current_value
                                alert.updated_at = datetime.now()
                else:
                    # Condition not met, resolve alert if active
                    if rule_id in self.active_alerts:
                        await self._resolve_alert(rule_id)

            except Exception as e:
                logger.error(f"Error checking rule {rule_id}: {e}")

    async def start_monitoring(self):
        """Start the monitoring loop"""
        if self.running:
            logger.warning("Monitoring already running")
            return

        self.running = True
        logger.info("🔍 Started monitoring alerts system")

        # Issue #729: Infrastructure monitoring moved to SLM server
        # This legacy monitoring_alerts.py was replaced by Prometheus AlertManager (Issue #69)
        # Infrastructure data now available via SLM API instead of
        # backend.api.infrastructure_monitor
        logger.warning(
            "⚠️ Infrastructure monitoring deprecated - use SLM server and Prometheus AlertManager"
        )

        while self.running:
            try:
                # TODO #729: Implement SLM-based infrastructure monitoring if needed
                # For now, this monitoring loop is disabled as infrastructure APIs moved to SLM
                logger.info(
                    "Monitoring loop running (infrastructure checks disabled - see Issue #729)"
                )

                await asyncio.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(30)  # Wait longer on error

    def stop_monitoring(self):
        """Stop the monitoring loop"""
        self.running = False
        logger.info("⏹️ Stopped monitoring alerts system")

    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts"""
        return list(self.active_alerts.values())

    def get_alert_rules(self) -> List[AlertRule]:
        """Get all alert rules"""
        return list(self.alert_rules.values())

    def acknowledge_alert(self, rule_id: str, acknowledged_by: str = "system"):
        """Acknowledge an active alert"""
        if rule_id in self.active_alerts:
            alert = self.active_alerts[rule_id]
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = datetime.now()
            alert.acknowledged_by = acknowledged_by
            alert.updated_at = datetime.now()

            # Update in Redis
            if self.redis_client:
                try:
                    self.redis_client.hset(
                        f"alert:{rule_id}",
                        mapping={
                            "status": alert.status.value,
                            "acknowledged_at": alert.acknowledged_at.isoformat(),
                            "acknowledged_by": acknowledged_by,
                            "updated_at": alert.updated_at.isoformat(),
                        },
                    )
                except Exception as e:
                    logger.warning(
                        f"Could not update alert acknowledgment in Redis: {e}"
                    )

            logger.info(f"👤 Alert acknowledged: {alert.rule_name} by {acknowledged_by}")
            return True
        return False


# Global instance
alerts_manager = MonitoringAlertsManager()


def get_alerts_manager() -> MonitoringAlertsManager:
    """Get the global alerts manager instance"""
    return alerts_manager
