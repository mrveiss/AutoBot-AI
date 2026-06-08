# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

"""Monitoring integration API endpoints.

Provides REST API for interacting with monitoring platforms
like Datadog and New Relic.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas_code import (
    MonitoringAlertsResponse,
    MonitoringConnectionTestResponse,
    MonitoringEventsResponse,
    MonitoringHostsResponse,
    MonitoringMetricsResponse,
    MonitoringProvidersResponse,
)
from api.schemas_workflows import (
    EventsQueryRequest,
    MetricsQueryRequest,
    MonitoringConnectionTestRequest,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from integrations.base import IntegrationConfig
from integrations.monitoring_integration import DatadogIntegration, NewRelicIntegration

logger = get_logger(__name__)
router = APIRouter(
    tags=["integrations-monitoring"],
    dependencies=[Depends(check_admin_permission)],
)


@router.post("/test-connection", response_model=MonitoringConnectionTestResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_connection",
    error_code_prefix="INTEGRATION_MONITORING",
)
async def test_connection(request: MonitoringConnectionTestRequest) -> Dict[str, Any]:
    """Test connection to a monitoring provider.

    Args:
        request: Connection test parameters

    Returns:
        Dict with connection health status

    Raises:
        HTTPException: If connection test fails
    """
    try:
        config = _build_config(request.provider, request)
        integration = _get_integration(request.provider, config)
        health = await integration.test_connection()

        return {
            "provider": request.provider,
            "status": health.status.value,
            "message": health.message,
            "details": health.details,
        }
    except Exception:
        logger.exception("Connection test failed for %s", request.provider)
        raise HTTPException(status_code=500, detail="Connection test failed")


@router.get("/providers", response_model=MonitoringProvidersResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_providers",
    error_code_prefix="INTEGRATION_MONITORING",
)
async def list_providers() -> Dict[str, List[Dict[str, str]]]:
    """List supported monitoring providers.

    Returns:
        Dict with list of provider metadata
    """
    return {
        "providers": [
            {
                "name": "datadog",
                "display_name": "Datadog",
                "required_credentials": ["api_key", "app_key"],
            },
            {
                "name": "new_relic",
                "display_name": "New Relic",
                "required_credentials": ["api_key", "account_id"],
            },
        ]
    }


@router.get("/{provider}/hosts", response_model=MonitoringHostsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_hosts",
    error_code_prefix="INTEGRATION_MONITORING",
)
async def list_hosts(
    provider: str,
    api_key: str = Query(..., description="API key"),
    app_key: str | None = Query(None, description="Application key (Datadog)"),
) -> Dict[str, Any]:
    """List monitored hosts or applications.

    Args:
        provider: Monitoring provider name
        api_key: API key for authentication
        app_key: Application key (Datadog only)

    Returns:
        Dict with list of hosts/applications

    Raises:
        HTTPException: If provider is invalid or query fails
    """
    try:
        _validate_provider(provider)
        config = _build_config_from_params(provider, api_key, app_key, None)
        integration = _get_integration(provider, config)

        if provider == "datadog":
            result = await integration.execute_action("list_hosts", {})
        else:  # new_relic
            result = await integration.execute_action("list_applications", {})

        return result
    except ValueError:
        raise HTTPException(status_code=400, detail="Internal server error")
    except Exception:
        logger.exception("Failed to list hosts for %s", provider)
        raise HTTPException(status_code=500, detail="Failed to list hosts")


@router.post("/{provider}/metrics", response_model=MonitoringMetricsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="query_metrics",
    error_code_prefix="INTEGRATION_MONITORING",
)
async def query_metrics(
    provider: str,
    request: MetricsQueryRequest,
    api_key: str = Query(..., description="API key"),
    app_key: str | None = Query(None, description="Application key (Datadog)"),
    account_id: str | None = Query(None, description="Account ID (New Relic)"),
) -> Dict[str, Any]:
    """Query metrics from monitoring provider.

    Args:
        provider: Monitoring provider name
        request: Metrics query parameters
        api_key: API key for authentication
        app_key: Application key (Datadog only)
        account_id: Account ID (New Relic only)

    Returns:
        Dict with metric query results

    Raises:
        HTTPException: If provider is invalid or query fails
    """
    try:
        _validate_provider(provider)
        config = _build_config_from_params(provider, api_key, app_key, account_id)
        integration = _get_integration(provider, config)

        params = _build_metrics_params(provider, request)
        result = await integration.execute_action("get_metrics", params)

        return result
    except ValueError:
        raise HTTPException(status_code=400, detail="Internal server error")
    except Exception:
        logger.exception("Failed to query metrics for %s", provider)
        raise HTTPException(status_code=500, detail="Failed to query metrics")


@router.get("/{provider}/alerts", response_model=MonitoringAlertsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_alerts",
    error_code_prefix="INTEGRATION_MONITORING",
)
async def list_alerts(
    provider: str,
    api_key: str = Query(..., description="API key"),
    app_key: str | None = Query(None, description="Application key (Datadog)"),
) -> Dict[str, Any]:
    """List active alerts and monitors.

    Args:
        provider: Monitoring provider name
        api_key: API key for authentication
        app_key: Application key (Datadog only)

    Returns:
        Dict with list of alerts/monitors

    Raises:
        HTTPException: If provider is invalid or query fails
    """
    try:
        _validate_provider(provider)
        config = _build_config_from_params(provider, api_key, app_key, None)
        integration = _get_integration(provider, config)

        if provider == "datadog":
            result = await integration.execute_action("list_monitors", {})
        else:  # new_relic
            result = await integration.execute_action("list_alerts", {})

        return result
    except ValueError:
        raise HTTPException(status_code=400, detail="Internal server error")
    except Exception:
        logger.exception("Failed to list alerts for %s", provider)
        raise HTTPException(status_code=500, detail="Failed to list alerts")


@router.post("/{provider}/events", response_model=MonitoringEventsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_events",
    error_code_prefix="INTEGRATION_MONITORING",
)
async def get_events(
    provider: str,
    request: EventsQueryRequest,
    api_key: str = Query(..., description="API key"),
    app_key: str | None = Query(None, description="Application key (Datadog)"),
) -> Dict[str, Any]:
    """Get recent events from monitoring provider.

    Args:
        provider: Monitoring provider name
        request: Events query parameters
        api_key: API key for authentication
        app_key: Application key (Datadog only)

    Returns:
        Dict with list of events

    Raises:
        HTTPException: If provider is invalid or query fails
    """
    try:
        _validate_provider(provider)

        if provider != "datadog":
            raise HTTPException(
                status_code=400,
                detail="Events endpoint only supported for Datadog",
            )

        config = _build_config_from_params(provider, api_key, app_key, None)
        integration = _get_integration(provider, config)

        params = _build_events_params(request)
        result = await integration.execute_action("get_events", params)

        return result
    except ValueError:
        raise HTTPException(status_code=400, detail="Internal server error")
    except Exception:
        logger.exception("Failed to get events for %s", provider)
        raise HTTPException(status_code=500, detail="Failed to get events")


def _validate_provider(provider: str) -> None:
    """Validate provider is supported.

    Args:
        provider: Provider name to validate

    Raises:
        ValueError: If provider is not supported
    """
    if provider not in ["datadog", "new_relic"]:
        raise ValueError(f"Unsupported provider: {provider}")


def _build_config(provider: str, request: MonitoringConnectionTestRequest) -> IntegrationConfig:
    """Build IntegrationConfig from request.

    Args:
        provider: Provider name
        request: Connection test request

    Returns:
        IntegrationConfig instance
    """
    extra: Dict[str, Any] = {}

    if provider == "datadog" and request.app_key:
        extra["app_key"] = request.app_key
    elif provider == "new_relic" and request.account_id:
        extra["account_id"] = request.account_id

    return IntegrationConfig(
        name=provider,
        provider=provider,
        api_key=request.api_key,
        extra=extra,
    )


def _build_config_from_params(
    provider: str,
    api_key: str,
    app_key: str | None,
    account_id: str | None,
) -> IntegrationConfig:
    """Build IntegrationConfig from query parameters.

    Args:
        provider: Provider name
        api_key: API key
        app_key: Application key (optional)
        account_id: Account ID (optional)

    Returns:
        IntegrationConfig instance
    """
    extra: Dict[str, Any] = {}

    if provider == "datadog" and app_key:
        extra["app_key"] = app_key
    elif provider == "new_relic" and account_id:
        extra["account_id"] = account_id

    return IntegrationConfig(
        name=provider,
        provider=provider,
        api_key=api_key,
        extra=extra,
    )


def _get_integration(provider: str, config: IntegrationConfig) -> DatadogIntegration | NewRelicIntegration:
    """Get integration instance for provider.

    Args:
        provider: Provider name
        config: Integration configuration

    Returns:
        Integration instance

    Raises:
        ValueError: If provider is not supported
    """
    if provider == "datadog":
        return DatadogIntegration(config)
    elif provider == "new_relic":
        return NewRelicIntegration(config)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def _build_metrics_params(provider: str, request: MetricsQueryRequest) -> Dict[str, Any]:
    """Build metrics query parameters.

    Args:
        provider: Provider name
        request: Metrics query request

    Returns:
        Dict with query parameters
    """
    if provider == "datadog":
        to_time = request.to_time or int(datetime.now(tz=timezone.utc).timestamp())
        from_time = request.from_time or int((datetime.now(tz=timezone.utc) - timedelta(hours=1)).timestamp())
        return {"query": request.query, "from_time": from_time, "to_time": to_time}
    else:  # new_relic
        since = request.since or "1 hour ago"
        return {"nrql": request.query, "since": since}


def _build_events_params(request: EventsQueryRequest) -> Dict[str, Any]:
    """Build events query parameters.

    Args:
        request: Events query request

    Returns:
        Dict with query parameters
    """
    end = request.end or int(datetime.now(tz=timezone.utc).timestamp())
    start = request.start or int((datetime.now(tz=timezone.utc) - timedelta(hours=1)).timestamp())
    return {"start": start, "end": end}
