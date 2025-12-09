# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Data models for chat workflow management.
"""

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from src.async_chat_workflow import WorkflowMessage


@dataclass
class LLMIterationContext:
    """
    Context for LLM continuation iterations.

    Issue #375: Groups related parameters passed through multiple methods
    in the LLM continuation loop to reduce long parameter lists.
    """

    ollama_endpoint: str
    selected_model: str
    session_id: str
    terminal_session_id: str
    used_knowledge: bool
    rag_citations: List[Dict[str, Any]]
    workflow_messages: List["WorkflowMessage"]
    execution_history: List[Dict[str, Any]] = field(default_factory=list)
    system_prompt: Optional[str] = None
    initial_prompt: Optional[str] = None
    message: Optional[str] = None


@dataclass
class WorkflowSession:
    """Represents an active chat workflow session"""

    session_id: str
    workflow: Any  # AsyncChatWorkflow instance
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    message_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    conversation_history: List[Dict[str, str]] = field(
        default_factory=list
    )  # Track conversation context
