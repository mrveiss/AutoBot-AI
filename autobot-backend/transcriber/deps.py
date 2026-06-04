# autobot-backend/transcriber/deps.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""FastAPI dependency: provides the transcriber Database instance."""

from fastapi import Request
from transcriber.database import Database

# Placeholder user ID for routes without real authentication.
# Replaced by real auth in future milestone.
DEFAULT_USER = "default"


async def get_db(request: Request) -> Database:
    return request.app.state.transcriber_db
