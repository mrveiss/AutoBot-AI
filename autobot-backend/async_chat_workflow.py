#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Async Chat Workflow using modern dependency injection and async patterns
Replaces SimpleChatWorkflow with proper async architecture
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from constants.threshold_constants import TimingConstants
from dependency_container import inject_services
from llm_interface import ChatMessage, LLMResponse
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for message classification keywords (Issue #326)
TERMINAL_KEYWORDS = {"terminal", "command", "bash", "shell", "run"}
DESKTOP_KEYWORDS = {"desktop", "gui", "window", "screen"}
SYSTEM_KEYWORDS = {"system", "config", "install", "setup"}
RESEARCH_KEYWORDS = {"research", "find", "search", "investigate"}


class MessageType(Enum):
    """Message classification types"""

    GENERAL_QUERY = "general_query"
    TERMINAL_TASK = "terminal_task"
    DESKTOP_TASK = "desktop_task"
    SYSTEM_TASK = "system_task"
    RESEARCH_NEEDED = "research_needed"


class KnowledgeStatus(Enum):
    """Knowledge availability status"""

    FOUND = "found"
    PARTIAL = "partial"
    MISSING = "missing"
    BYPASSED = "bypassed"


@dataclass
class WorkflowMessage:
    """Structured workflow message.

    Issue #650: Added unique `id` field for message deduplication and tracking.
    """

    type: str  # thought, planning, debug, utility, sources, json, response
    content: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))  # Issue #650: Unique ID
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "id": self.id,  # Issue #650: Include ID for frontend deduplication
            "type": self.type,
            "content": (
                self.content
            ),  # Changed from 'text' to 'content' for frontend compatibility
            "sender": "assistant",
            "timestamp": time.strftime("%H:%M:%S", time.localtime(self.timestamp)),
            "metadata": self.metadata,
        }


@dataclass
class ChatWorkflowResult:
    """Complete workflow result"""

    response: str
    message_type: MessageType
    knowledge_status: KnowledgeStatus
    kb_results: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    processing_time: float = 0.0
    workflow_steps: List[Dict[str, Any]] = field(default_factory=list)
    workflow_messages: List[WorkflowMessage] = field(default_factory=list)
    librarian_engaged: bool = False
    mcp_used: bool = False
    conversation_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "response": self.response,
            "message_type": self.message_type.value,
            "knowledge_status": self.knowledge_status.value,
            "kb_results": self.kb_results,
            "sources": self.sources,
            "kb_results_count": len(self.kb_results),
            "processing_time": self.processing_time,
            "workflow_steps": self.workflow_steps,
            "workflow_messages": [msg.to_dict() for msg in self.workflow_messages],
            "librarian_engaged": self.librarian_engaged,
            "mcp_used": self.mcp_used,
            "conversation_id": self.conversation_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }


