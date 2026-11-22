# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Background Tasks Initialization Module

Utility helpers shared across initialization code.
The main initialization sequence lives in lifespan.py.
"""

from fastapi import FastAPI

from autobot_shared.logging_manager import get_logger
from initialization.ai_stack_init import log_initialization_step

__all__ = ["get_or_create_knowledge_base_or_none", "log_initialization_step"]

logger = get_logger(__name__, "backend")


async def get_or_create_knowledge_base_or_none(app: FastAPI, force_refresh: bool = False):
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
