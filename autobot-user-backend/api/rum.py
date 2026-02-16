# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RUM (Real User Monitoring) API endpoints for logging frontend events.
Provides comprehensive logging of user interactions, errors, and performance metrics.

Issue #476: Added /metrics endpoint for Prometheus integration.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.type_defs.common import Metadata
from backend.monitoring.prometheus_metrics import get_metrics_manager
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)

# RUM configuration storage
rum_config = {
    "enabled": False,
    "error_tracking": True,
    "performance_monitoring": True,
    "interaction_tracking": False,
    "session_recording": False,
    "sample_rate": 100,
    "max_events_per_session": 1000,
    "debug_mode": False,
    "log_to_backend": True,
    "log_level": "info",
}

# Lock for thread-safe access to RUM state
_rum_lock = asyncio.Lock()

# Issue #380: Module-level frozenset for error event types
_ERROR_EVENT_TYPES = frozenset({"error", "promise_rejection"})

# In-memory storage for RUM events (in production, this would use Redis or database)
rum_events = []
rum_sessions = {}


def _format_error_log(session_id: str, url: str, data: Metadata) -> str:
    """Format error event log message (Issue #315: extracted)."""
    return (
        f"SESSION={session_id} URL={url} ERROR: {data.get('message', 'Unknown error')} "
        f"FILE={data.get('filename', 'unknown')} LINE={data.get('lineno', 0)} "
        f"CONTEXT={data.get('context', 'global')}"
    )


def _format_promise_rejection_log(session_id: str, url: str, data: Metadata) -> str:
    """Format promise rejection log message (Issue #315: extracted)."""
    return f"SESSION={session_id} URL={url} PROMISE_REJECTION: {data.get('reason', 'Unknown reason')}"


def _format_performance_log(session_id: str, url: str, data: Metadata) -> str:
    """Format performance event log message (Issue #315: extracted)."""
    metric_type = data.get("metric_type", "unknown")
    if metric_type == "api_call":
        return (
            f"SESSION={session_id} API_CALL: {data.get('method', 'GET')} {data.get('url', 'unknown')} "
            f"DURATION={data.get('duration', 0):.2f}ms STATUS={data.get('status', 'unknown')}"
        )
    return f"SESSION={session_id} PERFORMANCE: {metric_type} {data}"


def _format_interaction_log(session_id: str, url: str, data: Metadata) -> str:
    """Format interaction event log message (Issue #315: extracted)."""
    coords = data.get("coordinates", {})
    return (
        f"SESSION={session_id} INTERACTION: {data.get('element', 'unknown')} "
        f"ID={data.get('id', 'none')} CLASS={data.get('className', 'none')} "
        f"POS=({coords.get('x', 0)},{coords.get('y', 0)})"
    )


def _format_form_submission_log(session_id: str, url: str, data: Metadata) -> str:
    """Format form submission log message (Issue #315: extracted)."""
    return (
        f"SESSION={session_id} FORM_SUBMIT: ACTION={data.get('action', 'none')} "
        f"METHOD={data.get('method', 'GET')} FIELDS={data.get('fieldCount', 0)}"
    )


# Dictionary dispatch for log formatters (Issue #315: reduces nesting)
_RUM_LOG_FORMATTERS = {
    "error": _format_error_log,
    "promise_rejection": _format_promise_rejection_log,
    "performance": _format_performance_log,
    "interaction": _format_interaction_log,
    "form_submission": _format_form_submission_log,
}


def _log_rum_event_by_type(
    event_type: str, log_message: str, interaction_tracking: bool, rum_logger
) -> None:
    """Log RUM event using appropriate log level (Issue #315: extracted).

    Args:
        event_type: Type of RUM event
        log_message: Formatted log message
        interaction_tracking: Whether interaction tracking is enabled
        rum_logger: Logger instance to use
    """
    if event_type in _ERROR_EVENT_TYPES:
        rum_logger.error(log_message)
        return

    if event_type == "performance":
        rum_logger.info(log_message)
        return

    if event_type == "interaction":
        if interaction_tracking:
            rum_logger.debug(log_message)
        return

    rum_logger.info(log_message)


