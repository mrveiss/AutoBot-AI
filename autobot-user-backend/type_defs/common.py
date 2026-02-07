# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Common Type Definitions for AutoBot

Provides reusable type definitions to replace generic Dict[str, Any] patterns.
"""

from typing import Any, Dict, List, Optional, Union

# Type alias for timestamp strings (ISO 8601 format)
TimestampStr = str

# JSON-compatible types
# Note: Using Any to avoid Pydantic recursive type alias issues

JSONPrimitive = Union[str, int, float, bool, None]
JSONValue = (
    Any  # Simplified to avoid recursion - represents any JSON-serializable value
)
JSONArray = List[Any]
JSONObject = Dict[str, Any]

# Metadata type - used for generic key-value metadata storage
# More specific than Dict[str, Any] as values must be JSON-serializable
Metadata = Dict[str, Any]

# Metrics dictionary - numeric values with string keys
MetricsDict = Dict[str, Union[int, float]]

# Configuration types
ConfigValue = Union[str, int, float, bool, List[str], Dict[str, str]]
ConfigDict = Dict[str, ConfigValue]

# Search/Filter types
FilterValue = Union[str, int, float, bool, List[str]]
FilterDict = Dict[str, FilterValue]

# Entity ID types (for documentation/clarity)
EntityId = str
SessionId = str
ChatId = str
UserId = str
WorkflowId = str

# Status types
StatusDict = Dict[str, Union[str, bool, int, float, TimestampStr]]

# Error context type
ErrorContext = Dict[str, Union[str, int, float, bool, List[str]]]

# Document/Content types
DocumentContent = Dict[str, Union[str, int, float, List[str], Metadata]]
SearchResult = Dict[str, Union[str, float, int, Metadata]]
SearchResults = List[SearchResult]

# Optional wrapper types for common patterns
OptionalStr = Optional[str]
OptionalInt = Optional[int]
OptionalFloat = Optional[float]
OptionalBool = Optional[bool]
OptionalMetadata = Optional[Metadata]

# Message type constants for chat/streaming systems
# Used for deduplication logic and persistence filtering


class MessageTypes:
    """Constants for message types in the chat system.

    Issue #650: Extended to include display-related types for frontend filtering.
    Aligned with Agent Zero's 13-type message system for better UX.
    """

    # Streaming LLM response types - these accumulate tokens progressively
    LLM_RESPONSE = "llm_response"
    LLM_RESPONSE_CHUNK = "llm_response_chunk"
    RESPONSE = "response"

    # Terminal/command types
    TERMINAL_COMMAND = "terminal_command"
    TERMINAL_OUTPUT = "terminal_output"
    COMMAND_APPROVAL_REQUEST = "command_approval_request"

    # System message types
    SYSTEM = "system"
    ERROR = "error"
    DEFAULT = "default"

    # User message types
    USER = "user"
    TERMINAL_INTERPRETATION = "terminal_interpretation"

    # Issue #650: Display-related types for frontend filtering
    # These types allow users to toggle visibility of different message categories
    THOUGHT = "thought"  # LLM internal reasoning ([THOUGHT]...[/THOUGHT])
    PLANNING = "planning"  # LLM task planning ([PLANNING]...[/PLANNING])
    DEBUG = "debug"  # Debug/diagnostic messages
    UTILITY = "utility"  # Utility/tool status messages
    SOURCES = "sources"  # Knowledge base source references
    PROGRESS = "progress"  # Progress indicators for long-running tasks
    TOOL = "tool"  # Tool execution status
    HINT = "hint"  # Helpful hints/suggestions
    WARNING = "warning"  # Warning messages (non-fatal)
    INFO = "info"  # Informational messages


# Frozenset of message types that should NOT be persisted in websockets.py
# These are either:
# 1. Streaming types that accumulate tokens progressively (persisted once at completion)
# 2. Types explicitly persisted by their source (tool_handler, chat_integration, etc.)
#
# Issue #350 Root Cause Fix: Adding explicitly-persisted types prevents duplication
# from multiple persistence paths (websocket broadcast + explicit persistence).
SKIP_WEBSOCKET_PERSISTENCE_TYPES: frozenset = frozenset(
    [
        # Streaming LLM response types - persisted once at completion
        MessageTypes.LLM_RESPONSE,
        MessageTypes.LLM_RESPONSE_CHUNK,
        MessageTypes.RESPONSE,
        # Terminal types - explicitly persisted by chat_integration.py and service.py
        MessageTypes.TERMINAL_COMMAND,
        MessageTypes.TERMINAL_OUTPUT,
        # Approval request - explicitly persisted by tool_handler.py::_persist_approval_request()
        MessageTypes.COMMAND_APPROVAL_REQUEST,
        # Terminal interpretation - explicitly persisted by llm_handler.py
        MessageTypes.TERMINAL_INTERPRETATION,
    ]
)

# Backwards compatibility alias (deprecated - use SKIP_WEBSOCKET_PERSISTENCE_TYPES)
STREAMING_MESSAGE_TYPES = SKIP_WEBSOCKET_PERSISTENCE_TYPES
