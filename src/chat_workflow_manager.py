"""
Chat Workflow Manager - Centralized Chat Workflow Orchestration

This module provides a centralized manager for chat workflows, integrating
with the existing async chat workflow system and providing a unified interface
for the FastAPI application.

Key Features:
- Integration with async_chat_workflow
- Centralized workflow state management
- Redis-backed conversation history persistence
- Error handling and recovery
- Performance monitoring
- Session management
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from src.async_chat_workflow import AsyncChatWorkflow, WorkflowMessage, MessageType
from src.utils.redis_client import get_redis_client
from src.prompt_manager import get_prompt

logger = logging.getLogger(__name__)

# Exit intent detection keywords
EXIT_KEYWORDS = {
    "goodbye", "bye", "exit", "quit", "end chat", "stop",
    "that's all", "thanks goodbye", "bye bye", "see you",
    "farewell", "good bye", "later", "end conversation",
    "no more", "i'm done", "im done", "close chat"
}

def detect_exit_intent(message: str) -> bool:
    """
    Detect if user explicitly wants to end the conversation.

    Args:
        message: User's message

    Returns:
        True if user explicitly wants to exit, False otherwise
    """
    message_lower = message.lower().strip()

    # Check for exact exit phrases
    if message_lower in EXIT_KEYWORDS:
        logger.info(f"Exit intent detected: '{message_lower}'")
        return True

    # Check for exit keywords in message (with word boundaries)
    words = message_lower.split()
    for exit_word in EXIT_KEYWORDS:
        if exit_word in words:
            # Only consider it an exit if it's not part of a question
            if "?" not in message:
                logger.info(f"Exit intent detected from keyword: '{exit_word}'")
                return True

    return False


def detect_user_intent(message: str, conversation_history: List[Dict[str, str]] = None) -> str:
    """
    Detect user's intent to select appropriate context prompt.

    Args:
        message: User's message
        conversation_history: Previous conversation messages for context

    Returns:
        Intent type: 'installation', 'architecture', 'troubleshooting', 'api', or 'general'
    """
    message_lower = message.lower().strip()

    # Installation intent keywords
    installation_keywords = {
        "install", "setup", "configure", "deployment", "deploy",
        "first time", "getting started", "how to start", "run autobot",
        "start autobot", "vm setup", "distributed setup"
    }

    # Architecture intent keywords
    architecture_keywords = {
        "architecture", "design", "why", "how does", "how is",
        "vm", "virtual machine", "distributed", "infrastructure",
        "service", "component", "system design", "how many"
    }

    # Troubleshooting intent keywords
    troubleshooting_keywords = {
        "error", "issue", "problem", "not working", "broken",
        "failed", "fail", "crash", "timeout", "can't", "cannot",
        "stuck", "help", "fix", "debug", "troubleshoot"
    }

    # API intent keywords
    api_keywords = {
        "api", "endpoint", "request", "response", "integration",
        "curl", "http", "rest", "websocket", "stream",
        "documentation", "docs", "how to call", "how to use"
    }

    # Count keyword matches for each intent
    intent_scores = {
        'installation': sum(1 for kw in installation_keywords if kw in message_lower),
        'architecture': sum(1 for kw in architecture_keywords if kw in message_lower),
        'troubleshooting': sum(1 for kw in troubleshooting_keywords if kw in message_lower),
        'api': sum(1 for kw in api_keywords if kw in message_lower)
    }

    # Check conversation context for intent continuation
    if conversation_history and len(conversation_history) > 0:
        # Get last assistant response to maintain context
        last_responses = [msg.get('assistant', '') for msg in conversation_history[-2:]]
        context = ' '.join(last_responses).lower()

        # Boost scores based on conversation context
        if any(kw in context for kw in installation_keywords):
            intent_scores['installation'] += 0.5
        if any(kw in context for kw in architecture_keywords):
            intent_scores['architecture'] += 0.5
        if any(kw in context for kw in troubleshooting_keywords):
            intent_scores['troubleshooting'] += 0.5
        if any(kw in context for kw in api_keywords):
            intent_scores['api'] += 0.5

    # Find highest scoring intent
    max_score = max(intent_scores.values())

    if max_score > 0:
        detected_intent = max(intent_scores, key=intent_scores.get)
        logger.debug(f"Intent detected: {detected_intent} (score: {max_score}) for message: {message[:50]}...")
        return detected_intent

    # Default to general if no specific intent detected
    logger.debug(f"No specific intent detected, using general context for: {message[:50]}...")
    return 'general'


def select_context_prompt(intent: str, base_prompt: str) -> str:
    """
    Select and combine appropriate context prompt based on detected intent.

    Args:
        intent: Detected user intent
        base_prompt: Base system prompt

    Returns:
        Combined prompt with base + context-specific instructions
    """
    context_prompt_map = {
        'installation': 'chat.installation_help',
        'architecture': 'chat.architecture_explanation',
        'troubleshooting': 'chat.troubleshooting',
        'api': 'chat.api_documentation'
    }

    # If general intent, return base prompt only
    if intent == 'general' or intent not in context_prompt_map:
        logger.debug("Using base system prompt (general context)")
        return base_prompt

    # Load context-specific prompt
    try:
        context_key = context_prompt_map[intent]
        context_prompt = get_prompt(context_key)
        logger.info(f"Loaded context prompt: {context_key} for intent: {intent}")

        # Combine base prompt with context-specific prompt
        combined_prompt = f"""{base_prompt}

