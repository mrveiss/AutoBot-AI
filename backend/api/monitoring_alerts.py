#!/usr/bin/env python3
"""
Monitoring Alerts API endpoints
Provides REST API for managing alerts and notifications
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel

from src.utils.monitoring_alerts import (
    get_alerts_manager, 
    AlertRule, 
    Alert, 
    AlertSeverity, 
    AlertStatus,
    LogNotificationChannel,
    RedisNotificationChannel
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Pydantic models for API
class AlertRuleRequest(BaseModel):
    """Request model for creating/updating alert rules"""
    name: str
    metric_path: str
    threshold: float
    operator: str  # "gt", "lt", "eq", "gte", "lte"
    severity: str  # "low", "medium", "high", "critical"
    duration: int = 300
    cooldown: int = 1800
    description: str = ""
    enabled: bool = True
    tags: List[str] = []


class AlertRuleResponse(BaseModel):
    """Response model for alert rules"""
    id: str
    name: str
    metric_path: str
    threshold: float
    operator: str
    severity: str
    duration: int
    cooldown: int
    description: str
    enabled: bool
    tags: List[str]


class AlertResponse(BaseModel):
    """Response model for alerts"""
    rule_id: str
    rule_name: str
    metric_path: str
    current_value: float
    threshold: float
    severity: str
    status: str
    message: str
    created_at: str
    updated_at: str
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None
    tags: List[str]


class NotificationChannelRequest(BaseModel):
    """Request model for notification channels"""
    name: str
    type: str  # "log", "redis", "webhook"
    config: Dict[str, Any]
    enabled: bool = True


@router.get("/health")
async def alerts_health_check():
    """Health check for monitoring alerts system"""
    try:
        alerts_manager = get_alerts_manager()
        active_alerts = alerts_manager.get_active_alerts()
        alert_rules = alerts_manager.get_alert_rules()
        
        return {
            "status": "healthy",
            "service": "monitoring_alerts",
            "monitoring_active": alerts_manager.running,
            "active_alerts_count": len(active_alerts),
            "alert_rules_count": len(alert_rules),
            "notification_channels": list(alerts_manager.notification_channels.keys()),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Alerts health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/status")
async def get_alerts_status():
    """Get comprehensive alerts system status"""
    try:
        alerts_manager = get_alerts_manager()
        active_alerts = alerts_manager.get_active_alerts()
        alert_rules = alerts_manager.get_alert_rules()
        
        # Count alerts by severity
        severity_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for alert in active_alerts:
            severity_counts[alert.severity.value] += 1
        
        # Count alerts by status
        status_counts = {"active": 0, "acknowledged": 0}
        for alert in active_alerts:
            if alert.status.value in status_counts:
                status_counts[alert.status.value] += 1
        
        # Get enabled notification channels
        enabled_channels = [name for name, channel in alerts_manager.notification_channels.items() if channel.enabled]
        
        return {
            "monitoring_active": alerts_manager.running,
            "check_interval_seconds": alerts_manager.check_interval,
            "summary": {
                "total_alerts": len(active_alerts),
                "critical_alerts": severity_counts["critical"],
                "high_alerts": severity_counts["high"],
                "medium_alerts": severity_counts["medium"],
                "low_alerts": severity_counts["low"],
                "acknowledged_alerts": status_counts["acknowledged"],
                "active_rules": len([r for r in alert_rules if r.enabled]),
                "total_rules": len(alert_rules)
            },
            "severity_breakdown": severity_counts,
            "status_breakdown": status_counts,
            "notification_channels": {
                "total": len(alerts_manager.notification_channels),
                "enabled": enabled_channels,
                "disabled": [name for name in alerts_manager.notification_channels.keys() if name not in enabled_channels]
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting alerts status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts", response_model=List[AlertResponse])
async def get_active_alerts(
    severity: Optional[str] = Query(None, description="Filter by severity"),
    status: Optional[str] = Query(None, description="Filter by status"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)")
):
    """Get all active alerts with optional filters"""
    try:
        alerts_manager = get_alerts_manager()
        alerts = alerts_manager.get_active_alerts()
        
        # Apply filters
        if severity:
            alerts = [a for a in alerts if a.severity.value == severity.lower()]
        
        if status:
            alerts = [a for a in alerts if a.status.value == status.lower()]
        
        if tags:
            filter_tags = set(tag.strip() for tag in tags.split(","))
            alerts = [a for a in alerts if filter_tags.intersection(set(a.tags))]
        
        # Convert to response format
        response_alerts = []
        for alert in alerts:
            response_alerts.append(AlertResponse(
                rule_id=alert.rule_id,
                rule_name=alert.rule_name,
                metric_path=alert.metric_path,
                current_value=alert.current_value,
                threshold=alert.threshold,
                severity=alert.severity.value,
                status=alert.status.value,
                message=alert.message,
                created_at=alert.created_at.isoformat(),
                updated_at=alert.updated_at.isoformat(),
                acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                acknowledged_by=alert.acknowledged_by,
                tags=alert.tags
            ))
        
        return response_alerts
        
    except Exception as e:
        logger.error(f"Error getting active alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/{rule_id}/acknowledge")
async def acknowledge_alert(rule_id: str, acknowledged_by: str = "api_user"):
    """Acknowledge an active alert"""
    try:
        alerts_manager = get_alerts_manager()
        success = alerts_manager.acknowledge_alert(rule_id, acknowledged_by)
        
        if success:
            return {
                "status": "success",
                "message": f"Alert {rule_id} acknowledged by {acknowledged_by}",
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=404, detail="Alert not found or not active")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules", response_model=List[AlertRuleResponse])
async def get_alert_rules(enabled_only: bool = Query(False, description="Return only enabled rules")):
    """Get all alert rules"""
    try:
        alerts_manager = get_alerts_manager()
        rules = alerts_manager.get_alert_rules()
        
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        
        response_rules = []
        for rule in rules:
            response_rules.append(AlertRuleResponse(
                id=rule.id,
                name=rule.name,
                metric_path=rule.metric_path,
                threshold=rule.threshold,
                operator=rule.operator,
                severity=rule.severity.value,
                duration=rule.duration,
                cooldown=rule.cooldown,
                description=rule.description,
                enabled=rule.enabled,
                tags=rule.tags
            ))
        
        return response_rules
        
    except Exception as e:
        logger.error(f"Error getting alert rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rules", response_model=AlertRuleResponse)
async def create_alert_rule(rule_request: AlertRuleRequest):
    """Create a new alert rule"""
    try:
        alerts_manager = get_alerts_manager()
        
        # Generate rule ID
        rule_id = f"{rule_request.name.lower().replace(' ', '_')}_{int(datetime.now().timestamp())}"
        
        # Validate severity
        try:
            severity = AlertSeverity(rule_request.severity.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {rule_request.severity}")
        
        # Validate operator
        valid_operators = ["gt", "gte", "lt", "lte", "eq"]
        if rule_request.operator not in valid_operators:
            raise HTTPException(status_code=400, detail=f"Invalid operator: {rule_request.operator}")
        
        # Create alert rule
        rule = AlertRule(
            id=rule_id,
            name=rule_request.name,
            metric_path=rule_request.metric_path,
            threshold=rule_request.threshold,
            operator=rule_request.operator,
            severity=severity,
            duration=rule_request.duration,
            cooldown=rule_request.cooldown,
            description=rule_request.description,
            enabled=rule_request.enabled,
            tags=rule_request.tags
        )
        
        alerts_manager.add_alert_rule(rule)
        
        return AlertRuleResponse(
            id=rule.id,
            name=rule.name,
            metric_path=rule.metric_path,
            threshold=rule.threshold,
            operator=rule.operator,
            severity=rule.severity.value,
            duration=rule.duration,
            cooldown=rule.cooldown,
            description=rule.description,
            enabled=rule.enabled,
            tags=rule.tags
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating alert rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/rules/{rule_id}")
async def update_alert_rule(rule_id: str, rule_request: AlertRuleRequest):
    """Update an existing alert rule"""
    try:
        alerts_manager = get_alerts_manager()
        
        if rule_id not in alerts_manager.alert_rules:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        
        # Validate severity
        try:
            severity = AlertSeverity(rule_request.severity.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {rule_request.severity}")
        
        # Validate operator
        valid_operators = ["gt", "gte", "lt", "lte", "eq"]
        if rule_request.operator not in valid_operators:
            raise HTTPException(status_code=400, detail=f"Invalid operator: {rule_request.operator}")
        
        # Update the rule
        rule = AlertRule(
            id=rule_id,
            name=rule_request.name,
            metric_path=rule_request.metric_path,
            threshold=rule_request.threshold,
            operator=rule_request.operator,
            severity=severity,
            duration=rule_request.duration,
            cooldown=rule_request.cooldown,
            description=rule_request.description,
            enabled=rule_request.enabled,
            tags=rule_request.tags
        )
        
        alerts_manager.add_alert_rule(rule)  # This will update existing rule
        
        return {
            "status": "success",
            "message": f"Alert rule {rule_id} updated successfully",
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating alert rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(rule_id: str):
    """Delete an alert rule"""
    try:
        alerts_manager = get_alerts_manager()
        
        if rule_id not in alerts_manager.alert_rules:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        
        await alerts_manager.remove_alert_rule(rule_id)
        
        return {
            "status": "success",
            "message": f"Alert rule {rule_id} deleted successfully",
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting alert rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rules/{rule_id}/enable")
async def enable_alert_rule(rule_id: str):
    """Enable an alert rule"""
    try:
        alerts_manager = get_alerts_manager()
        
        if rule_id not in alerts_manager.alert_rules:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        
        rule = alerts_manager.alert_rules[rule_id]
        rule.enabled = True
        
        return {
            "status": "success",
            "message": f"Alert rule {rule_id} enabled",
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling alert rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rules/{rule_id}/disable")
async def disable_alert_rule(rule_id: str):
    """Disable an alert rule"""
    try:
        alerts_manager = get_alerts_manager()
        
        if rule_id not in alerts_manager.alert_rules:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        
        rule = alerts_manager.alert_rules[rule_id]
        rule.enabled = False
        
        # Resolve any active alerts for this rule
        if rule_id in alerts_manager.active_alerts:
            await alerts_manager._resolve_alert(rule_id)
        
        return {
            "status": "success",
            "message": f"Alert rule {rule_id} disabled",
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling alert rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitoring/start")
async def start_monitoring(background_tasks: BackgroundTasks):
    """Start the monitoring system"""
    try:
        alerts_manager = get_alerts_manager()
        
        if alerts_manager.running:
            return {
                "status": "already_running",
                "message": "Monitoring system is already active",
                "timestamp": datetime.now().isoformat()
            }
        
        # Start monitoring in background
        background_tasks.add_task(alerts_manager.start_monitoring)
        
        return {
            "status": "success",
            "message": "Monitoring system started",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error starting monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitoring/stop")
async def stop_monitoring():
    """Stop the monitoring system"""
    try:
        alerts_manager = get_alerts_manager()
        alerts_manager.stop_monitoring()
        
        return {
            "status": "success",
            "message": "Monitoring system stopped",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error stopping monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channels")
async def get_notification_channels():
    """Get all notification channels"""
    try:
        alerts_manager = get_alerts_manager()
        
        channels_info = []
        for name, channel in alerts_manager.notification_channels.items():
            channels_info.append({
                "name": name,
                "type": channel.__class__.__name__,
                "enabled": channel.enabled,
                "config": getattr(channel, 'config', {})
            })
        
        return {
            "channels": channels_info,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting notification channels: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-alert")
async def test_alert_system():
    """Send a test alert through all notification channels"""
    try:
        alerts_manager = get_alerts_manager()
        
        # Create a test alert
        test_alert = Alert(
            rule_id="test_alert",
            rule_name="Test Alert",
            metric_path="test.metric",
            current_value=99.0,
            threshold=80.0,
            severity=AlertSeverity.MEDIUM,
            status=AlertStatus.ACTIVE,
            message="This is a test alert to verify notification channels are working",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=["test", "verification"]
        )
        
        # Send through all enabled channels
        sent_channels = []
        failed_channels = []
        
        for channel_name, channel in alerts_manager.notification_channels.items():
            if channel.enabled:
                try:
                    success = await channel.send_alert(test_alert)
                    if success:
                        sent_channels.append(channel_name)
                    else:
                        failed_channels.append(channel_name)
                except Exception as e:
                    logger.error(f"Test alert failed on {channel_name}: {e}")
                    failed_channels.append(channel_name)
        
        return {
            "status": "success",
            "message": "Test alert sent",
            "sent_channels": sent_channels,
            "failed_channels": failed_channels,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error sending test alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))