class RumEvent(BaseModel):
    type: str
    timestamp: str
    sessionId: str
    url: str
    userAgent: str
    data: Metadata = {}


class RumConfig(BaseModel):
    enabled: bool = False
    error_tracking: bool = True
    performance_monitoring: bool = True
    interaction_tracking: bool = False
    session_recording: bool = False
    sample_rate: int = 100
    max_events_per_session: int = 1000
    debug_mode: bool = False
    log_to_backend: bool = True
    log_level: str = "info"


# Issue #476: RUM Metrics models for Prometheus integration
class PageMetrics(BaseModel):
    """Page performance metrics from frontend."""

    page: str
    load_time_seconds: Optional[float] = None
    fcp_seconds: Optional[float] = None  # First Contentful Paint
    lcp_seconds: Optional[float] = None  # Largest Contentful Paint
    tti_seconds: Optional[float] = None  # Time to Interactive
    dom_loaded_seconds: Optional[float] = None


class ApiCallMetric(BaseModel):
    """Frontend API call metric."""

    endpoint: str
    method: str
    status: str  # success, error, timeout
    latency_seconds: float
    is_slow: bool = False
    is_timeout: bool = False
    error_type: Optional[str] = None  # network, http, timeout


class JsErrorMetric(BaseModel):
    """JavaScript error metric."""

    error_type: str  # syntax, reference, type, etc.
    page: str
    is_rejection: bool = False  # True for unhandled Promise rejections
    component: Optional[str] = None  # Vue component name if applicable


class UserActionMetric(BaseModel):
    """User action/interaction metric."""

    action_type: str  # click, submit, navigation, etc.
    page: str
    form_name: Optional[str] = None
    form_status: Optional[str] = None  # success, validation_error, server_error


class SessionMetric(BaseModel):
    """Session metric."""

    event: str  # start, end
    duration_seconds: Optional[float] = None


class WebSocketMetric(BaseModel):
    """WebSocket event metric from frontend."""

    event: str  # connect, disconnect, error, reconnect
    direction: Optional[str] = None  # sent, received
    event_type: Optional[str] = None  # message type


class ResourceMetric(BaseModel):
    """Resource load metric."""

    resource_type: str  # script, stylesheet, image, font
    load_time_seconds: float
    is_slow: bool = False


class CriticalIssueMetric(BaseModel):
    """Critical issue from frontend."""

    issue_type: str  # api_timeout, error, crash


class RumMetrics(BaseModel):
    """
    Batch of RUM metrics from frontend.
    Issue #476: Used for Prometheus metrics export.
    """

    session_id: str
    timestamp: str
    page_metrics: Optional[PageMetrics] = None
    api_calls: Optional[List[ApiCallMetric]] = None
    js_errors: Optional[List[JsErrorMetric]] = None
    user_actions: Optional[List[UserActionMetric]] = None
    session: Optional[SessionMetric] = None
    websocket_events: Optional[List[WebSocketMetric]] = None
    resources: Optional[List[ResourceMetric]] = None
    critical_issues: Optional[List[CriticalIssueMetric]] = None


