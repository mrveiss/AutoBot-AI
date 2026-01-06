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

import asyncio
import json
import logging
import socket
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.utils.error_boundaries import ErrorCategory, with_error_handling

# Add scripts path for log forwarder import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.logging.log_forwarder import (
    DestinationConfig,
    DestinationScope,
    DestinationType,
    LogForwarder,
    SyslogProtocol,
    create_destination,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["log-forwarding"])

# Singleton forwarder instance
_forwarder: Optional[LogForwarder] = None
_forwarder_lock = asyncio.Lock()


async def _get_forwarder() -> LogForwarder:
    """Get or create the log forwarder singleton."""
    global _forwarder
    async with _forwarder_lock:
        if _forwarder is None:
            _forwarder = LogForwarder()
        return _forwarder


# Pydantic models for API
class DestinationCreate(BaseModel):
    """Model for creating a new destination."""
    name: str = Field(..., description="Unique name for the destination")
    type: str = Field(..., description="Destination type: seq, elasticsearch, loki, syslog, webhook, file")
    enabled: bool = Field(True, description="Whether the destination is enabled")
    url: Optional[str] = Field(None, description="URL/host for the destination")
    api_key: Optional[str] = Field(None, description="API key for authentication")
    username: Optional[str] = Field(None, description="Username for authentication")
    password: Optional[str] = Field(None, description="Password for authentication")
    index: Optional[str] = Field("autobot-logs", description="Index name (Elasticsearch)")
    file_path: Optional[str] = Field(None, description="File path (file destination)")
    min_level: str = Field("Information", description="Minimum log level to forward")
    batch_size: int = Field(10, ge=1, le=1000, description="Batch size for sending")
    batch_timeout: float = Field(5.0, ge=0.1, le=60.0, description="Batch timeout in seconds")
    retry_count: int = Field(3, ge=0, le=10, description="Number of retries on failure")
    retry_delay: float = Field(1.0, ge=0.1, le=30.0, description="Delay between retries")
    # Scope configuration
    scope: str = Field("global", description="Scope: global (all hosts) or per_host")
    target_hosts: List[str] = Field(default_factory=list, description="Target hosts for per_host scope")
    # Syslog-specific options
    syslog_protocol: str = Field("udp", description="Syslog protocol: udp, tcp, tcp_tls")
    ssl_verify: bool = Field(True, description="Verify SSL certificates for TLS")
    ssl_ca_cert: Optional[str] = Field(None, description="Path to CA certificate")
    ssl_client_cert: Optional[str] = Field(None, description="Path to client certificate")
    ssl_client_key: Optional[str] = Field(None, description="Path to client key")


class DestinationUpdate(BaseModel):
    """Model for updating an existing destination."""
    enabled: Optional[bool] = None
    url: Optional[str] = None
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    index: Optional[str] = None
    file_path: Optional[str] = None
    min_level: Optional[str] = None
    batch_size: Optional[int] = None
    batch_timeout: Optional[float] = None
    retry_count: Optional[int] = None
    retry_delay: Optional[float] = None
    scope: Optional[str] = None
    target_hosts: Optional[List[str]] = None
    syslog_protocol: Optional[str] = None
    ssl_verify: Optional[bool] = None
    ssl_ca_cert: Optional[str] = None
    ssl_client_cert: Optional[str] = None
    ssl_client_key: Optional[str] = None


class DestinationResponse(BaseModel):
    """Response model for a destination."""
    name: str
    type: str
    enabled: bool
    url: Optional[str]
    index: Optional[str]
    file_path: Optional[str]
    min_level: str
    batch_size: int
    batch_timeout: float
    scope: str
    target_hosts: List[str]
    syslog_protocol: str
    ssl_verify: bool
    # Status fields
    healthy: bool
    last_error: Optional[str]
    sent_count: int
    failed_count: int


def _config_to_destination_config(data: DestinationCreate) -> DestinationConfig:
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


