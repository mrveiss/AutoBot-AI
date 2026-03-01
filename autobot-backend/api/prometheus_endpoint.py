# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Prometheus Metrics HTTP Endpoint

Issue #1288: Exposes Prometheus-format metrics for scraping at /api/metrics/prometheus.
Moved from shared /metrics prefix to avoid collision with JSON metrics endpoints.
"""

from fastapi import APIRouter, Response
from monitoring.prometheus_metrics import get_metrics_manager
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get("")
async def metrics_endpoint():
    """
    Expose Prometheus metrics in text/plain format for scraping

    This endpoint is scraped by Prometheus at regular intervals
    configured in prometheus.yml (default: 15s)
    """
    metrics_manager = get_metrics_manager()

    # Generate metrics in Prometheus text format
    metrics_data = generate_latest(metrics_manager.registry)

    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)