def setup_rum_logger():
    """Set up dedicated RUM logger using centralized path configuration"""
    rum_logger = logging.getLogger("rum")
    rum_logger.setLevel(getattr(logging, rum_config["log_level"].upper(), logging.INFO))

    # Use centralized path management
    from backend.utils.paths_manager import ensure_log_directory, get_rum_log_path

    # Ensure logs directory exists
    ensure_log_directory()

    # Create file handler for RUM logs using centralized path
    rum_log_path = get_rum_log_path()
    handler = logging.FileHandler(rum_log_path)
    formatter = logging.Formatter(
        "%(asctime)s - RUM - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)

    # Clear existing handlers and add our handler
    rum_logger.handlers.clear()
    rum_logger.addHandler(handler)

    return rum_logger


# Initialize RUM logger
rum_logger = setup_rum_logger()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="configure_rum",
    error_code_prefix="RUM",
)
@router.post("/config")
async def configure_rum(config: RumConfig):
    """Configure RUM monitoring settings"""
    try:
        async with _rum_lock:
            rum_config.update(config.dict())

            # Reinitialize logger with new settings
            global rum_logger
            rum_logger = setup_rum_logger()

            config_enabled = rum_config["enabled"]
            config_copy = dict(rum_config)

        if config_enabled:
            rum_logger.info("RUM monitoring enabled with config: %s", config_copy)
        else:
            rum_logger.info("RUM monitoring disabled")

        logger.info("RUM configuration updated: enabled=%s", config_enabled)

        return {
            "status": "success",
            "message": "RUM configuration updated",
            "config": config_copy,
        }

    except Exception as e:
        logger.error("Error configuring RUM: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error configuring RUM: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="log_rum_event",
    error_code_prefix="RUM",
)
@router.post("/event")
async def log_rum_event(event: RumEvent):
    """Log a RUM event from the frontend"""
    try:
        async with _rum_lock:
            if not rum_config["enabled"]:
                return {"status": "disabled", "message": "RUM monitoring is disabled"}

            # Convert event to dictionary for processing
            event_data = event.dict()
            event_data["server_timestamp"] = datetime.now().isoformat()

            # Store event in memory (in production, this would go to Redis/DB)
            rum_events.append(event_data)

            # Update session tracking
            session_id = event.sessionId
            if session_id not in rum_sessions:
                rum_sessions[session_id] = {
                    "start_time": event_data["server_timestamp"],
                    "event_count": 0,
                    "last_activity": event_data["server_timestamp"],
                    "user_agent": event.userAgent,
                    "initial_url": event.url,
                }

            rum_sessions[session_id]["event_count"] += 1
            rum_sessions[session_id]["last_activity"] = event_data["server_timestamp"]
            session_event_count = rum_sessions[session_id]["event_count"]
            interaction_tracking = rum_config["interaction_tracking"]

            # Keep only last 10000 events in memory to prevent memory leaks
            if len(rum_events) > 10000:
                # Use slice assignment to modify global list in-place
                rum_events[:] = rum_events[-5000:]  # Keep last 5000 events

        # Log to dedicated RUM log file based on event type (outside lock)
        log_message = format_rum_log_message(event_data)
        _log_rum_event_by_type(
            event.type, log_message, interaction_tracking, rum_logger
        )

        return {
            "status": "success",
            "message": "Event logged",
            "session_event_count": session_event_count,
        }

    except Exception as e:
        logger.error("Error logging RUM event: %s", str(e))
        # Don't raise HTTP exception for RUM logging failures to avoid disrupting user experience
        return {"status": "error", "message": f"Failed to log RUM event: {str(e)}"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="disable_rum",
    error_code_prefix="RUM",
)
@router.post("/disable")
async def disable_rum():
    """Disable RUM monitoring"""
    try:
        async with _rum_lock:
            rum_config["enabled"] = False

        rum_logger.info("RUM monitoring disabled via API")
        logger.info("RUM monitoring disabled")

        return {"status": "success", "message": "RUM monitoring disabled"}

    except Exception as e:
        logger.error("Error disabling RUM: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error disabling RUM: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_rum_data",
    error_code_prefix="RUM",
)
@router.post("/clear")
async def clear_rum_data():
    """Clear all RUM data"""
    try:
        async with _rum_lock:
            events_cleared = len(rum_events)
            sessions_cleared = len(rum_sessions)

            # Use .clear() to modify globals in-place
            rum_events.clear()
            rum_sessions.clear()

        rum_logger.info(
            f"RUM data cleared: {events_cleared} events, {sessions_cleared} sessions"
        )

        return {
            "status": "success",
            "message": "RUM data cleared",
            "events_cleared": events_cleared,
            "sessions_cleared": sessions_cleared,
        }

    except Exception as e:
        logger.error("Error clearing RUM data: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error clearing RUM data: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_rum_data",
    error_code_prefix="RUM",
)
@router.get("/export")
async def export_rum_data():
    """Export RUM data for analysis"""

    try:
        async with _rum_lock:
            # Create copies of data under lock to prevent race conditions
            config_copy = dict(rum_config)
            sessions_copy = dict(rum_sessions)
            events_copy = list(rum_events[-1000:])  # Export last 1000 events
            total_events = len(rum_events)
            total_sessions = len(rum_sessions)

            # Calculate event type distribution
            event_types = {}
            for event in rum_events:
                event_type = event.get("type", "unknown")
                event_types[event_type] = event_types.get(event_type, 0) + 1

        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "config": config_copy,
            "sessions": sessions_copy,
            "events": events_copy,
            "summary": {
                "total_events": total_events,
                "total_sessions": total_sessions,
                "event_types": event_types,
            },
        }

        rum_logger.info("RUM data exported")

        return {"status": "success", "data": export_data}

    except Exception as e:
        logger.error("Error exporting RUM data: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error exporting RUM data: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_rum_status",
    error_code_prefix="RUM",
)
@router.get("/status")
async def get_rum_status():
    """Get current RUM status and statistics"""

    try:
        async with _rum_lock:
            # Calculate session statistics under lock
            active_sessions = 0
            total_events_today = 0
            today = datetime.now().date()

            for session_data in rum_sessions.values():
                last_activity = datetime.fromisoformat(
                    session_data["last_activity"].replace("Z", "+00:00")
                )
                if (datetime.now() - last_activity.replace(tzinfo=None)) < timedelta(
                    minutes=30
                ):
                    active_sessions += 1

                if last_activity.date() == today:
                    total_events_today += session_data["event_count"]

            status = {
                "enabled": rum_config["enabled"],
                "config": dict(rum_config),
                "statistics": {
                    "total_events": len(rum_events),
                    "total_sessions": len(rum_sessions),
                    "active_sessions": active_sessions,
                    "events_today": total_events_today,
                },
            }

        return {"status": "success", "rum_status": status}

    except Exception as e:
        logger.error("Error getting RUM status: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error getting RUM status: {str(e)}"
        )