---

## CONTEXT-SPECIFIC GUIDANCE

{context_prompt}

---

**Remember**: Follow both the general conversation management rules above AND the context-specific guidance for this {intent} conversation."""

        return combined_prompt

    except Exception as e:
        logger.warning(f"Failed to load context prompt for intent '{intent}': {e}")
        logger.warning("Falling back to base system prompt")
        return base_prompt


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
        self.redis_client = None
        self.conversation_history_ttl = 86400  # 24 hours in seconds
        self.transcript_dir = "data/conversation_transcripts"  # Long-term file storage

        logger.info("ChatWorkflowManager initialized")

    def _get_conversation_key(self, session_id: str) -> str:
        """Generate Redis key for conversation history."""
        return f"chat:conversation:{session_id}"

    async def _load_conversation_history(self, session_id: str) -> List[Dict[str, str]]:
        """Load conversation history from Redis (short-term) or file (long-term)."""
        try:
            # Try Redis first (fast access for recent conversations)
            if self.redis_client is not None:
                key = self._get_conversation_key(session_id)
                history_json = self.redis_client.get(key)

                if history_json:
                    logger.debug(f"Loaded conversation history from Redis for session {session_id}")
                    return json.loads(history_json)

            # Fall back to file-based transcript (long-term storage)
            history = await self._load_transcript(session_id)
            if history:
                logger.debug(f"Loaded conversation history from file for session {session_id}")
                # Repopulate Redis cache
                if self.redis_client is not None:
                    await self._save_conversation_history(session_id, history)

            return history

        except Exception as e:
            logger.error(f"Failed to load conversation history: {e}")
            return []

    async def _save_conversation_history(self, session_id: str, history: List[Dict[str, str]]):
        """Save conversation history to Redis with TTL."""
        try:
            if self.redis_client is None:
                return

            key = self._get_conversation_key(session_id)
            history_json = json.dumps(history)

            # Save with 24-hour expiration
            self.redis_client.setex(key, self.conversation_history_ttl, history_json)
            logger.debug(f"Saved conversation history for session {session_id} to Redis")

        except Exception as e:
            logger.error(f"Failed to save conversation history to Redis: {e}")

    def _get_transcript_path(self, session_id: str) -> Path:
        """Get file path for conversation transcript."""
        return Path(self.transcript_dir) / f"{session_id}.json"

    async def _append_to_transcript(self, session_id: str, user_message: str, assistant_message: str):
        """Append message exchange to long-term transcript file."""
        try:
            # Ensure transcript directory exists
            transcript_dir = Path(self.transcript_dir)
            transcript_dir.mkdir(parents=True, exist_ok=True)

            transcript_path = self._get_transcript_path(session_id)

            # Load existing transcript or create new
            if transcript_path.exists():
                with open(transcript_path, 'r', encoding='utf-8') as f:
                    transcript = json.load(f)
            else:
                transcript = {
                    "session_id": session_id,
                    "created_at": datetime.now().isoformat(),
                    "messages": []
                }

            # Append new exchange
            transcript["messages"].append({
                "timestamp": datetime.now().isoformat(),
                "user": user_message,
                "assistant": assistant_message
            })

            transcript["updated_at"] = datetime.now().isoformat()
            transcript["message_count"] = len(transcript["messages"])

            # Save transcript
            with open(transcript_path, 'w', encoding='utf-8') as f:
                json.dump(transcript, f, indent=2, ensure_ascii=False)

            logger.debug(f"Appended to transcript for session {session_id} ({transcript['message_count']} total messages)")

        except Exception as e:
            logger.error(f"Failed to append to transcript file: {e}")

    async def _load_transcript(self, session_id: str) -> List[Dict[str, str]]:
        """Load conversation history from transcript file."""
        try:
            transcript_path = self._get_transcript_path(session_id)

            if not transcript_path.exists():
                return []

            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript = json.load(f)

            # Convert to simple history format (last 10 messages)
            messages = transcript.get("messages", [])[-10:]
            return [{"user": msg["user"], "assistant": msg["assistant"]} for msg in messages]

        except Exception as e:
            logger.error(f"Failed to load transcript file: {e}")
            return []

    async def initialize(self) -> bool:
        """Initialize the workflow manager with default workflow and Redis."""
        try:
            async with self._lock:
                if self._initialized:
                    return True

                # Initialize Redis client for conversation history
                try:
                    self.redis_client = get_redis_client(async_client=False, database="main")
                    if self.redis_client:
                        logger.info("✅ Redis client initialized for conversation history")
                    else:
                        logger.warning("⚠️ Redis not available - conversation history will not persist")
                except Exception as redis_error:
                    logger.warning(f"⚠️ Redis initialization failed: {redis_error} - continuing without persistence")
                    self.redis_client = None

                # Create default workflow instance
                self.default_workflow = AsyncChatWorkflow()
                self._initialized = True

                logger.info("✅ ChatWorkflowManager initialized successfully")
                return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize ChatWorkflowManager: {e}")
            return False

    async def get_or_create_session(self, session_id: str) -> WorkflowSession:
        """Get existing session or create new one, loading history from Redis."""
        async with self._lock:
            if session_id not in self.sessions:
                # Create new workflow for this session
                workflow = AsyncChatWorkflow()

                # Load conversation history from Redis
                conversation_history = await self._load_conversation_history(session_id)

                self.sessions[session_id] = WorkflowSession(
                    session_id=session_id,
                    workflow=workflow,
                    conversation_history=conversation_history
                )

                logger.info(f"Created new workflow session: {session_id} with {len(conversation_history)} messages from history")

            # Update last activity
            self.sessions[session_id].last_activity = time.time()
            return self.sessions[session_id]

    async def process_message(
        self,
        session_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[WorkflowMessage]:
        """Process a message through the workflow system and return all messages."""
        messages = []
        async for msg in self.process_message_stream(session_id, message, context):
            messages.append(msg)
        return messages

    async def process_message_stream(
        self,
        session_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """Process a message through the workflow system as an async generator (for streaming)."""
        try:
            logger.debug(f"[ChatWorkflowManager] Starting process_message_stream for session={session_id}")
            logger.debug(f"[ChatWorkflowManager] Message: {message[:100]}...")

            session = await self.get_or_create_session(session_id)
            session.message_count += 1
            logger.debug(f"[ChatWorkflowManager] Session message_count: {session.message_count}")

            # CRITICAL: Check for explicit exit intent before processing
            user_wants_exit = detect_exit_intent(message)

            if user_wants_exit:
                logger.info(f"[ChatWorkflowManager] User explicitly requested to exit conversation: {session_id}")
                # Provide polite goodbye message
                yield WorkflowMessage(
                    type="response",
                    content="Goodbye! Feel free to return anytime if you need assistance. Take care!",
                    metadata={
                        "message_type": "exit_acknowledgment",
                        "exit_detected": True
                    }
                )
                return  # End conversation only when user explicitly wants to exit

            # ENHANCED LLM CALL with system prompt and context
            logger.debug(f"[ChatWorkflowManager] Using enhanced Ollama call with system prompt from prompt file")

            try:
                import httpx
                ollama_url = "http://localhost:11434/api/generate"

                # Load AutoBot system prompt from prompt file (with conversation continuation rules)
                try:
                    base_system_prompt = get_prompt("chat.system_prompt")
                    logger.debug("[ChatWorkflowManager] Loaded base system prompt from prompts/chat/system_prompt.md")
                except Exception as prompt_error:
                    logger.error(f"Failed to load system prompt from file: {prompt_error}")
                    # Fallback to minimal prompt if file loading fails
                    base_system_prompt = """You are AutoBot, a helpful AI assistant.

