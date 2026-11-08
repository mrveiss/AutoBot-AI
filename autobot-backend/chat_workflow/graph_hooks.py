# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Plugin lifecycle hooks the chat graph fires around LLM execution (moved out of ``graph.py``, #21023).

``graph.py`` is over the file-size ceiling and may not grow; these three were self-contained, so they live
here and ``graph`` imports them by name (a test that patches ``graph._emit_*`` still intercepts the call).
"""

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def _emit_planned_agent_error_hooks(session_id, iteration, exc: Exception) -> None:
    """Fire ON_AGENT_ERROR for the plan-only path (mirrors generate_response). GH#11202."""
    try:
        from autobot_shared.plugin_sdk import Hook, HookRegistry

        await HookRegistry().call_hook(
            Hook.ON_AGENT_ERROR.value,
            session_id=session_id,
            iteration=iteration,
            error=str(exc),
        )
    except Exception as _hook_exc:  # noqa: BLE001
        logger.debug("Plugin hook ON_AGENT_ERROR failed (non-fatal): %s", _hook_exc)


async def _emit_planned_agent_complete_hook(session_id, iteration, llm_response: str) -> None:
    """Fire ON_AGENT_COMPLETE for the plan-only path (mirrors generate_response). GH#11202."""
    try:
        from autobot_shared.plugin_sdk import Hook, HookRegistry

        await HookRegistry().call_hook(
            Hook.ON_AGENT_COMPLETE.value,
            session_id=session_id,
            iteration=iteration,
            response=llm_response or "",
        )
    except Exception as _hook_exc:  # noqa: BLE001
        logger.debug("Plugin hook ON_AGENT_COMPLETE failed (non-fatal): %s", _hook_exc)


async def _emit_agent_execute_hook(session_id, iteration) -> None:
    """Issue #3278: notify plugins before LLM execution."""
    try:
        from autobot_shared.plugin_sdk import Hook, HookRegistry

        await HookRegistry().call_hook(
            Hook.ON_AGENT_EXECUTE.value,
            session_id=session_id,
            iteration=iteration,
            agent_type="chat_workflow",
        )
    except Exception as _hook_exc:  # noqa: BLE001
        logger.debug("Plugin hook ON_AGENT_EXECUTE failed (non-fatal): %s", _hook_exc)