def format_rum_log_message(event_data: Metadata) -> str:
    """Format RUM event data into a readable log message.

    Uses dictionary dispatch pattern to reduce nesting (Issue #315).
    """
    event_type = event_data.get("type", "unknown")
    session_id = event_data.get("sessionId", "unknown")
    url = event_data.get("url", "unknown")
    data = event_data.get("data", {})

    # Use dictionary dispatch for known event types (Issue #315)
    formatter = _RUM_LOG_FORMATTERS.get(event_type)
    if formatter:
        return formatter(session_id, url, data)

    # Default format for unknown types
    return f"SESSION={session_id} URL={url} {event_type.upper()}: {data}"


# =============================================================================
# Issue #476: Prometheus Metrics Endpoint
# =============================================================================


def _process_page_metrics(metrics_manager, page_metrics: PageMetrics) -> None:
    """Process page performance metrics."""
    if page_metrics.load_time_seconds is not None:
        metrics_manager.record_frontend_page_load(
            page_metrics.page, page_metrics.load_time_seconds
        )
    if page_metrics.fcp_seconds is not None:
        metrics_manager.record_frontend_fcp(page_metrics.page, page_metrics.fcp_seconds)
    if page_metrics.lcp_seconds is not None:
        metrics_manager.record_frontend_lcp(page_metrics.page, page_metrics.lcp_seconds)
    if page_metrics.tti_seconds is not None:
        metrics_manager.record_frontend_tti(page_metrics.page, page_metrics.tti_seconds)
    if page_metrics.dom_loaded_seconds is not None:
        metrics_manager.record_frontend_dom_loaded(
            page_metrics.page, page_metrics.dom_loaded_seconds
        )


def _process_api_calls(metrics_manager, api_calls: List[ApiCallMetric]) -> None:
    """Process API call metrics."""
    for call in api_calls:
        metrics_manager.record_frontend_api_request(
            endpoint=call.endpoint,
            method=call.method,
            status=call.status,
            latency_seconds=call.latency_seconds,
            is_slow=call.is_slow,
            is_timeout=call.is_timeout,
        )
        if call.error_type:
            metrics_manager.record_frontend_api_error(
                call.endpoint, call.method, call.error_type
            )


def _process_js_errors(metrics_manager, js_errors: List[JsErrorMetric]) -> None:
    """Process JavaScript error metrics."""
    for error in js_errors:
        if error.is_rejection:
            metrics_manager.record_frontend_unhandled_rejection(error.page)
        else:
            metrics_manager.record_frontend_js_error(error.error_type, error.page)
        if error.component:
            metrics_manager.record_frontend_component_error(
                error.component, error.error_type
            )


