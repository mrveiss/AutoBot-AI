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

        Issue #716: Applies filter to remove internal continuation prompts
        that LLM sometimes echoes back. These should never be shown to users.

        Returns:
            WorkflowMessage with streaming metadata for frontend handling
        """
        # Import here to avoid circular dependency
        from src.async_chat_workflow import WorkflowMessage

        # Issue #716: Filter internal prompts from content before sending to frontend
        filtered_content = self._filter_internal_prompts(self.content)

        return WorkflowMessage(
            type=self.type,
            content=filtered_content,
            id=self.id,  # Use same ID for stable identity
            metadata={
                **self.metadata,
                "message_id": self.id,  # Backwards compat
                "version": self.version,
                "operation": self.operation.value,
                "streaming": True,
            },
        )

    def _filter_internal_prompts(self, text: str) -> str:
        """Filter out internal continuation prompts that LLM echoes back (Issue #716).

        The LLM sometimes echoes the continuation instructions we send it, which
        should never be shown to the user.

        Args:
            text: Content that may contain echoed internal prompts

        Returns:
            Text with internal prompts removed
        """
        import re

        # Patterns for internal prompts that should not be shown to users
        patterns = [
            re.compile(r"\*\*CRITICAL MULTI-STEP TASK INSTRUCTIONS.*?\*\*YOUR RESPONSE:\*\*", re.DOTALL | re.IGNORECASE),
            re.compile(r"User is in the middle of a multi-step task\. \d+ step\(s\) have been completed\."),
            re.compile(r"\*\*ORIGINAL USER REQUEST \(analyze this.*?\)\:\*\*"),
            re.compile(r"\*\*DECISION PROCESS:\*\*.*?\*\*IF TASK IS COMPLETE\*\*.*?TOOL_CALL", re.DOTALL | re.IGNORECASE),
            re.compile(r"\*\*IF MORE STEPS NEEDED\*\*.*?`<TOOL_CALL", re.DOTALL),
            re.compile(r"---\s*\n\*\*CRITICAL MULTI-STEP.*?---", re.DOTALL | re.IGNORECASE),
        ]

        filtered = text
        for pattern in patterns:
            filtered = pattern.sub("", filtered)

        # Clean up multiple newlines
        filtered = re.sub(r"\n{3,}", "\n\n", filtered)

        return filtered.strip() if filtered != text else text

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
class AgentContext:
    """
    Context for hierarchical agent delegation.

    Issue #657: Implements Agent Zero's subordinate agent pattern where complex
    tasks can be delegated to child agents. This enables better task decomposition
    and parallel execution of independent subtasks.

    Attributes:
        agent_id: Unique identifier for this agent instance
        level: Depth in hierarchy (0 = root, 1+ = subordinates)
        parent_id: ID of parent agent (None for root)
        max_depth: Maximum allowed delegation depth (prevents infinite delegation)
        session_id: Associated chat session ID
        created_at: When this agent context was created

    Usage:
        # Root agent
        root_ctx = AgentContext(agent_id="root", level=0)

        # Subordinate agent
        sub_ctx = AgentContext(
            agent_id="sub-123",
            level=1,
            parent_id="root"
        )
    """

    agent_id: str
    level: int = 0
    parent_id: Optional[str] = None
    max_depth: int = 3
    session_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def can_delegate(self) -> bool:
        """Check if this agent can delegate to subordinates."""
        return self.level < self.max_depth

    def create_subordinate_context(self, subordinate_id: str) -> "AgentContext":
        """
        Create context for a subordinate agent.

        Args:
            subordinate_id: ID for the new subordinate

        Returns:
            New AgentContext for the subordinate

        Raises:
            ValueError: If max delegation depth would be exceeded
        """
        if not self.can_delegate():
            raise ValueError(
                f"Cannot delegate: already at max depth {self.max_depth}"
            )

        return AgentContext(
            agent_id=subordinate_id,
            level=self.level + 1,
            parent_id=self.agent_id,
            max_depth=self.max_depth,
            session_id=self.session_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "agent_id": self.agent_id,
            "level": self.level,
            "parent_id": self.parent_id,
            "max_depth": self.max_depth,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "can_delegate": self.can_delegate(),
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
    agent_context: Optional[AgentContext] = None  # Issue #657: Agent hierarchy


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
