"""
Chat Workflow Manager - Centralized Chat Workflow Orchestration

This module provides a centralized manager for chat workflows, integrating
with the existing async chat workflow system and providing a unified interface
for the FastAPI application.

Key Features:
- Integration with async_chat_workflow
- Centralized workflow state management
- Error handling and recovery
- Performance monitoring
- Session management
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from src.async_chat_workflow import AsyncChatWorkflow, WorkflowMessage, MessageType

logger = logging.getLogger(__name__)


@dataclass
class WorkflowSession:
    """Represents an active chat workflow session"""
    session_id: str
    workflow: AsyncChatWorkflow
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    message_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    conversation_history: List[Dict[str, str]] = field(default_factory=list)  # Track conversation context


class ChatWorkflowManager:
    """
    Centralized manager for chat workflows across the application.

    Manages workflow sessions, provides unified interface, and handles
    lifecycle management for chat workflows.
    """

    def __init__(self):
        """Initialize the chat workflow manager."""
        self.sessions: Dict[str, WorkflowSession] = {}
        self.default_workflow: Optional[AsyncChatWorkflow] = None
        self._initialized = False
        self._lock = asyncio.Lock()

        logger.info("ChatWorkflowManager initialized")

    async def initialize(self) -> bool:
        """Initialize the workflow manager with default workflow."""
        try:
            async with self._lock:
                if self._initialized:
                    return True

                # Create default workflow instance
                self.default_workflow = AsyncChatWorkflow()
                self._initialized = True

                logger.info("✅ ChatWorkflowManager initialized successfully")
                return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize ChatWorkflowManager: {e}")
            return False

    async def get_or_create_session(self, session_id: str) -> WorkflowSession:
        """Get existing session or create new one."""
        async with self._lock:
            if session_id not in self.sessions:
                # Create new workflow for this session
                workflow = AsyncChatWorkflow()

                self.sessions[session_id] = WorkflowSession(
                    session_id=session_id,
                    workflow=workflow
                )

                logger.info(f"Created new workflow session: {session_id}")

            # Update last activity
            self.sessions[session_id].last_activity = time.time()
            return self.sessions[session_id]

    async def process_message(
        self,
        session_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[WorkflowMessage]:
        """Process a message through the workflow system."""
        try:
            logger.debug(f"[ChatWorkflowManager] Starting process_message for session={session_id}")
            logger.debug(f"[ChatWorkflowManager] Message: {message[:100]}...")

            session = await self.get_or_create_session(session_id)
            session.message_count += 1
            logger.debug(f"[ChatWorkflowManager] Session message_count: {session.message_count}")

            # ENHANCED LLM CALL with system prompt and context
            logger.debug(f"[ChatWorkflowManager] Using enhanced Ollama call with system prompt")

            try:
                import httpx
                ollama_url = "http://localhost:11434/api/generate"

                # AutoBot system prompt - defines personality and capabilities
                system_prompt = """You are AutoBot, an advanced AI assistant with the following capabilities:

1. **Multi-Agent System**: You can orchestrate specialized agents for different tasks
2. **Knowledge Base**: You have access to a comprehensive knowledge system
3. **Terminal Control**: You can execute system commands and automation
4. **Desktop Control**: You can interact with the desktop environment
5. **Research**: You can browse the web and gather information
6. **NPU Acceleration**: You leverage hardware AI acceleration for performance

**Your Personality**:
- Professional yet approachable
- Technical but clear in explanations
- Proactive in suggesting solutions
- Transparent about your capabilities and limitations

**Response Guidelines**:
- Be concise but complete
- Provide actionable information
- Offer next steps when appropriate
- Ask clarifying questions when needed