class AsyncChatWorkflow:
    """
    Async chat workflow with dependency injection and modern async patterns
    """

    def __init__(self):
        """Initialize async chat workflow with message tracking."""
        self.workflow_messages: List[WorkflowMessage] = []
        self._start_time: float = 0

    async def add_workflow_message(
        self, msg_type: str, content: str, **metadata
    ) -> None:
        """Add workflow message with proper structure"""
        message = WorkflowMessage(type=msg_type, content=content, metadata=metadata)

        self.workflow_messages.append(message)
        logger.info("WORKFLOW MESSAGE (%s): %s", msg_type, content)

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    @inject_services(llm="llm", config="config")
    async def process_chat_message(
        self, user_message: str, chat_id: str = "default", llm=None, config=None
    ) -> ChatWorkflowResult:
        """
        Process chat message through complete workflow with dependency injection.

        Issue #281: Refactored from 152 lines to use extracted helper methods
        for each workflow stage.
        """
        self._start_time = time.time()
        self.workflow_messages.clear()
        workflow_steps: List[Dict[str, Any]] = []

        try:
            # Stage 1: Initialize and classify
            await self._workflow_initialize(workflow_steps)
            message_type = await self._workflow_classify(user_message, workflow_steps)

            # Stage 2: Knowledge search
            knowledge_status, kb_results = await self._workflow_knowledge_search()

            # Stage 3: LLM response generation
            llm_response = await self._workflow_llm_generate(
                user_message, llm, workflow_steps
            )

            # Stage 4: Build and return result
            return self._build_success_result(
                llm_response,
                message_type,
                knowledge_status,
                kb_results,
                workflow_steps,
                chat_id,
            )

        except Exception as e:
            return await self._build_error_result(e, workflow_steps, chat_id)

    async def _workflow_initialize(self, workflow_steps: List[Dict[str, Any]]) -> None:
        """Initialize workflow with status messages. Issue #281: Extracted helper."""
        await self.add_workflow_message(
            "thought", "🤔 I'm analyzing your message...", step="initialization"
        )
        workflow_steps.append(
            {
                "step": "initialization",
                "status": "completed",
                "timestamp": time.time(),
            }
        )
        await self.add_workflow_message(
            "planning", "📋 Planning my response approach...", step="planning"
        )

    async def _workflow_classify(
        self, user_message: str, workflow_steps: List[Dict[str, Any]]
    ) -> MessageType:
        """Classify message and log workflow step. Issue #281: Extracted helper."""
        await self.add_workflow_message(
            "debug", "🔍 WORKFLOW: Classifying message type...", step="classification"
        )
        message_type = await self._classify_message(user_message)
        await self.add_workflow_message(
            "utility",
            f"✅ Classified as: {message_type.value}",
            step="classification",
            result=message_type.value,
        )
        workflow_steps.append(
            {
                "step": "classification",
                "result": message_type.value,
                "timestamp": time.time(),
            }
        )
        return message_type

    async def _workflow_knowledge_search(
        self,
    ) -> tuple[KnowledgeStatus, List[Dict[str, Any]]]:
        """Search knowledge base. Issue #281: Extracted helper."""
        await self.add_workflow_message(
            "debug", "🔍 WORKFLOW: Searching knowledge base...", step="knowledge_search"
        )
        knowledge_status = KnowledgeStatus.BYPASSED  # Simplified for now
        kb_results: List[Dict[str, Any]] = []
        await self.add_workflow_message(
            "utility",
            "📚 Knowledge base search completed",
            step="knowledge_search",
            results_count=len(kb_results),
        )
        return knowledge_status, kb_results

    async def _workflow_llm_generate(
        self, user_message: str, llm, workflow_steps: List[Dict[str, Any]]
    ) -> LLMResponse:
        """Generate LLM response and log workflow step. Issue #281: Extracted helper."""
        await self.add_workflow_message(
            "thought", "🧠 Generating response using LLM...", step="llm_generation"
        )
        await self.add_workflow_message(
            "debug", "🔗 WORKFLOW: Connecting to Ollama...", step="llm_connection"
        )
        llm_response = await self._generate_llm_response(user_message, llm)
        await self.add_workflow_message(
            "utility",
            "✅ LLM response received",
            step="llm_generation",
            response_length=len(llm_response.content),
            model=llm_response.model,
            processing_time=llm_response.processing_time,
        )
        workflow_steps.append(
            {
                "step": "llm_generation",
                "model": llm_response.model,
                "tokens_used": llm_response.tokens_used,
                "processing_time": llm_response.processing_time,
                "timestamp": time.time(),
            }
        )
        return llm_response

    def _build_success_result(
        self,
        llm_response: LLMResponse,
        message_type: MessageType,
        knowledge_status: KnowledgeStatus,
        kb_results: List[Dict[str, Any]],
        workflow_steps: List[Dict[str, Any]],
        chat_id: str,
    ) -> ChatWorkflowResult:
        """Build successful workflow result. Issue #281: Extracted helper."""
        processing_time = time.time() - self._start_time
        logger.info("Chat workflow completed in %.2fs", processing_time)
        return ChatWorkflowResult(
            response=llm_response.content,
            message_type=message_type,
            knowledge_status=knowledge_status,
            kb_results=kb_results,
            sources=[],
            processing_time=processing_time,
            workflow_steps=workflow_steps,
            workflow_messages=self.workflow_messages.copy(),
            librarian_engaged=False,
            mcp_used=False,
            conversation_id=chat_id,
        )

    async def _build_error_result(
        self, error: Exception, workflow_steps: List[Dict[str, Any]], chat_id: str
    ) -> ChatWorkflowResult:
        """Build error workflow result. Issue #281: Extracted helper."""
        await self.add_workflow_message(
            "debug",
            f"❌ WORKFLOW: Error occurred: {str(error)}",
            step="error_handling",
            error=str(error),
        )
        processing_time = time.time() - self._start_time
        return ChatWorkflowResult(
            response=(
                f"I apologize, but I encountered an error while processing your message:"
                f"{str(error)}"
            ),
            message_type=MessageType.GENERAL_QUERY,
            knowledge_status=KnowledgeStatus.BYPASSED,
            processing_time=processing_time,
            workflow_steps=workflow_steps,
            workflow_messages=self.workflow_messages.copy(),
            conversation_id=chat_id,
        )

    async def _classify_message(self, message: str) -> MessageType:
        """Classify message type (simplified implementation)"""
        message_lower = message.lower()

        # Simple keyword-based classification
        if any(word in message_lower for word in TERMINAL_KEYWORDS):
            return MessageType.TERMINAL_TASK
        elif any(word in message_lower for word in DESKTOP_KEYWORDS):
            return MessageType.DESKTOP_TASK
        elif any(word in message_lower for word in SYSTEM_KEYWORDS):
            return MessageType.SYSTEM_TASK
        elif any(word in message_lower for word in RESEARCH_KEYWORDS):
            return MessageType.RESEARCH_NEEDED
        else:
            return MessageType.GENERAL_QUERY

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def _generate_llm_response(self, user_message: str, llm) -> LLMResponse:
        """Generate LLM response with retry logic"""

        # Prepare chat messages
        messages = [ChatMessage(role="user", content=user_message)]

        # Add system prompt for AutoBot context
        system_prompt = (
            "You are AutoBot, an advanced autonomous AI assistant. "
            "Provide helpful, accurate, and concise responses."
        )
        messages.insert(0, ChatMessage(role="system", content=system_prompt))

        # Generate response with timeout
        response = await asyncio.wait_for(
            llm.chat_completion(messages, stream=False),
            timeout=TimingConstants.SHORT_TIMEOUT,
        )

        return response


