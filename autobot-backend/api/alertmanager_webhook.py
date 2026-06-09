# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AlertManager Webhook Integration
Receives alerts from Prometheus AlertManager and broadcasts to WebSocket clients.
Phase 3: Alert Migration (Issue #346)
Security: GH#9657 - Added webhook authentication (fail-closed)
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

from api.monitoring import ws_manager
from api.schemas_system import (
    AlertInstance,
    AlertManagerWebhook,
    AlertManagerWebhookHealthResponse,
    AlertManagerWebhookReceiveResponse,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])


@router.post("/alertmanager", response_model=AlertManagerWebhookReceiveResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="receive_alertmanager_webhook",
    error_code_prefix="ALERTMANAGER_WEBHOOK",
)
async def receive_alertmanager_webhook(payload: AlertManagerWebhook, request: Request):
    """
    Receive alerts from Prometheus AlertManager

    Phase 3 (Issue #346): AlertManager → WebSocket integration
    Replaces MonitoringAlertsManager's WebSocket notification channel

    Security (GH#9657): Requires X-AlertManager-Secret header authentication.
    Fails closed when ALERTMANAGER_WEBHOOK_SECRET is not configured.
    """
    try:
        # Verify webhook secret (GH#9657 fail-closed authentication)
        webhook_secret = os.environ.get("ALERTMANAGER_WEBHOOK_SECRET")
        if not webhook_secret:
            logger.error("AlertManager webhook secret not configured - failing closed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Webhook authentication not configured",
            )

        request_secret = request.headers.get("X-AlertManager-Secret")
        if not request_secret:
            logger.warning("AlertManager webhook authentication failed - missing secret header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authentication header",
            )

        if request_secret != webhook_secret:
            logger.warning("AlertManager webhook authentication failed - invalid secret")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid authentication credentials",
            )

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
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error("Failed to process AlertManager webhook: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook",
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
            },
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
                f"✅ RESOLVED [{labels.get('severity', '').upper()}] " f"{labels.get('alertname')}: Alert resolved"
            )

    except Exception as e:
        logger.error("Failed to process individual alert: %s", e, exc_info=True)


@router.get("/alertmanager/health", response_model=AlertManagerWebhookHealthResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="alertmanager_webhook_health",
    error_code_prefix="ALERTMANAGER_WEBHOOK",
)
async def alertmanager_webhook_health():
    """Health check endpoint for AlertManager webhook"""
    return {
        "status": "healthy",
        "endpoint": "/api/webhook/alertmanager",
        "websocket_manager": "connected" if ws_manager else "unavailable",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
