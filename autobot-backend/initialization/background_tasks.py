# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Background Tasks Initialization Module

Utility helpers shared across initialization code.
The main initialization sequence lives in lifespan.py.
"""

from fastapi import FastAPI

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__, "backend")


def log_initialization_step(stage: str, message: str, percentage: int = 0, success: bool = True):
    """Log initialization steps with consistent formatting."""
    icon = "✅" if success else "❌" if percentage == 100 else "🔄"
    logger.info(f"{icon} [{percentage:3d}%] {stage}: {message}")


async def get_or_create_knowledge_base(app: FastAPI, force_refresh: bool = False):
    """
    Get or create a properly initialized knowledge base instance for the app.
    Enhanced with AI Stack integration awareness.
    """
    from knowledge_factory import get_or_create_knowledge_base as factory_kb

    try:
        kb = await factory_kb(app, force_refresh)
        return kb
    except Exception as e:
        logger.error("Knowledge base initialization error: %s", e)
        return None
