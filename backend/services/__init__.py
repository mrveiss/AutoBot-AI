"""
Backend Services Module

This module contains all service layer components for the AutoBot backend,
including AI Stack integration, database connections, and external service clients.
"""

from src.constants.network_constants import NetworkConstants

from .ai_stack_client import (
    AIStackClient,
    AIStackError,
    close_ai_stack_client,
    get_ai_stack_client,
)

__all__ = [
    "AIStackClient",
    "AIStackError",
    "get_ai_stack_client",
    "close_ai_stack_client",
]