"""

                # Add conversation history for context (last 5 messages)
                conversation_context = ""
                if session.conversation_history:
                    conversation_context = "\n**Recent Conversation:**\n"
                    for msg in session.conversation_history[-5:]:  # Last 5 exchanges
                        conversation_context += f"User: {msg['user']}\nAssistant: {msg['assistant']}\n\n"

                # Build complete prompt with system context and history
                full_prompt = system_prompt + conversation_context + f"**Current user message:** {message}\n\nAssistant:"

                async with httpx.AsyncClient(timeout=60.0) as client:
                    # Stream the response from Ollama
                    async with client.stream(
                        "POST",
                        ollama_url,
                        json={
                            "model": "llama3.2:3b-instruct-q4_K_M",
                            "prompt": full_prompt,
                            "stream": True,  # Enable streaming for real-time response
                            "options": {
                                "temperature": 0.7,
                                "top_p": 0.9,
                                "num_ctx": 4096
                            }
                        }
                    ) as response:
                        if response.status_code == 200:
                            llm_response = ""
                            messages = []

                            # Stream response chunks
                            async for line in response.aiter_lines():
                                if line:
                                    try:
                                        import json
                                        chunk_data = json.loads(line)
                                        chunk_text = chunk_data.get("response", "")

                                        if chunk_text:
                                            llm_response += chunk_text

                                            # Yield streaming chunks
                                            from src.async_chat_workflow import WorkflowMessage
                                            messages.append(WorkflowMessage(
                                                type="response",
                                                content=chunk_text,
                                                metadata={
                                                    "message_type": "llm_response_chunk",
                                                    "model": "llama3.2:3b-instruct-q4_K_M",
                                                    "streaming": True
                                                }
                                            ))

                                        # Check if this is the final chunk
                                        if chunk_data.get("done", False):
                                            break

                                    except json.JSONDecodeError as e:
                                        logger.error(f"Failed to parse stream chunk: {e}")
                                        continue

                            logger.debug(f"[ChatWorkflowManager] Completed streaming response: {llm_response[:100]}...")

                            # Store complete exchange in conversation history
                            session.conversation_history.append({
                                "user": message,
                                "assistant": llm_response
                            })

                            # Keep history manageable (max 10 exchanges)
                            if len(session.conversation_history) > 10:
                                session.conversation_history = session.conversation_history[-10:]
                    else:
                        logger.error(f"[ChatWorkflowManager] Ollama request failed: {response.status_code}")
                        from src.async_chat_workflow import WorkflowMessage
                        messages = [WorkflowMessage(
                            type="error",
                            content=f"LLM service error: {response.status_code}",
                            metadata={"error": True}
                        )]

            except Exception as llm_error:
                logger.error(f"[ChatWorkflowManager] Direct LLM call failed: {llm_error}")
                from src.async_chat_workflow import WorkflowMessage
                messages = [WorkflowMessage(
                    type="error",
                    content=f"Failed to connect to LLM: {str(llm_error)}",
                    metadata={"error": True}
                )]

            logger.info(f"Processed message for session {session_id}, got {len(messages)} response messages")
            return messages

        except Exception as e:
            logger.error(f"❌ Error processing message for session {session_id}: {e}", exc_info=True)
            # Return error message
            return [WorkflowMessage(
                type="error",
                content=f"Error processing message: {str(e)}",
                metadata={"error": True, "session_id": session_id}
            )]

    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a session."""
        async with self._lock:
            if session_id not in self.sessions:
                return None

            session = self.sessions[session_id]
            return {
                "session_id": session.session_id,
                "created_at": session.created_at,
                "last_activity": session.last_activity,
                "message_count": session.message_count,
                "uptime": time.time() - session.created_at,
                "metadata": session.metadata
            }

    async def cleanup_inactive_sessions(self, max_age_seconds: int = 3600) -> int:
        """Clean up inactive sessions older than max_age_seconds."""
        current_time = time.time()
        removed_count = 0

        async with self._lock:
            sessions_to_remove = []

            for session_id, session in self.sessions.items():
                if current_time - session.last_activity > max_age_seconds:
                    sessions_to_remove.append(session_id)

            for session_id in sessions_to_remove:
                del self.sessions[session_id]
                removed_count += 1
                logger.info(f"Cleaned up inactive session: {session_id}")

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} inactive sessions")

        return removed_count

    async def get_active_sessions_count(self) -> int:
        """Get count of active sessions."""
        async with self._lock:
            return len(self.sessions)

    async def shutdown(self):
        """Shutdown the workflow manager and clean up resources."""
        try:
            async with self._lock:
                # Clear all sessions
                session_count = len(self.sessions)
                self.sessions.clear()

                # Reset state
                self.default_workflow = None
                self._initialized = False

                logger.info(f"✅ ChatWorkflowManager shutdown complete, cleaned up {session_count} sessions")

        except Exception as e:
            logger.error(f"❌ Error during ChatWorkflowManager shutdown: {e}")


# Global instance for easy access
_workflow_manager: Optional[ChatWorkflowManager] = None


def get_chat_workflow_manager() -> ChatWorkflowManager:
    """Get the global chat workflow manager instance."""
    global _workflow_manager
    if _workflow_manager is None:
        _workflow_manager = ChatWorkflowManager()
    return _workflow_manager


async def initialize_chat_workflow_manager() -> bool:
    """Initialize the global chat workflow manager."""
    manager = get_chat_workflow_manager()
    return await manager.initialize()


# Export main classes and functions
__all__ = [
    "ChatWorkflowManager",
    "WorkflowSession",
    "get_chat_workflow_manager",
    "initialize_chat_workflow_manager"
]