def _process_user_actions(
    metrics_manager, user_actions: List[UserActionMetric]
) -> None:
    """Process user action metrics."""
    for action in user_actions:
        metrics_manager.record_frontend_user_action(action.action_type, action.page)
        if action.form_name and action.form_status:
            metrics_manager.record_frontend_form_submission(
                action.form_name, action.form_status
            )


def _process_session_metric(metrics_manager, session: SessionMetric) -> None:
    """Process session metrics."""
    if session.event == "start":
        metrics_manager.record_frontend_session_start()
    elif session.event == "end" and session.duration_seconds is not None:
        metrics_manager.record_frontend_session_duration(session.duration_seconds)


def _process_websocket_events(
    metrics_manager, websocket_events: List[WebSocketMetric]
) -> None:
    """Process WebSocket event metrics."""
    for ws_event in websocket_events:
        metrics_manager.record_frontend_ws_event(ws_event.event)
        if ws_event.direction and ws_event.event_type:
            metrics_manager.record_frontend_ws_message(
                ws_event.direction, ws_event.event_type
            )


def _process_resources(metrics_manager, resources: List[ResourceMetric]) -> None:
    """Process resource load metrics."""
    for resource in resources:
        metrics_manager.record_frontend_resource_load(
            resource.resource_type, resource.load_time_seconds
        )
        if resource.is_slow:
            metrics_manager.record_frontend_slow_resource(resource.resource_type)


def _process_critical_issues(
    metrics_manager, critical_issues: List[CriticalIssueMetric]
) -> None:
    """Process critical issue metrics."""
    for issue in critical_issues:
        metrics_manager.record_frontend_critical_issue(issue.issue_type)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="receive_rum_metrics",
    error_code_prefix="RUM",
)
@router.post("/metrics")
async def receive_rum_metrics(metrics: RumMetrics):
    """
    Receive RUM metrics from frontend and record them to Prometheus.

    Issue #476: This endpoint receives batched RUM metrics from the frontend
    and records them to the Prometheus metrics system for monitoring.
    """
    try:
        metrics_manager = get_metrics_manager()
        recorded_count = 0

        # Process page performance metrics
        if metrics.page_metrics:
            _process_page_metrics(metrics_manager, metrics.page_metrics)
            recorded_count += 1

        # Process API call metrics
        if metrics.api_calls:
            _process_api_calls(metrics_manager, metrics.api_calls)
            recorded_count += len(metrics.api_calls)

        # Process JavaScript error metrics
        if metrics.js_errors:
            _process_js_errors(metrics_manager, metrics.js_errors)
            recorded_count += len(metrics.js_errors)

        # Process user action metrics
        if metrics.user_actions:
            _process_user_actions(metrics_manager, metrics.user_actions)
            recorded_count += len(metrics.user_actions)

        # Process session metrics
        if metrics.session:
            _process_session_metric(metrics_manager, metrics.session)
            recorded_count += 1

        # Process WebSocket events
        if metrics.websocket_events:
            _process_websocket_events(metrics_manager, metrics.websocket_events)
            recorded_count += len(metrics.websocket_events)

        # Process resource load metrics
        if metrics.resources:
            _process_resources(metrics_manager, metrics.resources)
            recorded_count += len(metrics.resources)

        # Process critical issues
        if metrics.critical_issues:
            _process_critical_issues(metrics_manager, metrics.critical_issues)
            recorded_count += len(metrics.critical_issues)

        logger.debug(
            f"Recorded {recorded_count} RUM metrics from session {metrics.session_id}"
        )

        return {
            "status": "success",
            "message": "RUM metrics recorded to Prometheus",
            "session_id": metrics.session_id,
            "metrics_recorded": recorded_count,
        }

    except Exception as e:
        logger.error("Error recording RUM metrics: %s", str(e))
        # Don't raise HTTP exception to avoid disrupting user experience
        return {
            "status": "error",
            "message": f"Failed to record RUM metrics: {str(e)}",
            "session_id": metrics.session_id,
        }
