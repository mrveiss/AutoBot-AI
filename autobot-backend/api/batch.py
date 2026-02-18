# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Batch API endpoints for optimized initial loading
Reduces multiple round trips by combining requests
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, List

from backend.type_defs.common import Metadata
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(tags=["batch", "optimization"])


# Helper functions for route matching (Issue #315 - extracted)
def _find_route_handler(app, endpoint: str, method: str):
    """Find matching route handler for given endpoint and method"""
    for route in app.routes:
        if hasattr(route, "path") and route.path == endpoint:
            if method in route.methods:
                return route.endpoint
    return None


def _process_session_file(filename: str, chats_directory: str) -> dict | None:
    """Process a single session file and return session metadata (Issue #315 - extracted)"""
    if not (filename.startswith("chat_") and filename.endswith(".json")):
        return None

    chat_id = filename.replace("chat_", "").replace(".json", "")
    chat_path = os.path.join(chats_directory, filename)

    try:
        stat = os.stat(chat_path)
        return {
            "id": chat_id,
            "title": f"Chat {chat_id[-8:] if len(chat_id) > 8 else chat_id}",
            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "message_count": 0,  # Skip message count for speed
        }
    except Exception as e:
        logger.warning("Failed to get stats for %s: %s", filename, e)
        return None


class BatchRequest(BaseModel):
    """Request multiple endpoints in one call"""

    requests: List[Metadata]  # List of {endpoint: str, method: str, params: dict}


class BatchResponse(BaseModel):
    """Combined response from multiple endpoints"""

    responses: Metadata  # Map of endpoint to response data
    errors: Dict[str, str]  # Map of endpoint to error message
    timing: Dict[str, float]  # Map of endpoint to response time


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_batch_status",
    error_code_prefix="BATCH",
)
@router.get("/status")
async def get_batch_status():
    """Get batch processing service status"""
    return {
        "status": "healthy",
        "service": "batch_processor",
        "capabilities": ["batch_load", "chat_init"],
        "max_batch_size": 10,
        "timeout": 30,
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="batch_load",
    error_code_prefix="BATCH",
)
@router.post("/load")
async def batch_load(batch_request: BatchRequest):
    """
    Execute multiple API calls in parallel and return combined results.
    Perfect for initial page loads.

    Example request:
    {
        "requests": [
            {"endpoint": "/api/chats", "method": "GET"},
            {"endpoint": "/api/system/health", "method": "GET"},
            {"endpoint": "/api/knowledge_base/stats", "method": "GET"}
        ]
    }
    """
    import time

    from backend.fast_app_factory_fix import app

    responses = {}
    errors = {}
    timing = {}

    async def execute_request(req: Metadata):
        """Execute a single batch request against the specified endpoint."""
        endpoint = req.get("endpoint", "")
        method = req.get("method", "GET").upper()
        params = req.get("params", {})

        start_time = time.time()

        try:
            # Get the route handler from the app (Issue #315 - refactored)
            route_handler = _find_route_handler(app, endpoint, method)

            if route_handler:
                # Call the endpoint handler directly
                if method == "GET":
                    response = await route_handler(**params)
                else:
                    response = await route_handler(params)

                responses[endpoint] = response
                timing[endpoint] = time.time() - start_time
                return

            # Endpoint not found
            errors[endpoint] = f"Endpoint {endpoint} not found"
            timing[endpoint] = time.time() - start_time

        except Exception as e:
            logger.error("Error in batch request for %s: %s", endpoint, e)
            errors[endpoint] = str(e)
            timing[endpoint] = time.time() - start_time

    # Execute all requests in parallel
    tasks = [execute_request(req) for req in batch_request.requests]
    await asyncio.gather(*tasks, return_exceptions=True)

    return BatchResponse(responses=responses, errors=errors, timing=timing)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="batch_chat_initialization",
    error_code_prefix="BATCH",
)
@router.get("/chat-init")
@router.post("/chat-init")
async def batch_chat_initialization():
    """
    Optimized endpoint for chat interface initialization.
    Returns all data needed to start the chat in one request.
    Supports both GET and POST methods for frontend compatibility.
    """
    import time

    start_time = time.time()
    logger.info("Starting batch chat initialization...")

    try:
        # Gather all data in parallel
        results = await asyncio.gather(
            get_chat_sessions(),
            get_system_health(),
            get_service_health(),
            get_settings(),
            return_exceptions=True,
        )

        # Unpack results with error handling
        chat_sessions = (
            results[0] if not isinstance(results[0], Exception) else {"sessions": []}
        )
        system_health = (
            results[1]
            if not isinstance(results[1], Exception)
            else {"status": "unknown"}
        )
        service_health = (
            results[2]
            if not isinstance(results[2], Exception)
            else {"status": "unknown"}
        )
        settings = results[3] if not isinstance(results[3], Exception) else {}

        response = {
            "chat_sessions": chat_sessions,
            "system_health": system_health,
            "service_health": service_health,
            "settings": settings,
            "timing": {"total_ms": (time.time() - start_time) * 1000},
        }

        logger.info(
            f"Batch chat initialization completed in {(time.time() - start_time)*1000:.2f}ms"
        )
        return response

    except Exception as e:
        logger.error("Batch chat initialization failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# Helper functions for batch initialization
async def get_chat_sessions():
    """Get chat sessions list using async file operations"""

    from backend.fast_app_factory_fix import app

    if hasattr(app.state, "chat_history_manager") and app.state.chat_history_manager:
        try:
            # Use asyncio.to_thread to avoid blocking the event loop
            sessions = await asyncio.to_thread(
                _get_sessions_sync, app.state.chat_history_manager
            )
            return {"sessions": sessions}
        except Exception as e:
            logger.warning("Failed to get chat sessions: %s", e)
            return {"sessions": []}
    return {"sessions": []}


def _get_sessions_sync(chat_history_manager):
    """Synchronous helper for getting sessions (runs in thread pool)"""
    try:
        sessions = []
        chats_directory = chat_history_manager._get_chats_directory()

        if not os.path.exists(chats_directory):
            os.makedirs(chats_directory, exist_ok=True)
            return sessions

        # Fast metadata-only approach (Issue #315 - refactored)
        for filename in os.listdir(chats_directory):
            session = _process_session_file(filename, chats_directory)
            if session:
                sessions.append(session)

        return sessions

    except Exception as e:
        logger.error("Failed to list chat sessions: %s", e)
        return []


async def get_system_health():
    """Get system health status"""
    from datetime import datetime

    return {
        "status": "healthy",
        "backend": "connected",
        "timestamp": datetime.now().isoformat(),
        "mode": "batch_optimized",
    }


async def get_kb_stats():
    """Get knowledge base statistics"""
    # Simplified for fast response
    return {"total_documents": 0, "total_chunks": 0, "categories": [], "total_facts": 0}


async def get_service_health():
    """Get service health status"""
    return {"status": "online", "healthy": 1, "total": 1, "warnings": 0, "errors": 0}


async def get_settings():
    """Get user settings"""
    try:
        from backend.fast_app_factory_fix import app

        # Try to get settings from app state or return defaults
        if hasattr(app.state, "settings"):
            return app.state.settings

        # Return default settings structure
        return {
            "theme": "light",
            "language": "en",
            "notifications": True,
            "auto_scroll": True,
        }
    except Exception as e:
        logger.warning("Failed to get settings: %s", e)
        return {}
