# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AlertManager Webhook Integration
Receives alerts from Prometheus AlertManager and broadcasts to WebSocket clients.
Phase 3: Alert Migration (Issue #346)
"""

import logging
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.api.monitoring import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])


class AlertAnnotations(BaseModel):
    """Alert annotations from AlertManager"""
    summary: str
    description: str
    recommendation: str | None = None


class AlertLabels(BaseModel):
    """Alert labels from AlertManager"""
    alertname: str
    severity: str
    component: str
    resource: str | None = None
    service: str | None = None


class AlertInstance(BaseModel):
    """Single alert instance from AlertManager"""
    status: str  # "firing" or "resolved"
    labels: Dict[str, str]
    annotations: Dict[str, str]
    startsAt: str
    endsAt: str | None = None
    generatorURL: str
    fingerprint: str


class AlertManagerWebhook(BaseModel):
    """AlertManager webhook payload structure"""
    version: str
    groupKey: str
    truncatedAlerts: int = 0
    status: str  # "firing" or "resolved"
    receiver: str
    groupLabels: Dict[str, str]
    commonLabels: Dict[str, str]
    commonAnnotations: Dict[str, str]
    externalURL: str
    alerts: List[AlertInstance]


@router.post("/alertmanager")
async def receive_alertmanager_webhook(
    payload: AlertManagerWebhook,
    request: Request
):
    """
    Receive alerts from Prometheus AlertManager

    Phase 3 (Issue #346): AlertManager → WebSocket integration
    Replaces MonitoringAlertsManager's WebSocket notification channel
    """
    try:
        logger.info(
            f"Received AlertManager webhook: {len(payload.alerts)} alerts "
            f"(status: {payload.status}, receiver: {payload.receiver})"
        )

        # Process each alert in the payload
        for alert in payload.alerts:
            await _process_alert(alert, payload.status)

        return {
            "status": "success",
            "processed": len(payload.alerts),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error("Failed to process AlertManager webhook: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process webhook: {str(e)}"
        )


async def _process_alert(alert: AlertInstance, group_status: str):
    """Process a single alert and broadcast to WebSocket clients"""
    try:
        # Extract alert details
        labels = alert.labels
        annotations = alert.annotations
        alert_status = alert.status  # "firing" or "resolved"

        # Convert AlertManager data to frontend format
        alert_data = {
            "type": "system_alert" if alert_status == "firing" else "alert_recovery",
            "data": {
                "rule_id": alert.fingerprint,
                "rule_name": labels.get("alertname", "Unknown Alert"),
                "severity": labels.get("severity", "unknown"),
                "component": labels.get("component", "unknown"),
                "resource": labels.get("resource"),
                "service": labels.get("service"),
                "message": annotations.get("summary", "No description available"),
                "description": annotations.get("description", ""),
                "recommendation": annotations.get("recommendation"),
                "status": alert_status,
                "starts_at": alert.startsAt,
                "ends_at": alert.endsAt,
                "generator_url": alert.generatorURL,
                "fingerprint": alert.fingerprint,
                "tags": [
                    labels.get("severity", ""),
                    labels.get("component", ""),
                    labels.get("resource", ""),
                ],
            }
        }

        # Broadcast to all connected WebSocket clients
        await ws_manager.broadcast_update(alert_data)

        # Log alert for audit trail
        severity_emoji = {
            "low": "ℹ️",
            "medium": "⚠️",
            "high": "🚨",
            "critical": "🔥",
            "warning": "⚠️",
        }
        emoji = severity_emoji.get(labels.get("severity", ""), "⚠️")

        if alert_status == "firing":
            logger.warning(
                f"{emoji} ALERT [{labels.get('severity', '').upper()}] "
                f"{labels.get('alertname')}: {annotations.get('summary')}"
            )
        else:
            logger.info(
                f"✅ RESOLVED [{labels.get('severity', '').upper()}] "
                f"{labels.get('alertname')}: Alert resolved"
            )

    except Exception as e:
        logger.error("Failed to process individual alert: %s", e, exc_info=True)


@router.get("/alertmanager/health")
async def alertmanager_webhook_health():
    """Health check endpoint for AlertManager webhook"""
    return {
        "status": "healthy",
        "endpoint": "/api/webhook/alertmanager",
        "websocket_manager": "connected" if ws_manager else "unavailable",
        "timestamp": datetime.now().isoformat()
    }
