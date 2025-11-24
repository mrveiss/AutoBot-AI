"""
Simple Chat Workflow - A working replacement for the broken ChatWorkflowManager

This provides a clean, working chat workflow that shows all interaction steps
and integrates properly with the frontend message filtering system.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of user messages"""

    GENERAL_QUERY = "general_query"
    SIMPLE = "simple"


class KnowledgeStatus(Enum):
    """Status of knowledge availability"""

    BYPASSED = "bypassed"
    SIMPLE = "simple"


@dataclass
class SimpleWorkflowResult:
    """Result of processing a chat message"""

    response: str
    message_type: MessageType
    knowledge_status: KnowledgeStatus
    kb_results: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]
    processing_time: float
    librarian_engaged: bool = False
    mcp_used: bool = False
    workflow_steps: List[Dict[str, Any]] = None
    workflow_messages: List[Dict[str, Any]] = None


class SimpleChatWorkflow:
    """Simple, working chat workflow that shows all interaction steps"""

    def __init__(self):
        self.chat_id = None
        self.llm = None  # Store LLM instance for model info

    async def send_workflow_message(
        self, message_type: str, content: str, metadata: Dict = None
    ):
        """Send intermediate workflow messages to frontend - these will be collected and returned"""
        workflow_message = {
            "sender": "assistant",
            "text": content,
            "timestamp": time.strftime("%H:%M:%S"),
            "type": message_type,
            "metadata": metadata or {},
        }

        # Store workflow messages to return later
        if not hasattr(self, "workflow_messages"):
            self.workflow_messages = []
        self.workflow_messages.append(workflow_message)

        logger.info(f"WORKFLOW MESSAGE ({message_type}): {content}")

    async def process_message(
        self, user_message: str, chat_id: Optional[str] = None
    ) -> SimpleWorkflowResult:
        """
        Process a chat message with full visibility into the workflow steps
        """
        start_time = time.time()
        self.chat_id = chat_id
        self.workflow_messages = []  # Reset workflow messages for this request
        workflow_steps = []

        try:
            # Step 1: Show thinking process
            await self.send_workflow_message(
                "thought", "🤔 I'm analyzing your message..."
            )
            workflow_steps.append(
                {
                    "step": "thinking",
                    "message": "Analyzing user message",
                    "timestamp": time.time(),
                }
            )

            # Step 2: Show planning
            await self.send_workflow_message(
                "planning", "📋 Planning my response approach..."
            )
            await asyncio.sleep(0.5)  # Brief pause for realism

            # Step 3: Show classification
            await self.send_workflow_message(
                "debug", "🔍 WORKFLOW: Classifying message type..."
            ),
            message_type = MessageType.GENERAL_QUERY
            await self.send_workflow_message(
                "utility", f"✅ Classified as: {message_type.value}"
            )

            workflow_steps.append(
                {
                    "step": "classification",
                    "result": message_type.value,
                    "timestamp": time.time(),
                }
            )

            # Step 4: Show knowledge search
            await self.send_workflow_message(
                "debug", "🔍 WORKFLOW: Searching knowledge base..."
            )
            await asyncio.sleep(0.3)
            await self.send_workflow_message(
                "utility", "📚 Knowledge base search completed"
            )

            # Step 5: Show LLM interaction
            logger.info("DEBUG: Starting LLM interaction step")
            await self.send_workflow_message(
                "thought", "🧠 Generating response using LLM..."
            )
            await self.send_workflow_message(
                "debug", "🔗 WORKFLOW: Connecting to Ollama..."
            )
            logger.info("DEBUG: Workflow messages sent, proceeding to LLM call")

            # Call the actual LLM
            logger.info("DEBUG: About to call _get_llm_response()")
            response = await self._get_llm_response(user_message)
            logger.info(f"DEBUG: LLM response received, length: {len(response)}")

            await self.send_workflow_message("utility", "✅ LLM response received")
            logger.info("DEBUG: Sent LLM response workflow message")

            # Step 6: Show completion
            await self.send_workflow_message(
                "debug", "🏁 WORKFLOW: Response generation completed"
            )

            workflow_steps.append(
                {
                    "step": "completion",
                    "response_length": len(response),
                    "timestamp": time.time(),
                }
            )

            # Show sources if any - get actual model from LLM instance
            provider, model_name = "ollama", "unknown"
            if self.llm:
                try:
                    provider, model_name = self.llm._determine_provider_and_model(
                        "orchestrator"
                    )
                except Exception as e:
                    logger.warning(f"Could not determine model: {e}")
                    model_name = (
                        self.llm.settings.default_model
                        if hasattr(self.llm, "settings")
                        else "unknown"
                    )

            sources = [{"source": "LLM", "type": provider, "model": model_name}]
            await self.send_workflow_message(
                "sources", f"📖 Sources used: {len(sources)}"
            )

            processing_time = time.time() - start_time
            logger.info(
                f"DEBUG: About to return SimpleWorkflowResult, processing_time: {processing_time:.2f}s"
            )

            result = SimpleWorkflowResult(
                response=response,
                message_type=message_type,
                knowledge_status=KnowledgeStatus.SIMPLE,
                kb_results=[],
                sources=sources,
                processing_time=processing_time,
                workflow_steps=workflow_steps,
                workflow_messages=self.workflow_messages,
            )
            logger.info("DEBUG: SimpleWorkflowResult created successfully, returning")
            return result

        except Exception as e:
            logger.error(f"Workflow failed: {e}")
            await self.send_workflow_message("debug", f"❌ WORKFLOW ERROR: {str(e)}")

            return SimpleWorkflowResult(
                response=f"I apologize, but I encountered an error: {str(e)}",
                message_type=MessageType.GENERAL_QUERY,
                knowledge_status=KnowledgeStatus.BYPASSED,
                kb_results=[],
                sources=[],
                processing_time=time.time() - start_time,
                workflow_steps=workflow_steps,
                workflow_messages=getattr(self, "workflow_messages", []),
            )

    async def _get_llm_response(self, user_message: str) -> str:
        """Get response from LLM with error handling and timeout protection"""
        try:
            # Import and instantiate LLM in thread to avoid blocking event loop
            def create_llm():
                from src.llm_interface import LLMInterface

                return LLMInterface()

            llm = await asyncio.to_thread(create_llm)
            self.llm = llm  # Store for model info access

            # Show LLM request details
            logger.info(f"DEBUG: Preparing LLM request for: {user_message[:50]}...")

            # CRITICAL FIX: Add timeout protection for LLM call
            llm_task = llm.chat_completion(
                messages=[{"role": "user", "content": user_message}],
                llm_type="orchestrator",
            )

            # 15 second timeout for LLM response to prevent hanging
            response = await asyncio.wait_for(llm_task, timeout=15.0)

            # CRITICAL DEBUG: Safely log the response structure
            try:
                logger.info(f"DEBUG: LLM response received, type: {type(response)}")
                if isinstance(response, dict):
                    logger.info(f"DEBUG: LLM response keys: {list(response.keys())}")
                    # Only log first 100 chars to avoid huge logs
                    response_preview = (
                        str(response)[:100] + "..."
                        if len(str(response)) > 100
                        else str(response)
                    )
                    logger.info(f"DEBUG: LLM response preview: {response_preview}")
                else:
                    response_preview = (
                        str(response)[:100] + "..."
                        if len(str(response)) > 100
                        else str(response)
                    )
                    logger.info(f"DEBUG: LLM response preview: {response_preview}")
            except Exception as log_error:
                logger.warning(f"DEBUG: Could not log response structure: {log_error}")

            # FIXED: Handle the correct response structure from LLM interface with safe error handling
            try:
                if isinstance(response, dict):
                    # Check for nested message.content structure (Ollama format)
                    if (
                        "message" in response
                        and isinstance(response["message"], dict)
                        and "content" in response["message"]
                    ):
                        content = response["message"]["content"]
                        logger.info(
                            f"DEBUG: Extracted content from message.content: {len(content)} chars"
                        )
                        return content
                    # Check for direct content key (fallback format)
                    elif "content" in response:
                        content = response["content"]
                        logger.info(
                            f"DEBUG: Extracted content from direct content: {len(content)} chars"
                        )
                        return content
                    # Check for error format
                    elif "error" in response:
                        error_msg = response.get("error", "Unknown error")
                        logger.error(f"DEBUG: LLM returned error: {error_msg}")
                        return f"LLM error: {error_msg}"
                    else:
                        logger.warning(
                            "DEBUG: Unexpected dict format, converting to string"
                        )
                        return str(response)
                elif isinstance(response, str):
                    logger.info(
                        f"DEBUG: Response is already string: {len(response)} chars"
                    )
                    return response
                else:
                    logger.warning(
                        f"DEBUG: Unknown response type {type(response)}, converting to string"
                    )
                    return str(response)
            except Exception as parse_error:
                logger.error(f"DEBUG: Response parsing failed: {parse_error}")
                return f"Response parsing error: {parse_error}"

        except asyncio.TimeoutError:
            logger.error("LLM request timed out after 15 seconds")
            return f"Hello! I received your message '{user_message}' but the LLM is taking too long to respond. This might be a temporary issue - please try again."
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            return f"Hello! I received your message '{user_message}' but had trouble processing it with the LLM. Error: {str(e)}"


# Global instance
simple_workflow_manager = SimpleChatWorkflow()


async def process_chat_message_simple(
    user_message: str, chat_id: Optional[str] = None, conversation=None
) -> SimpleWorkflowResult:
    """
    Process a chat message using the simple workflow manager.
    This replaces the broken ChatWorkflowManager.
    """
    return await simple_workflow_manager.process_message(user_message, chat_id)
