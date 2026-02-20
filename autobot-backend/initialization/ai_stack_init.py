# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AI Stack Initialization Module

This module handles AI Stack connection initialization and agent verification
for the AutoBot backend.
"""

from fastapi import FastAPI

from autobot_shared.logging_manager import get_logger
from backend.services.ai_stack_client import get_ai_stack_client

logger = get_logger(__name__, "backend")


def log_initialization_step(
    stage: str, message: str, percentage: int = 0, success: bool = True
):
    """Log initialization steps with consistent formatting."""
    icon = "✅" if success else "❌" if percentage == 100 else "🔄"
    logger.info(f"{icon} [{percentage:3d}%] {stage}: {message}")


async def update_init_status(key: str, value: str) -> None:
    """Update initialization status (imported from app_factory_enhanced)."""
    # This function will be called with the parent module's status dict


async def append_init_error(error: str) -> None:
    """Append initialization error (imported from app_factory_enhanced)."""
    # This function will be called with the parent module's error list


async def initialize_ai_stack(app: FastAPI, update_status_fn, append_error_fn) -> None:
    """
    Initialize AI Stack connection and verify agent availability.

    Args:
        app: FastAPI application instance
        update_status_fn: Function to update initialization status
        append_error_fn: Function to append initialization errors
    """
    try:
        log_initialization_step("AI Stack", "Initializing AI Stack connection...", 0)

        # Test AI Stack connectivity
        ai_client = await get_ai_stack_client()
        health_status = await ai_client.health_check()
        app.state.ai_stack_client = ai_client

        if health_status["status"] == "healthy":
            await update_status_fn("ai_stack", "connected")
            log_initialization_step(
                "AI Stack", "AI Stack connection established", 50, True
            )

            # Test agent availability
            try:
                agents_info = await ai_client.list_available_agents()
                agent_count = len(agents_info.get("agents", []))
                await update_status_fn("ai_stack_agents", "ready")
                app.state.ai_stack_agents = agents_info

                log_initialization_step(
                    "AI Stack",
                    f"Verified {agent_count} AI agents available",
                    100,
                    True,
                )
            except Exception as e:
                logger.warning("AI Stack agent verification failed: %s", e)
                await update_status_fn("ai_stack_agents", "partial")
                await append_error_fn(f"Agent verification: {str(e)}")

        else:
            logger.warning(
                "AI Stack API unreachable at %s — agent routing disabled",
                ai_client.base_url,
            )
            await update_status_fn("ai_stack", "error")
            await append_error_fn("AI Stack health check failed")
            ai_client.start_retry_loop()
            log_initialization_step(
                "AI Stack", "AI Stack unreachable — retry enabled", 100, False
            )

    except Exception as e:
        logger.warning("AI Stack API unreachable — agent routing disabled: %s", e)
        await update_status_fn("ai_stack", "error")
        await append_error_fn(f"AI Stack init: {str(e)}")
        log_initialization_step(
            "AI Stack", f"Initialization failed: {str(e)}", 100, False
        )
