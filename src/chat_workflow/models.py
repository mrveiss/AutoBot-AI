# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Data models for chat workflow management.

Issue #656: Implements Agent Zero's LogItem pattern with StreamingMessage class
for stable message identity and distinct stream/update operations.
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from src.async_chat_workflow import WorkflowMessage


class StreamingOperation(Enum):
    """Type of streaming operation performed."""

    CREATE = "create"  # New message created
    STREAM = "stream"  # Content appended (for LLM tokens)
    UPDATE = "update"  # Content replaced (for progress updates)


@dataclass
class StreamingMessage:
    """
    Message with stable identity for streaming updates.

    Issue #656: Implements Agent Zero's LogItem pattern with distinct
    stream() (append) and update() (replace) operations for cleaner
    streaming message accumulation and deduplication.

    Attributes:
        id: Stable UUID for message identity across updates
        type: Message type (response, thought, planning, progress, etc.)
        content: Current accumulated content
        metadata: Structured key-value pairs
        version: Increments on each update (for frontend deduplication)
        operation: Last operation performed (create, stream, update)

    Usage:
        # For LLM streaming tokens (accumulate)
        msg = StreamingMessage(type="response")
        for chunk in llm_stream:
            msg.stream(chunk)
            yield msg.to_workflow_message()

        # For progress updates (replace)
        progress = StreamingMessage(type="progress")
        progress.update("Step 1/5...")
        yield progress.to_workflow_message()
        progress.update("Step 2/5...")  # Replaces previous
        yield progress.to_workflow_message()
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = "response"
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: int = 0
    operation: StreamingOperation = StreamingOperation.CREATE

    def stream(self, chunk: str) -> "StreamingMessage":
        """
        Append content (for streaming LLM tokens).

        Use this for accumulating LLM response chunks where each chunk
        should be added to the existing content.

        Args:
            chunk: Text chunk to append

        Returns:
            self for method chaining
        """
        self.content += chunk
        self.version += 1
        self.operation = StreamingOperation.STREAM
        return self

    def update(self, content: str) -> "StreamingMessage":
        """
        Replace content (for progress updates).

        Use this for progress messages where each update should replace
        the previous content entirely.

        Args:
            content: New content to replace existing

        Returns:
            self for method chaining
        """
        self.content = content
        self.version += 1
        self.operation = StreamingOperation.UPDATE
        return self

    def set_type(self, message_type: str) -> "StreamingMessage":
        """
        Change the message type.

        Use when transitioning between types (e.g., response → thought).

        Args:
            message_type: New message type

        Returns:
            self for method chaining
        """
        self.type = message_type
        self.version += 1
        return self

    def set_metadata(self, key: str, value: Any) -> "StreamingMessage":
        """
        Set a metadata key-value pair.

        Args:
            key: Metadata key
            value: Metadata value

        Returns:
            self for method chaining
        """
        self.metadata[key] = value
        self.version += 1
        return self

    def merge_metadata(self, updates: Dict[str, Any]) -> "StreamingMessage":
        """
        Merge multiple metadata key-value pairs.

        Args:
            updates: Dictionary of metadata to merge

        Returns:
            self for method chaining
        """
        self.metadata.update(updates)
        self.version += 1
        return self

    def to_workflow_message(self) -> "WorkflowMessage":
        """
        Convert to WorkflowMessage for yielding.

        Returns:
            WorkflowMessage with streaming metadata for frontend handling
        """
        # Import here to avoid circular dependency
        from src.async_chat_workflow import WorkflowMessage

        return WorkflowMessage(
            type=self.type,
            content=self.content,
            id=self.id,  # Use same ID for stable identity
            metadata={
                **self.metadata,
                "message_id": self.id,  # Backwards compat
                "version": self.version,
                "operation": self.operation.value,
                "streaming": True,
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "metadata": self.metadata,
            "version": self.version,
            "operation": self.operation.value,
        }


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
