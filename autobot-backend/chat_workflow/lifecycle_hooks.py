# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Lifecycle hook emitters of the chat loop: continuation, loop end, errors and response send (#4181).

Moved out of ``llm_handler.py`` unchanged (the file-size ratchet, #19673); ``llm_handler`` re-exports every name, so
``from chat_workflow.llm_handler import _emit_loop_complete`` keeps working.
"""

from __future__ import annotations

from typing import Any, Dict

from middleware.base import HookContext
from middleware.hooks import HookPoint
from middleware.manager import get_extension_manager


async def _emit_before_continuation(iteration: int, session_id: str, context: Dict[str, Any]) -> bool:
    """Emit BEFORE_CONTINUATION hook to registered extensions.

    Issue #4181: Fires before starting next iteration of continuation loop
    so extensions can inspect state or cancel continuation.

    Args:
        iteration: Current iteration number
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        False to cancel continuation, True otherwise
    """
    ctx = HookContext(
        session_id=session_id,
        data={"iteration": iteration, "context": context},
    )
    results = await get_extension_manager().invoke_hook(HookPoint.BEFORE_CONTINUATION, ctx)
    return not any(result is False for result in results)


async def _emit_after_continuation(iteration: int, response: str, session_id: str, context: Dict[str, Any]) -> str:
    """Emit AFTER_CONTINUATION hook to registered extensions.

    Issue #4181: Fires after continuation iteration completes so extensions
    can inspect or modify the response.

    Args:
        iteration: Completed iteration number
        response: Response from this iteration
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        Possibly modified response
    """
    ctx = HookContext(
        session_id=session_id,
        data={"iteration": iteration, "response": response, "context": context},
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.AFTER_CONTINUATION, ctx, "response")
    return result if isinstance(result, str) else response


async def _emit_loop_complete(total_iterations: int, final_response: str, session_id: str) -> str:
    """Emit LOOP_COMPLETE hook to registered extensions.

    Issue #4181: Fires when continuation loop completes so extensions
    can finalize or modify the final response.

    Args:
        total_iterations: Total iterations completed
        final_response: Final response from loop
        session_id: Session identifier

    Returns:
        Possibly modified final response
    """
    ctx = HookContext(
        session_id=session_id,
        data={"total_iterations": total_iterations, "final_response": final_response},
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.LOOP_COMPLETE, ctx, "final_response")
    return result if isinstance(result, str) else final_response


async def _emit_repairable_error(error: Exception, session_id: str, context: Dict[str, Any]) -> bool:
    """Emit REPAIRABLE_ERROR hook to registered extensions.

    Issue #4181: Fires when a repairable error occurs so extensions
    can attempt recovery or take corrective action.

    Args:
        error: The repairable exception
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        True if error was handled, False otherwise
    """
    ctx = HookContext(
        session_id=session_id,
        data={
            "error": str(error),
            "error_type": type(error).__name__,
            "context": context,
        },
    )
    result = await get_extension_manager().invoke_until_handled(HookPoint.REPAIRABLE_ERROR, ctx)
    return result is not None


async def _emit_critical_error(error: Exception, session_id: str, context: Dict[str, Any]) -> None:
    """Emit CRITICAL_ERROR hook to registered extensions.

    Issue #4181: Fires when a critical unrecoverable error occurs so
    extensions can log, alert, or perform cleanup.

    Args:
        error: The critical exception
        session_id: Session identifier
        context: Request-level context dict
    """
    ctx = HookContext(
        session_id=session_id,
        data={
            "error": str(error),
            "error_type": type(error).__name__,
            "context": context,
        },
    )
    await get_extension_manager().invoke_hook(HookPoint.CRITICAL_ERROR, ctx)


async def _emit_before_response_send(response: str, session_id: str, context: Dict[str, Any]) -> str:
    """Emit BEFORE_RESPONSE_SEND hook to registered extensions.

    Issue #4181: Fires before sending response to user so extensions
    can inspect, filter, or modify the response.

    Args:
        response: Response to be sent
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        Possibly modified response
    """
    ctx = HookContext(
        session_id=session_id,
        data={"response": response, "context": context},
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.BEFORE_RESPONSE_SEND, ctx, "response")
    return result if isinstance(result, str) else response


async def _emit_after_response_send(response: str, session_id: str, context: Dict[str, Any]) -> None:
    """Emit AFTER_RESPONSE_SEND hook to registered extensions.

    Issue #4181: Fires after response is sent to user so extensions
    can perform post-processing or logging.

    Args:
        response: Response that was sent
        session_id: Session identifier
        context: Request-level context dict
    """
    ctx = HookContext(
        session_id=session_id,
        data={"response": response, "context": context},
    )
    await get_extension_manager().invoke_hook(HookPoint.AFTER_RESPONSE_SEND, ctx)