def _destination_to_response(dest) -> DestinationResponse:
    """Convert LogDestination to API response."""
    return DestinationResponse(
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_destinations",
    error_code_prefix="LOGFWD",
)
@router.get("/destinations")
async def list_destinations() -> List[Dict[str, Any]]:
    """List all configured log forwarding destinations."""
    try:
        forwarder = await _get_forwarder()
        destinations = []
        for dest in forwarder.destinations.values():
            destinations.append({
                **dest.config.to_dict_sanitized(),
                "healthy": dest.is_healthy,
                "last_error": dest._last_error,
                "sent_count": dest._sent_count,
                "failed_count": dest._failed_count,
            })
        return destinations
    except Exception as e:
        logger.error("Error listing destinations: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_destination",
    error_code_prefix="LOGFWD",
)
@router.get("/destinations/{name}")
async def get_destination(name: str) -> Dict[str, Any]:
    """Get a specific destination by name."""
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
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_destination",
    error_code_prefix="LOGFWD",
)
@router.post("/destinations")
async def create_destination_endpoint(data: DestinationCreate) -> Dict[str, Any]:
    """Create a new log forwarding destination."""
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
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating destination: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_destination",
    error_code_prefix="LOGFWD",
)
@router.put("/destinations/{name}")
async def update_destination(name: str, data: DestinationUpdate) -> Dict[str, Any]:
    """Update an existing destination."""
    try:
        forwarder = await _get_forwarder()

        if name not in forwarder.destinations:
            raise HTTPException(status_code=404, detail=f"Destination not found: {name}")

        # Get existing config and update fields
        existing = forwarder.destinations[name].config
        update_dict = data.model_dump(exclude_unset=True)

        # Create new config with updated fields
        new_config = DestinationConfig(
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
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating destination %s: %s", name, e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_destination",
    error_code_prefix="LOGFWD",
)
@router.delete("/destinations/{name}")
async def delete_destination(name: str) -> Dict[str, str]:
    """Delete a log forwarding destination."""
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
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_destination",
    error_code_prefix="LOGFWD",
)
@router.post("/destinations/{name}/test")
async def test_destination(name: str) -> Dict[str, Any]:
    """Test connectivity to a destination."""
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
            "message": "Connection successful" if healthy else f"Connection failed: {dest._last_error}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error testing destination %s: %s", name, e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_all_destinations",
    error_code_prefix="LOGFWD",
)
@router.post("/test-all")
async def test_all_destinations() -> Dict[str, Any]:
    """Test connectivity to all destinations."""
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
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_status",
    error_code_prefix="LOGFWD",
)
@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """Get log forwarding service status and statistics."""
    try:
        forwarder = await _get_forwarder()

        destinations_status = []
        total_sent = 0
        total_failed = 0

        for dest in forwarder.destinations.values():
            destinations_status.append({
                "name": dest.config.name,
                "type": dest.config.type.value,
                "enabled": dest.config.enabled,
                "healthy": dest.is_healthy,
                "last_error": dest._last_error,
                "sent_count": dest._sent_count,
                "failed_count": dest._failed_count,
                "scope": dest.config.scope.value,
            })
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
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_forwarding",
    error_code_prefix="LOGFWD",
)
@router.post("/start")
async def start_forwarding() -> Dict[str, str]:
    """Start the log forwarding service."""
    try:
        forwarder = await _get_forwarder()

        if forwarder.running:
            return {"message": "Log forwarding service is already running"}

        # Start in background thread
        import threading
        thread = threading.Thread(target=forwarder.start, daemon=True)
        thread.start()

        # Wait briefly for startup
        await asyncio.sleep(0.5)

        return {"message": "Log forwarding service started"}
    except Exception as e:
        logger.error("Error starting log forwarding: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_forwarding",
    error_code_prefix="LOGFWD",
)
@router.post("/stop")
async def stop_forwarding() -> Dict[str, str]:
    """Stop the log forwarding service."""
    try:
        forwarder = await _get_forwarder()

        if not forwarder.running:
            return {"message": "Log forwarding service is not running"}

        forwarder.stop()

        return {"message": "Log forwarding service stopped"}
    except Exception as e:
        logger.error("Error stopping log forwarding: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_destination_types",
    error_code_prefix="LOGFWD",
)
@router.get("/destination-types")
async def get_destination_types() -> Dict[str, Any]:
    """Get available destination types and their configuration options."""
    return {
        "types": [
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
                "optional": ["syslog_protocol", "ssl_verify", "ssl_ca_cert", "ssl_client_cert", "ssl_client_key"],
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
        ],
        "scopes": [
            {"value": "global", "label": "Global", "description": "Apply to all hosts"},
            {"value": "per_host", "label": "Per Host", "description": "Apply only to specified hosts"},
        ],
        "log_levels": ["Debug", "Information", "Warning", "Error", "Fatal"],
        "syslog_protocols": [
            {"value": "udp", "label": "UDP", "description": "UDP (unreliable, fast)"},
            {"value": "tcp", "label": "TCP", "description": "TCP (reliable)"},
            {"value": "tcp_tls", "label": "TCP + TLS", "description": "TCP with SSL/TLS encryption"},
        ],
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_known_hosts",
    error_code_prefix="LOGFWD",
)
@router.get("/known-hosts")
async def get_known_hosts() -> Dict[str, Any]:
    """Get list of known AutoBot hosts for per-host configuration."""
    # Return the known AutoBot infrastructure hosts
    return {
        "hosts": [
            {"hostname": "autobot-main", "ip": "172.16.168.20", "description": "Main Machine (Backend API)"},
            {"hostname": "autobot-frontend", "ip": "172.16.168.21", "description": "Frontend VM"},
            {"hostname": "autobot-npu-worker", "ip": "172.16.168.22", "description": "NPU Worker VM"},
            {"hostname": "autobot-redis", "ip": "172.16.168.23", "description": "Redis VM"},
            {"hostname": "autobot-ai-stack", "ip": "172.16.168.24", "description": "AI Stack VM"},
            {"hostname": "autobot-browser", "ip": "172.16.168.25", "description": "Browser VM"},
        ],
        "current_hostname": socket.gethostname(),
    }
