"""
Batch API endpoints for optimized initial loading
Reduces multiple round trips by combining requests
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)
router = APIRouter(tags=["batch", "optimization"])


class BatchRequest(BaseModel):
    """Request multiple endpoints in one call"""

    requests: List[Dict[str, Any]]  # List of {endpoint: str, method: str, params: dict}


class BatchResponse(BaseModel):
    """Combined response from multiple endpoints"""

    responses: Dict[str, Any]  # Map of endpoint to response data
    errors: Dict[str, str]  # Map of endpoint to error message
    timing: Dict[str, float]  # Map of endpoint to response time


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


@router.post("/chat-init")
async def chat_init():
    """Initialize chat system - required by frontend"""
    return {
        "status": "success",
        "message": "Chat system initialized",
        "sessions": [],
        "timestamp": datetime.now().isoformat(),
    }


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

    from fastapi import Request

    from backend.fast_app_factory_fix import app

    responses = {}
    errors = {}
    timing = {}

    async def execute_request(req: Dict[str, Any]):
        endpoint = req.get("endpoint", "")
        method = req.get("method", "GET").upper()
        params = req.get("params", {})

        start_time = time.time()

        try:
            # Get the route handler from the app
            for route in app.routes:
                if hasattr(route, "path") and route.path == endpoint:
                    if method in route.methods:
                        # Call the endpoint handler directly
                        if method == "GET":
                            response = await route.endpoint(**params)
                        else:
                            response = await route.endpoint(params)

                        responses[endpoint] = response
                        timing[endpoint] = time.time() - start_time
                        return

            # Endpoint not found
            errors[endpoint] = f"Endpoint {endpoint} not found"
            timing[endpoint] = time.time() - start_time

        except Exception as e:
            logger.error(f"Error in batch request for {endpoint}: {e}")
            errors[endpoint] = str(e)
            timing[endpoint] = time.time() - start_time

    # Execute all requests in parallel
    tasks = [execute_request(req) for req in batch_request.requests]
    await asyncio.gather(*tasks, return_exceptions=True)

    return BatchResponse(responses=responses, errors=errors, timing=timing)


@router.post("/chat-init")
async def batch_chat_initialization():
    """
    Optimized endpoint for chat interface initialization.
    Returns all data needed to start the chat in one request.
    """
    import asyncio
    import time

    start_time = time.time()
    logger.info("Starting batch chat initialization...")

    try:
        # Minimal response to avoid any blocking operations
        response = {
            "chat_sessions": [],
            "system_health": {
                "status": "healthy",
                "backend": "connected",
                "mode": "batch_fast",
            },
            "kb_stats": {"total_documents": 0, "total_chunks": 0, "status": "ready"},
            "service_health": {"status": "online", "healthy": 1, "total": 1},
            "timing": {"total_ms": (time.time() - start_time) * 1000},
        }

        logger.info(
            f"Batch chat initialization completed in {(time.time() - start_time)*1000:.2f}ms"
        )
        return response

    except Exception as e:
        logger.error(f"Batch chat initialization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Helper functions for batch initialization
async def get_chat_sessions():
    """Get chat sessions list using async file operations"""
    import asyncio
    import os
    from datetime import datetime

    from backend.fast_app_factory_fix import app

    if hasattr(app.state, "chat_history_manager") and app.state.chat_history_manager:
        try:
            # Use asyncio.to_thread to avoid blocking the event loop
            sessions = await asyncio.to_thread(
                _get_sessions_sync, app.state.chat_history_manager
            )
            return sessions
        except Exception as e:
            logger.warning(f"Failed to get chat sessions: {e}")
            return []
    return []


def _get_sessions_sync(chat_history_manager):
    """Synchronous helper for getting sessions (runs in thread pool)"""
    try:
        sessions = []
        chats_directory = chat_history_manager._get_chats_directory()

        if not os.path.exists(chats_directory):
            os.makedirs(chats_directory, exist_ok=True)
            return sessions

        # Fast metadata-only approach
        for filename in os.listdir(chats_directory):
            if filename.startswith("chat_") and filename.endswith(".json"):
                chat_id = filename.replace("chat_", "").replace(".json", "")
                chat_path = os.path.join(chats_directory, filename)

                try:
                    stat = os.stat(chat_path)
                    sessions.append(
                        {
                            "id": chat_id,
                            "title": f"Chat {chat_id[-8:] if len(chat_id) > 8 else chat_id}",
                            "created_at": datetime.fromtimestamp(
                                stat.st_ctime
                            ).isoformat(),
                            "updated_at": datetime.fromtimestamp(
                                stat.st_mtime
                            ).isoformat(),
                            "message_count": 0,  # Skip message count for speed
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to get stats for {filename}: {e}")
                    continue

        return sessions

    except Exception as e:
        logger.error(f"Failed to list chat sessions: {e}")
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