# Global workflow instance manager
class WorkflowManager:
    """Manages workflow instances"""

    def __init__(self):
        """Initialize workflow manager with async lock."""
        self._instance: Optional[AsyncChatWorkflow] = None
        self._lock = asyncio.Lock()

    async def get_workflow(self) -> AsyncChatWorkflow:
        """Get workflow instance"""
        if self._instance is None:
            async with self._lock:
                if self._instance is None:
                    self._instance = AsyncChatWorkflow()

        return self._instance


# Global workflow manager
workflow_manager = WorkflowManager()


# Convenience function
async def process_chat_message(
    user_message: str, chat_id: str = "default"
) -> ChatWorkflowResult:
    """Process chat message through async workflow"""
    try:
        # Add timeout protection to prevent hanging - maximum 25 seconds
        workflow = await workflow_manager.get_workflow()
        result = await asyncio.wait_for(
            workflow.process_chat_message(user_message, chat_id), timeout=25.0
        )
        return result
    except asyncio.TimeoutError:
        logger.error(
            f"Chat workflow timed out after 25 seconds for message: {user_message[:50]}..."
        )
        # Return emergency fallback response
        return ChatWorkflowResult(
            response=(
                f"I apologize, but I'm experiencing a processing delay. Your message was:"
                f"'{user_message}' (Emergency mode active)"
            ),
            message_type=MessageType.GENERAL_QUERY,
            knowledge_status=KnowledgeStatus.BYPASSED,
            kb_results=[],
            research_results=None,
            librarian_engaged=False,
            mcp_used=False,
            processing_time=25.0,
        )
    except Exception as e:
        logger.error("Chat workflow error: %s", e)
        return ChatWorkflowResult(
            response=f"I encountered an error processing your message. Error: {str(e)}",
            message_type=MessageType.GENERAL_QUERY,
            knowledge_status=KnowledgeStatus.BYPASSED,
            kb_results=[],
            research_results=None,
            librarian_engaged=False,
            mcp_used=False,
            processing_time=0.1,
        )
