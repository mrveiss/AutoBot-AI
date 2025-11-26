# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RUM (Real User Monitoring) API endpoints for logging frontend events.
Provides comprehensive logging of user interactions, errors, and performance metrics.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict

from backend.type_defs.common import Metadata

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.utils.error_boundaries import ErrorCategory, with_error_handling

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

# In-memory storage for RUM events (in production, this would use Redis or database)
rum_events = []
rum_sessions = {}


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
    # Note: rum_config is modified in-place via .update(), no reassignment needed
    try:
        rum_config.update(config.dict())

        # Reinitialize logger with new settings
        global rum_logger
        rum_logger = setup_rum_logger()

        if rum_config["enabled"]:
            rum_logger.info(f"RUM monitoring enabled with config: {rum_config}")
        else:
            rum_logger.info("RUM monitoring disabled")

        logger.info(f"RUM configuration updated: enabled={rum_config['enabled']}")

        return {
            "status": "success",
            "message": "RUM configuration updated",
            "config": rum_config,
        }

    except Exception as e:
        logger.error(f"Error configuring RUM: {str(e)}")
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

        # Log to dedicated RUM log file based on event type
        log_message = format_rum_log_message(event_data)

        if event.type == "error" or event.type == "promise_rejection":
            rum_logger.error(log_message)
        elif event.type == "performance":
            rum_logger.info(log_message)
        elif event.type == "interaction":
            if rum_config["interaction_tracking"]:
                rum_logger.debug(log_message)
        else:
            rum_logger.info(log_message)

        # Keep only last 10000 events in memory to prevent memory leaks
        if len(rum_events) > 10000:
            # Use slice assignment to modify global list in-place
            rum_events[:] = rum_events[-5000:]  # Keep last 5000 events

        return {
            "status": "success",
            "message": "Event logged",
            "session_event_count": rum_sessions[session_id]["event_count"],
        }

    except Exception as e:
        logger.error(f"Error logging RUM event: {str(e)}")
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
        rum_config["enabled"] = False

        rum_logger.info("RUM monitoring disabled via API")
        logger.info("RUM monitoring disabled")

        return {"status": "success", "message": "RUM monitoring disabled"}

    except Exception as e:
        logger.error(f"Error disabling RUM: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error disabling RUM: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_rum_data",
    error_code_prefix="RUM",
)
@router.post("/clear")
async def clear_rum_data():
    """Clear all RUM data"""
    # Note: rum_events/rum_sessions are modified in-place via .clear(), no reassignment needed
    try:
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
        logger.error(f"Error clearing RUM data: {str(e)}")
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
        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "config": rum_config,
            "sessions": rum_sessions,
            "events": rum_events[-1000:],  # Export last 1000 events to avoid huge files
            "summary": {
                "total_events": len(rum_events),
                "total_sessions": len(rum_sessions),
                "event_types": {},
            },
        }

        # Calculate event type distribution
        for event in rum_events:
            event_type = event.get("type", "unknown")
            export_data["summary"]["event_types"][event_type] = (
                export_data["summary"]["event_types"].get(event_type, 0) + 1
            )

        rum_logger.info("RUM data exported")

        return {"status": "success", "data": export_data}

    except Exception as e:
        logger.error(f"Error exporting RUM data: {str(e)}")
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
        # Calculate session statistics
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
            "config": rum_config,
            "statistics": {
                "total_events": len(rum_events),
                "total_sessions": len(rum_sessions),
                "active_sessions": active_sessions,
                "events_today": total_events_today,
            },
        }

        return {"status": "success", "rum_status": status}

    except Exception as e:
        logger.error(f"Error getting RUM status: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting RUM status: {str(e)}"
        )


def format_rum_log_message(event_data: Metadata) -> str:
    """Format RUM event data into a readable log message"""
    event_type = event_data.get("type", "unknown")
    session_id = event_data.get("sessionId", "unknown")
    url = event_data.get("url", "unknown")
    data = event_data.get("data", {})

    if event_type == "error":
        return (
            f"SESSION={session_id} URL={url} ERROR: {data.get('message', 'Unknown error')} "
            f"FILE={data.get('filename', 'unknown')} LINE={data.get('lineno', 0)} "
            f"CONTEXT={data.get('context', 'global')}"
        )

    elif event_type == "promise_rejection":
        return f"SESSION={session_id} URL={url} PROMISE_REJECTION: {data.get('reason', 'Unknown reason')}"

    elif event_type == "performance":
        metric_type = data.get("metric_type", "unknown")
        if metric_type == "api_call":
            return (
                f"SESSION={session_id} API_CALL: {data.get('method', 'GET')} {data.get('url', 'unknown')} "
                f"DURATION={data.get('duration', 0):.2f}ms STATUS={data.get('status', 'unknown')}"
            )
        else:
            return f"SESSION={session_id} PERFORMANCE: {metric_type} {data}"

    elif event_type == "interaction":
        return (
            f"SESSION={session_id} INTERACTION: {data.get('element', 'unknown')} "
            f"ID={data.get('id', 'none')} CLASS={data.get('className', 'none')} "
            f"POS=({data.get('coordinates', {}).get('x', 0)},{data.get('coordinates', {}).get('y', 0)})"
        )

    elif event_type == "form_submission":
        return (
            f"SESSION={session_id} FORM_SUBMIT: ACTION={data.get('action', 'none')} "
            f"METHOD={data.get('method', 'GET')} FIELDS={data.get('fieldCount', 0)}"
        )

    else:
        return f"SESSION={session_id} URL={url} {event_type.upper()}: {data}"
