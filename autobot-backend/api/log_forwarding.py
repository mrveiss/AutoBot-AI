# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Log Forwarding API

Provides endpoints to manage log forwarding destinations via the GUI.
Supports multiple destination types: Seq, Elasticsearch, Loki, Syslog (UDP/TCP/TLS), Webhook, File.

Features:
- CRUD operations for log forwarding destinations
- Health checks and connectivity tests
- Global and per-host configuration scope
- Start/stop forwarding service control
- Real-time status and statistics
"""

from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.threshold_constants import TimingConstants

# Add scripts path for log forwarder import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# log_forwarder lives in autobot-infrastructure/shared/scripts/logging/ —
# only available when the infrastructure repo is on PYTHONPATH (#6666).
from autobot_shared.missing_dep import optional_import

_log_forwarder_imports = optional_import(
    "scripts.logging.log_forwarder",
    [
        "DestinationConfig",
        "DestinationScope",
        "DestinationType",
        "LogForwarder",
        "SyslogProtocol",
    ],
)
DestinationConfig = _log_forwarder_imports["DestinationConfig"]  # type: ignore[assignment, misc]
DestinationScope = _log_forwarder_imports["DestinationScope"]  # type: ignore[assignment, misc]
DestinationType = _log_forwarder_imports["DestinationType"]  # type: ignore[assignment, misc]
LogForwarder = _log_forwarder_imports["LogForwarder"]  # type: ignore[assignment, misc]
SyslogProtocol = _log_forwarder_imports["SyslogProtocol"]  # type: ignore[assignment, misc]
from api.schemas_system import (
    LogForwardingDestinationItem,
    LogFwdAutoStartResponse,
    LogFwdCreateUpdateResponse,
    LogFwdDestinationCreate,
    LogFwdDestinationResponse,
    LogFwdDestinationTypesResponse,
    LogFwdDestinationUpdate,
    LogFwdKnownHostsResponse,
    LogFwdMessageResponse,
    LogFwdStatusResponse,
    LogFwdTestAllResponse,
    LogFwdTestResponse,
)

logger = get_logger(__name__)

router = APIRouter(tags=["log-forwarding"])

# Singleton forwarder instance.
# #6794: _MissingDep now no-ops on type subscript so LogForwarder | None
# evaluates safely even when scripts.logging is missing — no forward-ref
# string needed.
_forwarder: LogForwarder | None = None
_forwarder_lock = asyncio.Lock()


async def _get_forwarder() -> LogForwarder:
    """Get or create the log forwarder singleton."""
    global _forwarder
    async with _forwarder_lock:
        if _forwarder is None:
            _forwarder = LogForwarder()
        return _forwarder


# Pydantic models for API


def _build_updated_destination_config(
    name: str,
    existing: DestinationConfig,
    update_dict: dict,
) -> DestinationConfig:
    """Helper for update_destination. Ref: #1088.

    Merges update_dict fields over the existing DestinationConfig and returns
    the new DestinationConfig.  The destination type is always preserved.
    """
    return DestinationConfig(
        name=name,
        type=existing.type,
        enabled=update_dict.get("enabled", existing.enabled),
        url=update_dict.get("url", existing.url),
        api_key=update_dict.get("api_key", existing.api_key),
        username=update_dict.get("username", existing.username),
        password=update_dict.get("password", existing.password),
        index=update_dict.get("index", existing.index),
        file_path=update_dict.get("file_path", existing.file_path),
        min_level=update_dict.get("min_level", existing.min_level),
        batch_size=update_dict.get("batch_size", existing.batch_size),
        batch_timeout=update_dict.get("batch_timeout", existing.batch_timeout),
        retry_count=update_dict.get("retry_count", existing.retry_count),
        retry_delay=update_dict.get("retry_delay", existing.retry_delay),
        scope=DestinationScope(update_dict.get("scope", existing.scope.value)),
        target_hosts=update_dict.get("target_hosts", existing.target_hosts),
        syslog_protocol=SyslogProtocol(update_dict.get("syslog_protocol", existing.syslog_protocol.value)),
        ssl_verify=update_dict.get("ssl_verify", existing.ssl_verify),
        ssl_ca_cert=update_dict.get("ssl_ca_cert", existing.ssl_ca_cert),
        ssl_client_cert=update_dict.get("ssl_client_cert", existing.ssl_client_cert),
        ssl_client_key=update_dict.get("ssl_client_key", existing.ssl_client_key),
    )


def _config_to_destination_config(data: LogFwdDestinationCreate) -> DestinationConfig:
    """Convert API model to DestinationConfig."""
    try:
        dest_type = DestinationType(data.type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid destination type: {data.type}")

    try:
        scope = DestinationScope(data.scope)
    except ValueError:
        scope = DestinationScope.GLOBAL

    try:
        syslog_protocol = SyslogProtocol(data.syslog_protocol)
    except ValueError:
        syslog_protocol = SyslogProtocol.UDP

    return DestinationConfig(
        name=data.name,
        type=dest_type,
        enabled=data.enabled,
        url=data.url,
        api_key=data.api_key,
        username=data.username,
        password=data.password,
        index=data.index,
        file_path=data.file_path,
        min_level=data.min_level,
        batch_size=data.batch_size,
        batch_timeout=data.batch_timeout,
        retry_count=data.retry_count,
        retry_delay=data.retry_delay,
        scope=scope,
        target_hosts=data.target_hosts,
        syslog_protocol=syslog_protocol,
        ssl_verify=data.ssl_verify,
        ssl_ca_cert=data.ssl_ca_cert,
        ssl_client_cert=data.ssl_client_cert,
        ssl_client_key=data.ssl_client_key,
    )


def _destination_to_response(dest) -> LogFwdDestinationResponse:
    """Convert LogDestination to API response."""
    return LogFwdDestinationResponse(
        name=dest.config.name,
        type=dest.config.type.value,
        enabled=dest.config.enabled,
        url=dest.config.url,
        index=dest.config.index,
        file_path=dest.config.file_path,
        min_level=dest.config.min_level,
        batch_size=dest.config.batch_size,
        batch_timeout=dest.config.batch_timeout,
        scope=dest.config.scope.value,
        target_hosts=dest.config.target_hosts,
        syslog_protocol=dest.config.syslog_protocol.value,
        ssl_verify=dest.config.ssl_verify,
        healthy=dest.is_healthy,
        last_error=dest._last_error,
        sent_count=dest._sent_count,
        failed_count=dest._failed_count,
    )


@router.get("/destinations", response_model=List[LogForwardingDestinationItem])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_destinations",
    error_code_prefix="LOG_FORWARDING",
)
async def list_destinations(
    admin_check: bool = Depends(check_admin_permission),
) -> List[Dict[str, Any]]:
    """List all configured log forwarding destinations.

    Issue #744: Requires admin authentication.
    """
    try:
        forwarder = await _get_forwarder()
        destinations = []
        for dest in forwarder.destinations.values():
            destinations.append(
                {
                    **dest.config.to_dict_sanitized(),
                    "healthy": dest.is_healthy,
                    "last_error": dest._last_error,
                    "sent_count": dest._sent_count,
                    "failed_count": dest._failed_count,
                }
            )
        return destinations
    except Exception as e:
        logger.error("Error listing destinations: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/destinations/{name}", response_model=LogForwardingDestinationItem)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_destination",
    error_code_prefix="LOG_FORWARDING",
)
async def get_destination(
    name: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Get a specific destination by name.

    Issue #744: Requires admin authentication.
    """
    try:
        forwarder = await _get_forwarder()
        if name not in forwarder.destinations:
            raise HTTPException(status_code=404, detail=f"Destination not found: {name}")

        dest = forwarder.destinations[name]
        return {
            **dest.config.to_dict_sanitized(),
            "healthy": dest.is_healthy,
            "last_error": dest._last_error,
            "sent_count": dest._sent_count,
            "failed_count": dest._failed_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting destination %s: %s", name, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/destinations", response_model=LogFwdCreateUpdateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_destination_endpoint",
    error_code_prefix="LOG_FORWARDING",
)
async def create_destination_endpoint(
    data: LogFwdDestinationCreate,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Create a new log forwarding destination.

    Issue #744: Requires admin authentication.
    """
    try:
        forwarder = await _get_forwarder()

        # Check if name already exists
        if data.name in forwarder.destinations:
            raise HTTPException(status_code=409, detail=f"Destination already exists: {data.name}")

        config = _config_to_destination_config(data)
        success = forwarder.add_destination(config)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to create destination")

        dest = forwarder.destinations[data.name]
        return {
            "message": f"Destination created: {data.name}",
            "destination": {
                **dest.config.to_dict_sanitized(),
                "healthy": dest.is_healthy,
                "last_error": dest._last_error,
                "sent_count": dest._sent_count,
                "failed_count": dest._failed_count,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating destination: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/destinations/{name}", response_model=LogFwdCreateUpdateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_destination",
    error_code_prefix="LOG_FORWARDING",
)
async def update_destination(
    name: str,
    data: LogFwdDestinationUpdate,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Update an existing destination.

    Issue #744: Requires admin authentication.
    """
    try:
        forwarder = await _get_forwarder()

        if name not in forwarder.destinations:
            raise HTTPException(status_code=404, detail=f"Destination not found: {name}")

        existing = forwarder.destinations[name].config
        update_dict = data.model_dump(exclude_unset=True)

        # Build updated config using extracted helper (Issue #1088)
        new_config = _build_updated_destination_config(name, existing, update_dict)

        success = forwarder.update_destination(name, new_config)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update destination")

        dest = forwarder.destinations[name]
        return {
            "message": f"Destination updated: {name}",
            "destination": {
                **dest.config.to_dict_sanitized(),
                "healthy": dest.is_healthy,
                "last_error": dest._last_error,
                "sent_count": dest._sent_count,
                "failed_count": dest._failed_count,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating destination %s: %s", name, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/destinations/{name}", response_model=LogFwdMessageResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_destination",
    error_code_prefix="LOG_FORWARDING",
)
async def delete_destination(
    name: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """Delete a log forwarding destination.

    Issue #744: Requires admin authentication.
    """
    try:
        forwarder = await _get_forwarder()

        if name not in forwarder.destinations:
            raise HTTPException(status_code=404, detail=f"Destination not found: {name}")

        success = forwarder.remove_destination(name)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete destination")

        return {"message": f"Destination deleted: {name}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting destination %s: %s", name, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/destinations/{name}/test", response_model=LogFwdTestResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_destination",
    error_code_prefix="LOG_FORWARDING",
)
async def test_destination(
    name: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Test connectivity to a destination.

    Issue #744: Requires admin authentication.
    """
    try:
        forwarder = await _get_forwarder()

        if name not in forwarder.destinations:
            raise HTTPException(status_code=404, detail=f"Destination not found: {name}")

        dest = forwarder.destinations[name]

        # Run health check in thread pool to avoid blocking
        healthy = await asyncio.to_thread(dest.health_check)

        return {
            "name": name,
            "healthy": healthy,
            "last_error": dest._last_error,
            "message": ("Connection successful" if healthy else f"Connection failed: {dest._last_error}"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error testing destination %s: %s", name, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/test-all", response_model=LogFwdTestAllResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_all_destinations",
    error_code_prefix="LOG_FORWARDING",
)
async def test_all_destinations(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Test connectivity to all destinations.

    Issue #744: Requires admin authentication.
    """
    try:
        forwarder = await _get_forwarder()
        results = await asyncio.to_thread(forwarder.test_destinations)

        return {
            "results": results,
            "total": len(results),
            "healthy": sum(1 for v in results.values() if v),
            "unhealthy": sum(1 for v in results.values() if not v),
        }
    except Exception as e:
        logger.error("Error testing all destinations: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/status", response_model=LogFwdStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_status",
    error_code_prefix="LOG_FORWARDING",
)
async def get_status(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Get log forwarding service status and statistics.

    Issue #744: Requires admin authentication.
    """
    try:
        forwarder = await _get_forwarder()

        destinations_status = []
        total_sent = 0
        total_failed = 0

        for dest in forwarder.destinations.values():
            destinations_status.append(
                {
                    "name": dest.config.name,
                    "type": dest.config.type.value,
                    "enabled": dest.config.enabled,
                    "healthy": dest.is_healthy,
                    "last_error": dest._last_error,
                    "sent_count": dest._sent_count,
                    "failed_count": dest._failed_count,
                    "scope": dest.config.scope.value,
                }
            )
            total_sent += dest._sent_count
            total_failed += dest._failed_count

        return {
            "running": forwarder.running,
            "hostname": forwarder.hostname,
            "queue_size": forwarder.log_queue.qsize(),
            "destinations": destinations_status,
            "total_destinations": len(forwarder.destinations),
            "enabled_destinations": sum(1 for d in forwarder.destinations.values() if d.config.enabled),
            "healthy_destinations": sum(1 for d in forwarder.destinations.values() if d.is_healthy),
            "total_sent": total_sent,
            "total_failed": total_failed,
        }
    except Exception as e:
        logger.error("Error getting status: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/start", response_model=LogFwdMessageResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_forwarding",
    error_code_prefix="LOG_FORWARDING",
)
async def start_forwarding(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """Start the log forwarding service.

    Issue #744: Requires admin authentication.
    """
    try:
        forwarder = await _get_forwarder()

        if forwarder.running:
            return {"message": "Log forwarding service is already running"}

        # Start in background thread
        import threading

        thread = threading.Thread(target=forwarder.start, daemon=True)
        thread.start()

        # Wait briefly for startup
        await asyncio.sleep(TimingConstants.SHORT_DELAY)

        return {"message": "Log forwarding service started"}
    except Exception as e:
        logger.error("Error starting log forwarding: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/stop", response_model=LogFwdMessageResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_forwarding",
    error_code_prefix="LOG_FORWARDING",
)
async def stop_forwarding(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """Stop the log forwarding service.

    Issue #744: Requires admin authentication.
    """
    try:
        forwarder = await _get_forwarder()

        if not forwarder.running:
            return {"message": "Log forwarding service is not running"}

        forwarder.stop()

        return {"message": "Log forwarding service stopped"}
    except Exception as e:
        logger.error("Error stopping log forwarding: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


def _get_destination_type_list() -> list:
    """Helper for get_destination_types. Ref: #1088.

    Returns the static list of supported destination type descriptors.
    """
    return [
        {
            "value": "seq",
            "label": "Seq",
            "description": "Datalust Seq structured logging server",
            "requires": ["url"],
            "optional": ["api_key"],
        },
        {
            "value": "elasticsearch",
            "label": "Elasticsearch",
            "description": "Elasticsearch cluster for log indexing",
            "requires": ["url"],
            "optional": ["username", "password", "index"],
        },
        {
            "value": "loki",
            "label": "Grafana Loki",
            "description": "Grafana Loki for log aggregation",
            "requires": ["url"],
            "optional": ["username", "password"],
        },
        {
            "value": "syslog",
            "label": "Syslog",
            "description": "Standard syslog server (UDP/TCP/TLS)",
            "requires": ["url"],
            "optional": [
                "syslog_protocol",
                "ssl_verify",
                "ssl_ca_cert",
                "ssl_client_cert",
                "ssl_client_key",
            ],
            "protocols": ["udp", "tcp", "tcp_tls"],
        },
        {
            "value": "webhook",
            "label": "Webhook",
            "description": "Custom HTTP webhook endpoint",
            "requires": ["url"],
            "optional": ["api_key"],
        },
        {
            "value": "file",
            "label": "File",
            "description": "Local file logging",
            "requires": ["file_path"],
            "optional": [],
        },
    ]


def _get_syslog_protocol_list() -> list:
    """Helper for get_destination_types. Ref: #1088.

    Returns the static list of supported syslog protocol descriptors.
    """
    return [
        {"value": "udp", "label": "UDP", "description": "UDP (unreliable, fast)"},
        {"value": "tcp", "label": "TCP", "description": "TCP (reliable)"},
        {
            "value": "tcp_tls",
            "label": "TCP + TLS",
            "description": "TCP with SSL/TLS encryption",
        },
    ]


@router.get("/destination-types", response_model=LogFwdDestinationTypesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_destination_types",
    error_code_prefix="LOG_FORWARDING",
)
async def get_destination_types(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Get available destination types and their configuration options.

    Issue #744: Requires admin authentication.
    Issue #1088: Static data extracted to _get_destination_type_list and
    _get_syslog_protocol_list helpers.
    """
    return {
        "types": _get_destination_type_list(),
        "scopes": [
            {"value": "global", "label": "Global", "description": "Apply to all hosts"},
            {
                "value": "per_host",
                "label": "Per Host",
                "description": "Apply only to specified hosts",
            },
        ],
        "log_levels": ["Debug", "Information", "Warning", "Error", "Fatal"],
        "syslog_protocols": _get_syslog_protocol_list(),
    }


@router.get("/known-hosts", response_model=LogFwdKnownHostsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_known_hosts",
    error_code_prefix="LOG_FORWARDING",
)
async def get_known_hosts(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Get list of known AutoBot hosts for per-host configuration.

    Issue #744: Requires admin authentication.
    """
    # Return the known AutoBot infrastructure hosts from SSOT config
    return {
        "hosts": [
            {
                "hostname": "autobot-main",
                "ip": config.vm.main,
                "description": "Main Machine (Backend API)",
            },
            {
                "hostname": "autobot-frontend",
                "ip": config.vm.frontend,
                "description": "Frontend VM",
            },
            {
                "hostname": "autobot-npu-worker",
                "ip": config.vm.npu,
                "description": "NPU Worker VM",
            },
            {
                "hostname": "autobot-redis",
                "ip": config.vm.redis,
                "description": "Redis VM",
            },
            {
                "hostname": "autobot-ai-stack",
                "ip": config.vm.aistack,
                "description": "AI Stack VM",
            },
            {
                "hostname": "autobot-browser",
                "ip": config.vm.browser,
                "description": "Browser VM",
            },
        ],
        "current_hostname": socket.gethostname(),
    }


# Issue #553: Auto-start configuration
@router.get("/auto-start", response_model=LogFwdAutoStartResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_auto_start",
    error_code_prefix="LOG_FORWARDING",
)
async def get_auto_start(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Get auto-start configuration.

    Issue #744: Requires admin authentication.
    """
    forwarder = await _get_forwarder()
    return {
        "auto_start": forwarder.auto_start,
        "message": ("Auto-start is enabled" if forwarder.auto_start else "Auto-start is disabled"),
    }


@router.put("/auto-start", response_model=LogFwdAutoStartResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="set_auto_start",
    error_code_prefix="LOG_FORWARDING",
)
async def set_auto_start(
    enabled: bool = Query(..., description="Enable or disable auto-start"),
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Set auto-start configuration.

    Issue #744: Requires admin authentication.
    """
    forwarder = await _get_forwarder()
    forwarder.auto_start = enabled
    forwarder.save_config()
    return {
        "auto_start": forwarder.auto_start,
        "message": f"Auto-start {'enabled' if enabled else 'disabled'}",
    }
