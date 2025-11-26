#!/usr/bin/env python3
"""
Simple Async App without Redis dependency
Quick fix to get async chat working without full dependency setup
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@asynccontextmanager
async def simple_lifespan(app: FastAPI):
    """Simple lifespan manager without complex dependencies"""
    logger.info("🚀 Starting AutoBot backend (Simple Async)")
    yield
    logger.info("🛑 Shutting down AutoBot backend")


def create_simple_app() -> FastAPI:
    """Create FastAPI app with minimal async architecture"""

    app = FastAPI(
        title="AutoBot API (Simple Async)",
        version="2.0.0-simple",
        description="AutoBot backend with simple async architecture",
        lifespan=simple_lifespan
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error(f"Global exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": str(exc),
                "type": type(exc).__name__
            }
        )

    # Health endpoint
    @app.get("/api/system/health")
    async def health_check():
        """Simple health check"""
        return {
            "status": "healthy",
            "backend": "connected",
            "timestamp": "2025-09-01T14:30:00.000Z",
            "simple_async": True,
            "response_time_ms": "< 50ms"
        }

    # Simple chat endpoint
    class ChatMessageRequest(BaseModel):
        message: str = Field(..., min_length=1, max_length=10000)
        options: dict = Field(default_factory=dict)

    @app.post("/api/chat/chats/{chat_id}/message")
    async def send_chat_message(chat_id: str, request_data: ChatMessageRequest):
        """Simple chat endpoint with mock LLM response"""
        try:
            logger.info(f"Processing chat message for chat_id: {chat_id}")

            # Mock response (replace with actual LLM call later)
            mock_response = f"Hello! I received your message: '{request_data.message}'. This is a simple async response from the new architecture."

            return {
                "response": mock_response,
                "message_type": "general_query",
                "knowledge_status": "bypassed",
                "processing_time": 0.1,
                "conversation_id": chat_id,
                "workflow_messages": [
                    {
                        "type": "thought",
                        "text": "🤔 Processing your message with simple async architecture...",
                        "sender": "assistant",
                        "timestamp": "14:30:00",
                        "metadata": {}
                    },
                    {
                        "type": "response",
                        "text": mock_response,
                        "sender": "assistant",
                        "timestamp": "14:30:00",
                        "metadata": {}
                    }
                ],
                "sources": [],
                "metadata": {
                    "architecture": "simple_async",
                    "redis_required": False
                }
            }

        except Exception as e:
            logger.error(f"Chat processing error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/chat/chats/new")
    async def create_new_chat():
        """Create new chat session"""
        import uuid
        chat_id = str(uuid.uuid4())
        return {
            "chat_id": chat_id,
            "created": True,
            "timestamp": "2025-09-01T14:30:00.000Z"
        }

    @app.get("/api/chat/chats/{chat_id}")
    async def get_chat_messages(chat_id: str):
        """Get messages for a chat session"""
        return {
            "chat_id": chat_id,
            "messages": [],
            "message_count": 0
        }

    @app.get("/api/chat/chats")
    async def list_chats():
        """List all chat sessions"""
        return {
            "chats": [],
            "total_count": 0
        }

    return app


# Create the app instance
app = create_simple_app()
