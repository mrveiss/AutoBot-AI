# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Extension hook point definitions.

Issue #658: Defines 22 lifecycle hook points for the extension system,
implementing Agent Zero's pattern for modular customization.
"""

from enum import Enum, auto


class HookPoint(Enum):
    """
    All extension hook points in the agent lifecycle.

    Hook points are organized into logical groups:
    - Message preparation (BEFORE_MESSAGE_PROCESS, AFTER_PROMPT_BUILD)
    - LLM interaction (BEFORE_LLM_CALL, DURING_LLM_STREAMING, etc.)
    - Tool execution (BEFORE_TOOL_PARSE, BEFORE_TOOL_EXECUTE, etc.)
    - Continuation loop (BEFORE_CONTINUATION, AFTER_CONTINUATION, etc.)
    - Error handling (ON_REPAIRABLE_ERROR, ON_CRITICAL_ERROR)
    - Response (BEFORE_RESPONSE_SEND, AFTER_RESPONSE_SEND)
    - Session lifecycle (ON_SESSION_CREATE, ON_SESSION_DESTROY)
    - Knowledge integration (BEFORE_RAG_QUERY, AFTER_RAG_RESULTS)
    - Approval flow (ON_APPROVAL_REQUIRED, ON_APPROVAL_RECEIVED)

    Usage:
        from extensions.hooks import HookPoint

        # Invoke hook at specific point
        await extension_manager.invoke_hook(
            HookPoint.BEFORE_TOOL_EXECUTE,
            context
        )
    """

    # Message preparation
    BEFORE_MESSAGE_PROCESS = auto()
    AFTER_PROMPT_BUILD = auto()

    # LLM interaction
    BEFORE_LLM_CALL = auto()
    DURING_LLM_STREAMING = auto()
    AFTER_LLM_RESPONSE = auto()

    # Tool execution
    BEFORE_TOOL_PARSE = auto()
    BEFORE_TOOL_EXECUTE = auto()
    AFTER_TOOL_EXECUTE = auto()
    TOOL_ERROR = auto()  # Method: on_tool_error

    # Continuation loop
    BEFORE_CONTINUATION = auto()
    AFTER_CONTINUATION = auto()
    LOOP_COMPLETE = auto()  # Method: on_loop_complete

    # Error handling
    REPAIRABLE_ERROR = auto()  # Method: on_repairable_error
    CRITICAL_ERROR = auto()  # Method: on_critical_error

    # Response
    BEFORE_RESPONSE_SEND = auto()
    AFTER_RESPONSE_SEND = auto()

    # Session lifecycle
    SESSION_CREATE = auto()  # Method: on_session_create
    SESSION_DESTROY = auto()  # Method: on_session_destroy

    # Knowledge integration
    BEFORE_RAG_QUERY = auto()
    AFTER_RAG_RESULTS = auto()

    # Approval flow
    APPROVAL_REQUIRED = auto()  # Method: on_approval_required
    APPROVAL_RECEIVED = auto()  # Method: on_approval_received


# Hook metadata for documentation and validation
HOOK_METADATA = {
    HookPoint.BEFORE_MESSAGE_PROCESS: {
        "description": "Called at the start of message handling",
        "can_modify": ["message", "context"],
        "return_type": "None",
    },
    HookPoint.AFTER_PROMPT_BUILD: {
        "description": "Called after system prompt is built",
        "can_modify": ["prompt"],
        "return_type": "Modified prompt string or None",
    },
    HookPoint.BEFORE_LLM_CALL: {
        "description": "Called before calling the LLM",
        "can_modify": ["prompt", "model"],
        "return_type": "False to cancel, None to continue",
    },
    HookPoint.DURING_LLM_STREAMING: {
        "description": "Called for each streaming chunk from LLM",
        "can_modify": ["chunk"],
        "return_type": "Modified chunk or None",
    },
    HookPoint.AFTER_LLM_RESPONSE: {
        "description": "Called after full response is received",
        "can_modify": ["response"],
        "return_type": "Modified response or None",
    },
    HookPoint.BEFORE_TOOL_PARSE: {
        "description": "Called before parsing tool calls from response",
        "can_modify": ["response"],
        "return_type": "Modified response or None",
    },
    HookPoint.BEFORE_TOOL_EXECUTE: {
        "description": "Called before each tool execution",
        "can_modify": ["tool_call"],
        "return_type": "False to cancel, None to continue",
    },
    HookPoint.AFTER_TOOL_EXECUTE: {
        "description": "Called after tool execution completes",
        "can_modify": ["result"],
        "return_type": "Modified result or None",
    },
    HookPoint.TOOL_ERROR: {
        "description": "Called when a tool throws an error",
        "can_modify": ["error"],
        "return_type": "RepairableException or re-raise",
    },
    HookPoint.BEFORE_CONTINUATION: {
        "description": "Called before LLM continuation iteration",
        "can_modify": ["prompt", "context"],
        "return_type": "False to stop loop, None to continue",
    },
    HookPoint.AFTER_CONTINUATION: {
        "description": "Called after each continuation iteration",
        "can_modify": ["response"],
        "return_type": "None",
    },
    HookPoint.LOOP_COMPLETE: {
        "description": "Called when message loop completes",
        "can_modify": ["final_response"],
        "return_type": "None",
    },
    HookPoint.REPAIRABLE_ERROR: {
        "description": "Called when a repairable error occurs",
        "can_modify": ["error", "suggestion"],
        "return_type": "Modified suggestion or None",
    },
    HookPoint.CRITICAL_ERROR: {
        "description": "Called when a critical error occurs",
        "can_modify": ["error"],
        "return_type": "None (logging only)",
    },
    HookPoint.BEFORE_RESPONSE_SEND: {
        "description": "Called before sending response via WebSocket",
        "can_modify": ["response"],
        "return_type": "Modified response or None",
    },
    HookPoint.AFTER_RESPONSE_SEND: {
        "description": "Called after response is sent",
        "can_modify": [],
        "return_type": "None (logging only)",
    },
    HookPoint.SESSION_CREATE: {
        "description": "Called when a new session is created",
        "can_modify": ["session"],
        "return_type": "None",
    },
    HookPoint.SESSION_DESTROY: {
        "description": "Called when a session is destroyed",
        "can_modify": [],
        "return_type": "None (cleanup only)",
    },
    HookPoint.BEFORE_RAG_QUERY: {
        "description": "Called before querying knowledge base",
        "can_modify": ["query"],
        "return_type": "Modified query or None",
    },
    HookPoint.AFTER_RAG_RESULTS: {
        "description": "Called after RAG results are retrieved",
        "can_modify": ["results", "citations"],
        "return_type": "Modified results or None",
    },
    HookPoint.APPROVAL_REQUIRED: {
        "description": "Called when tool requires user approval",
        "can_modify": ["tool_call", "message"],
        "return_type": "True to auto-approve, None for normal flow",
    },
    HookPoint.APPROVAL_RECEIVED: {
        "description": "Called when user approval is received",
        "can_modify": [],
        "return_type": "None (logging only)",
    },
}


def get_hook_metadata(hook: HookPoint) -> dict:
    """
    Get metadata for a hook point.

    Args:
        hook: The hook point

    Returns:
        Dictionary with description, can_modify, and return_type
    """
    return HOOK_METADATA.get(hook, {
        "description": "Unknown hook",
        "can_modify": [],
        "return_type": "None",
    })