CRITICAL: NEVER end conversations prematurely. Only say goodbye when user explicitly says goodbye, bye, exit, or quit.
If a user gives short responses like "of autobot" or "yes", they are clarifying or continuing the conversation - keep helping them!"""

                # CONTEXT-AWARE PROMPT SELECTION
                # Detect user intent based on message and conversation history
                user_intent = detect_user_intent(message, session.conversation_history)
                logger.info(f"[ChatWorkflowManager] Detected user intent: {user_intent}")

                # Select appropriate context prompt based on intent
                system_prompt = select_context_prompt(user_intent, base_system_prompt)

                # Add conversation history for context (last 5 messages)
                conversation_context = ""
                if session.conversation_history:
                    conversation_context = "\n**Recent Conversation:**\n"
                    for msg in session.conversation_history[-5:]:  # Last 5 exchanges
                        conversation_context += f"User: {msg['user']}\nAssistant: {msg['assistant']}\n\n"

                # Build complete prompt with system context and history
                full_prompt = system_prompt + conversation_context + f"\n**Current user message:** {message}\n\nAssistant:"

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

                            # Stream response chunks as they arrive
                            async for line in response.aiter_lines():
                                if line:
                                    try:
                                        import json
                                        chunk_data = json.loads(line)
                                        chunk_text = chunk_data.get("response", "")

                                        if chunk_text:
                                            llm_response += chunk_text

                                            # Yield streaming chunks in real-time
                                            from src.async_chat_workflow import WorkflowMessage
                                            yield WorkflowMessage(
                                                type="response",
                                                content=chunk_text,
                                                metadata={
                                                    "message_type": "llm_response_chunk",
                                                    "model": "llama3.2:3b-instruct-q4_K_M",
                                                    "streaming": True
                                                }
                                            )

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

                            # Persist to both Redis (short-term cache) and file (long-term storage)
                            await self._save_conversation_history(session_id, session.conversation_history)
                            await self._append_to_transcript(session_id, message, llm_response)
                        else:
                            logger.error(f"[ChatWorkflowManager] Ollama request failed: {response.status_code}")
                            from src.async_chat_workflow import WorkflowMessage
                            yield WorkflowMessage(
                                type="error",
                                content=f"LLM service error: {response.status_code}",
                                metadata={"error": True}
                            )

            except Exception as llm_error:
                logger.error(f"[ChatWorkflowManager] Direct LLM call failed: {llm_error}")
                from src.async_chat_workflow import WorkflowMessage
                yield WorkflowMessage(
                    type="error",
                    content=f"Failed to connect to LLM: {str(llm_error)}",
                    metadata={"error": True}
                )

        except Exception as e:
            logger.error(f"❌ Error processing message for session {session_id}: {e}", exc_info=True)
            # Yield error message
            from src.async_chat_workflow import WorkflowMessage
            yield WorkflowMessage(
                type="error",
                content=f"Error processing message: {str(e)}",
                metadata={"error": True, "session_id": session_id}
            )

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