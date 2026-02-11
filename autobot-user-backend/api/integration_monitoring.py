# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

"""Monitoring integration API endpoints.

Provides REST API for interacting with monitoring platforms
like Datadog and New Relic.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, validator

from backend.integrations.base import IntegrationConfig
from backend.integrations.monitoring_integration import (
    DatadogIntegration,
    NewRelicIntegration,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["integrations-monitoring"])


class ConnectionTestRequest(BaseModel):
    """Request model for testing monitoring connection."""

    provider: str = Field(..., description="Monitoring provider")
    api_key: str = Field(..., description="API key")
    app_key: Optional[str] = Field(None, description="Application key (Datadog only)")
    account_id: Optional[str] = Field(None, description="Account ID (New Relic only)")

    @validator("provider")
    def validate_provider(cls, v: str) -> str:
        """Validate provider is supported."""
        if v not in ["datadog", "new_relic"]:
            raise ValueError("Provider must be 'datadog' or 'new_relic'")
        return v


class MetricsQueryRequest(BaseModel):
    """Request model for querying metrics."""

    query: str = Field(..., description="Metric query")
    from_time: Optional[int] = Field(None, description="Start time (unix timestamp)")
    to_time: Optional[int] = Field(None, description="End time (unix timestamp)")
    since: Optional[str] = Field(None, description="Relative time (e.g., '1 hour ago')")

    @validator("from_time")
    def validate_from_time(cls, v: Optional[int]) -> Optional[int]:
        """Ensure from_time is not in future."""
        if v and v > int(datetime.now().timestamp()):
            raise ValueError("from_time cannot be in the future")
        return v

    @validator("to_time")
    def validate_to_time(
        cls, v: Optional[int], values: Dict[str, Any]
    ) -> Optional[int]:
        """Ensure to_time is after from_time."""
        if v and "from_time" in values and values["from_time"]:
            if v < values["from_time"]:
                raise ValueError("to_time must be after from_time")
            time_range = v - values["from_time"]
            if time_range > 86400:  # 24 hours
                raise ValueError("Time range cannot exceed 24 hours")
        return v


class EventsQueryRequest(BaseModel):
    """Request model for querying events."""

    start: Optional[int] = Field(None, description="Start time (unix timestamp)")
    end: Optional[int] = Field(None, description="End time (unix timestamp)")

    @validator("end")
    def validate_time_range(
        cls, v: Optional[int], values: Dict[str, Any]
    ) -> Optional[int]:
        """Validate time range does not exceed 24 hours."""
        if v and "start" in values and values["start"]:
            time_range = v - values["start"]
            if time_range > 86400:
                raise ValueError("Time range cannot exceed 24 hours")
        return v


class MonitorCreateRequest(BaseModel):
    """Request model for creating a monitor."""

    type: str = Field(..., description="Monitor type")
    query: str = Field(..., description="Monitor query")
    name: str = Field(..., description="Monitor name")
    message: str = Field(..., description="Notification message")


@router.post("/test-connection")
async def test_connection(request: ConnectionTestRequest) -> Dict[str, Any]:
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
    except Exception as e:
        logger.exception("Connection test failed for %s", request.provider)
        raise HTTPException(status_code=500, detail=f"Connection test failed: {str(e)}")


@router.get("/providers")
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


@router.get("/{provider}/hosts")
async def list_hosts(
    provider: str,
    api_key: str = Query(..., description="API key"),
    app_key: Optional[str] = Query(None, description="Application key (Datadog)"),
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to list hosts for %s", provider)
        raise HTTPException(status_code=500, detail=f"Failed to list hosts: {str(e)}")


@router.post("/{provider}/metrics")
async def query_metrics(
    provider: str,
    request: MetricsQueryRequest,
    api_key: str = Query(..., description="API key"),
    app_key: Optional[str] = Query(None, description="Application key (Datadog)"),
    account_id: Optional[str] = Query(None, description="Account ID (New Relic)"),
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to query metrics for %s", provider)
        raise HTTPException(
            status_code=500, detail=f"Failed to query metrics: {str(e)}"
        )


@router.get("/{provider}/alerts")
async def list_alerts(
    provider: str,
    api_key: str = Query(..., description="API key"),
    app_key: Optional[str] = Query(None, description="Application key (Datadog)"),
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to list alerts for %s", provider)
        raise HTTPException(status_code=500, detail=f"Failed to list alerts: {str(e)}")


@router.post("/{provider}/events")
async def get_events(
    provider: str,
    request: EventsQueryRequest,
    api_key: str = Query(..., description="API key"),
    app_key: Optional[str] = Query(None, description="Application key (Datadog)"),
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to get events for %s", provider)
        raise HTTPException(status_code=500, detail=f"Failed to get events: {str(e)}")


def _validate_provider(provider: str) -> None:
    """Validate provider is supported.

    Args:
        provider: Provider name to validate

    Raises:
        ValueError: If provider is not supported
    """
    if provider not in ["datadog", "new_relic"]:
        raise ValueError(f"Unsupported provider: {provider}")


def _build_config(provider: str, request: ConnectionTestRequest) -> IntegrationConfig:
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
    app_key: Optional[str],
    account_id: Optional[str],
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


def _get_integration(
    provider: str, config: IntegrationConfig
) -> DatadogIntegration | NewRelicIntegration:
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


def _build_metrics_params(
    provider: str, request: MetricsQueryRequest
) -> Dict[str, Any]:
    """Build metrics query parameters.

    Args:
        provider: Provider name
        request: Metrics query request

    Returns:
        Dict with query parameters
    """
    if provider == "datadog":
        to_time = request.to_time or int(datetime.now().timestamp())
        from_time = request.from_time or int(
            (datetime.now() - timedelta(hours=1)).timestamp()
        )
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
    end = request.end or int(datetime.now().timestamp())
    start = request.start or int((datetime.now() - timedelta(hours=1)).timestamp())
    return {"start": start, "end": end}
