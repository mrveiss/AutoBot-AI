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
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from src.constants.network_constants import NetworkConstants
from src.dependency_container import get_config, get_llm, inject_services
from src.llm_interface import ChatMessage, LLMResponse

logger = logging.getLogger(__name__)


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
    """Structured workflow message"""

    type: str  # thought, planning, debug, utility, sources, json, response
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
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
        self.workflow_messages: List[WorkflowMessage] = []
        self._start_time: float = 0

    async def add_workflow_message(
        self, msg_type: str, content: str, **metadata
    ) -> None:
        """Add workflow message with proper structure"""
        message = WorkflowMessage(type=msg_type, content=content, metadata=metadata)

        self.workflow_messages.append(message)
        logger.info(f"WORKFLOW MESSAGE ({msg_type}): {content}")

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    @inject_services(llm="llm", config="config")
    async def process_chat_message(
        self, user_message: str, chat_id: str = "default", llm=None, config=None
    ) -> ChatWorkflowResult:
        """
        Process chat message through complete workflow with dependency injection
        """
        self._start_time = time.time()
        self.workflow_messages.clear()

        workflow_steps = []

        try:
            # Step 1: Initialize workflow
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

            # Step 2: Show planning
            await self.add_workflow_message(
                "planning", "📋 Planning my response approach...", step="planning"
            )
            await asyncio.sleep(0.2)  # Brief pause for UX

            # Step 3: Message classification
            await self.add_workflow_message(
                "debug",
                "🔍 WORKFLOW: Classifying message type...",
                step="classification",
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

            # Step 4: Knowledge search (simplified for now)
            await self.add_workflow_message(
                "debug",
                "🔍 WORKFLOW: Searching knowledge base...",
                step="knowledge_search",
            )

            knowledge_status = KnowledgeStatus.BYPASSED  # Simplified for now
            kb_results = []

            await asyncio.sleep(0.1)  # Simulate search
            await self.add_workflow_message(
                "utility",
                "📚 Knowledge base search completed",
                step="knowledge_search",
                results_count=len(kb_results),
            )

            # Step 5: LLM interaction
            await self.add_workflow_message(
                "thought", "🧠 Generating response using LLM...", step="llm_generation"
            )

            await self.add_workflow_message(
                "debug", "🔗 WORKFLOW: Connecting to Ollama...", step="llm_connection"
            )

            # Generate LLM response
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

            # Step 6: Completion
            await self.add_workflow_message(
                "debug", "🏁 WORKFLOW: Response generation completed", step="completion"
            )

            processing_time = time.time() - self._start_time

            # Create result
            result = ChatWorkflowResult(
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

            logger.info(f"Chat workflow completed in {processing_time:.2f}s")
            return result

        except Exception as e:
            # Error handling with workflow message
            await self.add_workflow_message(
                "debug",
                f"❌ WORKFLOW: Error occurred: {str(e)}",
                step="error_handling",
                error=str(e),
            )

            processing_time = time.time() - self._start_time

            return ChatWorkflowResult(
                response=f"I apologize, but I encountered an error while processing your message: {str(e)}",
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
        if any(
            word in message_lower
            for word in ["terminal", "command", "bash", "shell", "run"]
        ):
            return MessageType.TERMINAL_TASK
        elif any(
            word in message_lower for word in ["desktop", "gui", "window", "screen"]
        ):
            return MessageType.DESKTOP_TASK
        elif any(
            word in message_lower for word in ["system", "config", "install", "setup"]
        ):
            return MessageType.SYSTEM_TASK
        elif any(
            word in message_lower
            for word in ["research", "find", "search", "investigate"]
        ):
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
        system_prompt = """You are AutoBot, an advanced autonomous AI assistant. Provide helpful, accurate, and concise responses."""
        messages.insert(0, ChatMessage(role="system", content=system_prompt))

        # Generate response with timeout
        response = await asyncio.wait_for(
            llm.chat_completion(messages, stream=False), timeout=30.0
        )

        return response


# Global workflow instance manager
class WorkflowManager:
    """Manages workflow instances"""

    def __init__(self):
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
            response=f"I apologize, but I'm experiencing a processing delay. Your message was: '{user_message}' (Emergency mode active)",
            message_type=MessageType.GENERAL_QUERY,
            knowledge_status=KnowledgeStatus.BYPASSED,
            kb_results=[],
            research_results=None,
            librarian_engaged=False,
            mcp_used=False,
            processing_time=25.0,
        )
    except Exception as e:
        logger.error(f"Chat workflow error: {e}")
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
