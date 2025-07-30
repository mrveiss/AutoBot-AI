from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import json
import yaml
from datetime import datetime, timedelta
import requests
import logging
import uuid
from functools import lru_cache

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Simple TTL Cache implementation for performance optimization
class TTLCache:
    def __init__(self, ttl_seconds=300):  # 5 minute default TTL
        self.cache = {}
        self.ttl = ttl_seconds
    
    def get(self, key):
        if key in self.cache:
            value, timestamp = self.cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl):
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value):
        self.cache[key] = (value, datetime.now())
    
    def clear(self):
        self.cache.clear()

# Global cache instances
settings_cache = TTLCache(ttl_seconds=300)  # 5 minutes

# Import ChatHistoryManager
import sys
import os
import shutil
import glob
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.chat_history_manager import ChatHistoryManager
from src.config import global_config_manager

app = FastAPI()

# Initialize chat history manager with Redis support
chat_history_manager = ChatHistoryManager(use_redis=True, redis_host="localhost", redis_port=6379)

# Initialize app state for health checks
@app.on_event("startup")
async def startup_event():
    """Initialize application state on startup"""
    # Initialize empty state objects to prevent health check errors
    app.state.orchestrator = None  # Will be set if orchestrator is initialized
    app.state.diagnostics = None   # Will be set if diagnostics is initialized
    logger.info("Application startup completed - app.state initialized")

# Configure CORS
cors_origins = global_config_manager.get_nested('backend.cors_origins', ['http://localhost:5173'])
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .api import chat

app.include_router(chat.router)

from .api import chat, settings

app.include_router(chat.router)
app.include_router(settings.router)

from .api import chat, settings, redis

app.include_router(chat.router)
app.include_router(settings.router)
app.include_router(redis.router)

from .api import chat, settings, redis, llm

app.include_router(chat.router)
app.include_router(settings.router)
app.include_router(redis.router)
app.include_router(llm.router)

from .api import chat, settings, redis, llm, prompts, knowledge, system

app.include_router(chat.router)
app.include_router(settings.router)
app.include_router(redis.router)
app.include_router(llm.router)
app.include_router(prompts.router)
app.include_router(knowledge.router)
app.include_router(system.router)


if __name__ == "__main__":
    import uvicorn
    server_host = global_config_manager.get_nested('backend.server_host', '0.0.0.0')
    server_port = global_config_manager.get_nested('backend.server_port', 8001)
    logger.info(f"Starting FastAPI server on {server_host}:{server_port}")
    uvicorn.run(app, host=server_host, port=server_port)
