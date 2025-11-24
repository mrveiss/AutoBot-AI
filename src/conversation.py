# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation Class with Knowledge Base Integration and Source Tracking
Provides comprehensive conversation state management and grounded responses
"""

import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents import get_kb_librarian
from src.agents.classification_agent import ClassificationAgent, ClassificationResult
from src.agents.llm_failsafe_agent import get_robust_llm_response
from src.autobot_types import TaskComplexity
from src.constants.network_constants import NetworkConstants
from src.research_browser_manager import research_browser_manager
from src.source_attribution import (
    SourceType,
    clear_sources,
    get_attribution,
    source_manager,
    track_source,
)
from src.unified_config_manager import config as global_config_manager

logger = logging.getLogger(__name__)


@dataclass
class ConversationMessage:
    """Individual message in a conversation"""

    message_id: str
    role: str  # 'user', 'assistant', 'system'
    content: str
    timestamp: datetime
    message_type: str = "chat"  # chat, thought, planning, utility, debug, source
    metadata: Dict[str, Any] = None
    sources: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.sources is None:
            self.sources = []


@dataclass
class ConversationState:
    """Current state of conversation processing"""

    conversation_id: str
    classification: Optional[ClassificationResult] = None
    kb_context: List[Dict[str, Any]] = None
    sources_used: List[Dict[str, Any]] = None
    total_tokens: int = 0
    processing_time: float = 0.0
    status: str = "active"  # active, completed, error

    def __post_init__(self):
        if self.kb_context is None:
            self.kb_context = []
        if self.sources_used is None:
            self.sources_used = []


class Conversation:
    """
    Comprehensive conversation management with KB integration and source tracking
    """

    def __init__(self, conversation_id: str = None):
        self.conversation_id = conversation_id or str(uuid.uuid4())
        self.messages: List[ConversationMessage] = []
        self.state = ConversationState(conversation_id=self.conversation_id)
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

        # Initialize agents
        self._initialize_classification_agent()
        self.kb_librarian = None  # Lazy loaded

        # Conversation settings
        self.max_kb_results = 5
        self.kb_timeout = 8.0  # Reduced from 10s to 8s - should be longer than KB circuit breaker (5s)
        self.include_sources = True

        logger.info(f"Created conversation {self.conversation_id}")

    def _initialize_classification_agent(self):
        """Initialize the appropriate classification agent based on configuration."""
        try:
            # Check if Gemma classification is enabled
            use_gemma = global_config_manager.get_nested(
                "classification.use_gemma", False
            )

            if use_gemma:
                try:
                    # Try to import and use Gemma classification agent
                    from src.agents.gemma_classification_agent import (
                        GemmaClassificationAgent,
                    )

                    self.classification_agent = GemmaClassificationAgent()
                    logger.info("Using Gemma-powered classification agent")
                    return
                except ImportError as e:
                    logger.warning(f"Failed to load Gemma classification agent: {e}")
                except Exception as e:
                    logger.warning(f"Gemma classification agent error: {e}")

            # Fallback to standard classification agent
            self.classification_agent = ClassificationAgent()
            logger.info("Using standard classification agent")

        except Exception as e:
            logger.error(f"Error initializing classification agent: {e}")
            # Ultimate fallback
            self.classification_agent = ClassificationAgent()

    async def process_user_message(self, user_message: str, **kwargs) -> Dict[str, Any]:
        """
        Process a user message with full KB integration and source tracking

        Returns:
            Dict containing response, sources, and metadata
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # Clear previous sources for new response
            clear_sources()

            # Add user message to conversation
            user_msg = ConversationMessage(
                message_id=str(uuid.uuid4()),
                role="user",
                content=user_message,
                timestamp=datetime.now(),
                message_type="chat",
            )
            self.messages.append(user_msg)

            # Step 1: Classify the request
            await self._classify_message(user_message)

            # Step 2: Search Knowledge Base (always, regardless of complexity)
            kb_results = await self._search_knowledge_base(user_message)

            # Step 3: Check if research is needed based on classification
            research_results = None
            if (
                self.state.classification
                and self.state.classification.complexity == TaskComplexity.COMPLEX
                and self._needs_external_research(user_message, kb_results)
            ):
                research_results = await self._conduct_research(user_message)

            # Step 4: Generate response with KB context and research
            response = await self._generate_response(
                user_message, kb_results, research_results
            )

            # Step 5: Add source attribution
            sources_block = get_attribution()

            # Step 6: Create response message
            assistant_msg = ConversationMessage(
                message_id=str(uuid.uuid4()),
                role="assistant",
                content=response,
                timestamp=datetime.now(),
                message_type="chat",
                sources=source_manager.current_response_sources,
            )
            self.messages.append(assistant_msg)

            # Add source message if sources were found
            if sources_block and self.include_sources:
                source_msg = ConversationMessage(
                    message_id=str(uuid.uuid4()),
                    role="system",
                    content=sources_block,
                    timestamp=datetime.now(),
                    message_type="source",
                )
                self.messages.append(source_msg)

            # Update conversation state
            processing_time = asyncio.get_event_loop().time() - start_time
            self.state.processing_time = processing_time
            self.state.sources_used = [
                s.to_dict() for s in source_manager.current_response_sources
            ]
            self.updated_at = datetime.now()

            # Return comprehensive response
            result = {
                "response": response,
                "sources": sources_block,
                "classification": (
                    asdict(self.state.classification)
                    if self.state.classification
                    else None
                ),
                "kb_results_count": len(kb_results),
                "processing_time": processing_time,
                "conversation_id": self.conversation_id,
                "message_id": assistant_msg.message_id,
            }

            # Add research information if available
            if research_results:
                result["research"] = research_results

            return result

        except Exception as e:
            logger.error(
                f"Error processing message in conversation {self.conversation_id}: {e}"
            )
            self.state.status = "error"

            # Add error message
            error_msg = ConversationMessage(
                message_id=str(uuid.uuid4()),
                role="system",
                content=f"Error processing request: {str(e)}",
                timestamp=datetime.now(),
                message_type="debug",
                metadata={"error": True},
            )
            self.messages.append(error_msg)

            return {
                "response": (
                    "I encountered an error processing your request. Please try again."
                ),
                "error": str(e),
                "conversation_id": self.conversation_id,
            }

    async def _classify_message(self, message: str):
        """Classify the user message for workflow routing"""
        try:
            self.state.classification = (
                await self.classification_agent.classify_request(message)
            )

            # Add classification as a thought message
            classification_msg = ConversationMessage(
                message_id=str(uuid.uuid4()),
                role="system",
                content=f"Classified as: {self.state.classification.complexity.value} "
                f"(confidence: {self.state.classification.confidence:.2f})",
                timestamp=datetime.now(),
                message_type="thought",
                metadata={
                    "classification": asdict(self.state.classification),
                    "reasoning": self.state.classification.reasoning,
                },
            )
            self.messages.append(classification_msg)

            logger.info(
                f"Message classified as {self.state.classification.complexity.value} "
                f"with {self.state.classification.confidence:.2f} confidence"
            )

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            # Default to SIMPLE if classification fails
            self.state.classification = ClassificationResult(
                complexity=TaskComplexity.SIMPLE,
                confidence=0.5,
                reasoning="Classification failed, defaulting to simple",
                suggested_agents=["chat_responder"],
                estimated_steps=1,
                user_approval_needed=False,
                context_analysis={"error": str(e)},
            )

    async def _search_knowledge_base(self, query: str) -> List[Dict[str, Any]]:
        """Search Knowledge Base with timeout protection"""
        try:
            if self.kb_librarian is None:
                self.kb_librarian = get_kb_librarian()

            # Add planning message
            planning_msg = ConversationMessage(
                message_id=str(uuid.uuid4()),
                role="system",
                content=f"Searching Knowledge Base for: '{query}'",
                timestamp=datetime.now(),
                message_type="planning",
            )
            self.messages.append(planning_msg)

            # Search with timeout protection
            search_task = asyncio.create_task(
                self.kb_librarian.search_knowledge_base(query)
            )

            kb_result = await asyncio.wait_for(search_task, timeout=self.kb_timeout)

            if kb_result:
                # KB librarian returns a list directly
                results = kb_result
                self.state.kb_context = results

                # Track KB sources
                for i, doc in enumerate(results):
                    source_manager.add_kb_source(
                        content=doc.get("content", "")[:200] + "...",
                        entry_id=str(doc.get("id", f"kb_{i}")),
                        confidence=doc.get("score", 0.5),
                        metadata={
                            "title": doc.get("title", "Knowledge Base Entry"),
                            "source_file": doc.get("source_file", "unknown"),
                        },
                    )

                # Add utility message about KB results
                utility_msg = ConversationMessage(
                    message_id=str(uuid.uuid4()),
                    role="system",
                    content=f"Found {len(results)} relevant knowledge base entries",
                    timestamp=datetime.now(),
                    message_type="utility",
                    metadata={"kb_results": len(results)},
                )
                self.messages.append(utility_msg)

                logger.info(f"KB search found {len(results)} results")
                return results
            else:
                logger.info("No KB results found")
                return []

        except asyncio.TimeoutError:
            logger.warning(f"KB search timed out after {self.kb_timeout}s")

            timeout_msg = ConversationMessage(
                message_id=str(uuid.uuid4()),
                role="system",
                content="Knowledge base search timed out, proceeding without KB context",
                timestamp=datetime.now(),
                message_type="utility",
                metadata={"timeout": True},
            )
            self.messages.append(timeout_msg)
            return []

        except Exception as e:
            logger.error(f"KB search failed: {e}")

            error_msg = ConversationMessage(
                message_id=str(uuid.uuid4()),
                role="system",
                content=f"Knowledge base search failed: {str(e)}",
                timestamp=datetime.now(),
                message_type="debug",
                metadata={"error": True},
            )
            self.messages.append(error_msg)
            return []

    async def _generate_response(
        self,
        user_message: str,
        kb_results: List[Dict[str, Any]],
        research_results: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate response with KB context and source attribution"""
        try:
            # Build context from KB results
            kb_context = ""
            if kb_results:
                kb_context = "\n\nRELEVANT KNOWLEDGE BASE INFORMATION:\n"
                for i, doc in enumerate(
                    kb_results[:3], 1
                ):  # Limit to top 3 for context
                    title = doc.get("title", f"Document {i}")
                    content = doc.get("content", "")[:300]  # Limit content length
                    kb_context += f"\n{i}. {title}:\n{content}...\n"

            # Build context from research results
            research_context = ""
            if (
                research_results
                and research_results.get("success")
                and research_results.get("results")
            ):
                research_context = "\n\nEXTERNAL RESEARCH RESULTS:\n"
                for i, result in enumerate(
                    research_results["results"][:2], 1
                ):  # Limit to top 2
                    content_data = result.get("content", {})
                    if content_data.get("success"):
                        text_content = content_data.get("text_content", "")[
                            :400
                        ]  # Limit length
                        research_context += (
                            f"\n{i}. Research Query: {result.get('query', 'Unknown')}\n"
                        )
                        research_context += f"   Content: {text_content}...\n"

                        if result.get("interaction_required"):
                            research_context += "   ⚠️ Browser session available for manual verification\n"
                            research_context += (
                                f"   🌐 Browser URL: {result.get('browser_url', '')}\n"
                            )

            # Create enhanced prompt with KB and research context
            system_prompt = """You are AutoBot, an intelligent AI assistant. You have access to a knowledge base and can conduct external research.

IMPORTANT INSTRUCTIONS:
1. Always prioritize information from the Knowledge Base when available
2. Use external research results to supplement KB information, especially for current/recent topics
3. If research requires user interaction (CAPTCHA, verification), inform the user about browser session availability
4. Cite sources when referencing specific information
5. Be conversational but accurate
6. If you don't know something and it's not in KB or research, say so clearly"""

            user_prompt = """User Message: {user_message}

{kb_context}

{research_context}

Please provide a helpful, accurate response based on the available information. If you reference information from the knowledge base, mention AutoBot's documentation. If you reference research results, mention external sources. If research requires user interaction, explain how they can access the browser session."""

            # Add planning message
            planning_msg = ConversationMessage(
                message_id=str(uuid.uuid4()),
                role="system",
                content="Generating response with KB context and LLM",
                timestamp=datetime.now(),
                message_type="planning",
            )
            self.messages.append(planning_msg)

            # Get LLM response with failover
            llm_response = await get_robust_llm_response(
                f"{system_prompt}\n\n{user_prompt}",
                context={
                    "conversation_id": self.conversation_id,
                    "classification": (
                        self.state.classification.complexity.value
                        if self.state.classification
                        else "simple"
                    ),
                    "kb_results_count": len(kb_results),
                },
            )

            # Track LLM as a source
            track_source(
                SourceType.LLM_TRAINING,
                "Generated response using LLM",
                reliability="medium",
                metadata={
                    "tier_used": llm_response.tier_used.value,
                    "model": getattr(llm_response, "model_used", "unknown"),
                    "warnings": llm_response.warnings,
                },
            )

            response_content = llm_response.content

            # Add utility message about LLM tier used
            utility_msg = ConversationMessage(
                message_id=str(uuid.uuid4()),
                role="system",
                content=f"Response generated using {llm_response.tier_used.value} LLM tier",
                timestamp=datetime.now(),
                message_type="utility",
                metadata={
                    "tier_used": llm_response.tier_used.value,
                    "warnings": llm_response.warnings,
                },
            )
            self.messages.append(utility_msg)

            logger.info(f"Response generated using {llm_response.tier_used.value} tier")
            return response_content

        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return (
                "I'm having trouble generating a response right now. Please try again."
            )

    def _needs_external_research(
        self, user_message: str, kb_results: List[Dict[str, Any]]
    ) -> bool:
        """Determine if external research is needed"""
        # Check if KB results are insufficient
        if not kb_results or len(kb_results) < 2:
            # Check for research keywords
            research_keywords = [
                "latest",
                "current",
                "recent",
                "new",
                "today",
                "2024",
                "2025",
                "what's happening",
                "news",
                "trends",
                "update",
                "status",
                "compare",
                "vs",
                "versus",
                "difference between",
                "how to",
                "tutorial",
                "guide",
                "step by step",
                "price",
                "cost",
                "buy",
                "purchase",
                "review",
            ]

            user_lower = user_message.lower()
            return any(keyword in user_lower for keyword in research_keywords)

        return False

    async def _conduct_research(self, user_message: str) -> Dict[str, Any]:
        """Conduct external research using browser automation"""
        try:
            # Add planning message
            planning_msg = ConversationMessage(
                message_id=str(uuid.uuid4()),
                role="system",
                content="Conducting external research with browser automation",
                timestamp=datetime.now(),
                message_type="planning",
            )
            self.messages.append(planning_msg)

            # Generate search queries based on user message
            search_queries = self._generate_search_queries(user_message)
            research_results = []

            for query in search_queries[:2]:  # Limit to 2 queries
                # Try researching with search engine
                search_url = (
                    f"{NetworkConstants.GOOGLE_SEARCH_BASE_URL}?q={query.replace(' ',"
                    f"'+')}"
                )


                research_result = await research_browser_manager.research_url(
                    self.conversation_id, search_url, extract_content=True
                )

                if research_result.get("success"):
                    research_results.append(
                        {
                            "query": query,
                            "url": search_url,
                            "status": research_result.get("status"),
                            "content": research_result.get("content", {}),
                            "session_id": research_result.get("session_id"),
                            "browser_url": research_result.get("browser_url"),
                            "interaction_required": (
                                research_result.get("status") == "interaction_required"
                            ),
                        }
                    )

                    # Track research source
                    track_source(
                        SourceType.WEB_SEARCH,
                        f"External research: {query}",
                        reliability="medium",
                        metadata={
                            "query": query,
                            "url": search_url,
                            "research_session": research_result.get("session_id"),
                            "interaction_required": (
                                research_result.get("status") == "interaction_required"
                            ),
                        },
                    )

            if research_results:
                # Add utility message about research
                utility_msg = ConversationMessage(
                    message_id=str(uuid.uuid4()),
                    role="system",
                    content=f"Completed external research with {len(research_results)} queries",
                    timestamp=datetime.now(),
                    message_type="utility",
                    metadata={"research_queries": len(research_results)},
                )
                self.messages.append(utility_msg)

            return {
                "success": True,
                "queries": search_queries,
                "results": research_results,
                "total_results": len(research_results),
            }

        except Exception as e:
            logger.error(f"Research failed: {e}")

            error_msg = ConversationMessage(
                message_id=str(uuid.uuid4()),
                role="system",
                content=f"External research failed: {str(e)}",
                timestamp=datetime.now(),
                message_type="debug",
                metadata={"error": True},
            )
            self.messages.append(error_msg)

            return {"success": False, "error": str(e)}

    def _generate_search_queries(self, user_message: str) -> List[str]:
        """Generate search queries based on user message"""
        # Simple query generation - in production, this could use LLM
        queries = []

        # Add the original message as a query
        queries.append(user_message)

        # Add variations based on keywords
        if "how to" in user_message.lower():
            queries.append(f"{user_message} tutorial guide")
        elif "what is" in user_message.lower():
            queries.append(f"{user_message} definition explanation")
        elif any(word in user_message.lower() for word in ["compare", "vs", "versus"]):
            queries.append(f"{user_message} comparison review")
        else:
            # Add a more specific query
            queries.append(f"{user_message} 2024 latest information")

        return queries[:3]  # Limit to 3 queries

    async def get_research_session(self) -> Optional[str]:
        """Get the current research session ID for this conversation"""
        session = research_browser_manager.get_session_by_conversation(
            self.conversation_id
        )
        return session.session_id if session else None

    def get_messages(self, message_types: List[str] = None) -> List[Dict[str, Any]]:
        """Get conversation messages, optionally filtered by type"""
        if message_types is None:
            message_types = ["chat", "source"]  # Default to user-facing messages

        filtered_messages = []
        for msg in self.messages:
            if msg.message_type in message_types:
                filtered_messages.append(asdict(msg))

        return filtered_messages

    def get_conversation_summary(self) -> Dict[str, Any]:
        """Get a summary of the conversation"""
        return {
            "conversation_id": self.conversation_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message_count": len(self.messages),
            "status": self.state.status,
            "classification": (
                asdict(self.state.classification) if self.state.classification else None
            ),
            "kb_context_count": len(self.state.kb_context),
            "sources_used": len(self.state.sources_used),
            "total_processing_time": self.state.processing_time,
        }

    def export_conversation(self) -> Dict[str, Any]:
        """Export complete conversation data"""
        return {
            "conversation_id": self.conversation_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [asdict(msg) for msg in self.messages],
            "state": asdict(self.state),
            "summary": self.get_conversation_summary(),
        }

    async def cleanup(self):
        """Clean up conversation resources"""
        clear_sources()
        logger.info(f"Cleaned up conversation {self.conversation_id}")


# Conversation Manager for handling multiple conversations
class ConversationManager:
    """Manages multiple conversations"""

    def __init__(self):
        self.conversations: Dict[str, Conversation] = {}
        self.max_conversations = 100  # Limit memory usage

    def create_conversation(self, conversation_id: str = None) -> Conversation:
        """Create a new conversation"""
        conversation = Conversation(conversation_id)

        # Clean up old conversations if at limit
        if len(self.conversations) >= self.max_conversations:
            oldest_id = min(
                self.conversations.keys(),
                key=lambda x: self.conversations[x].created_at,
            )
            # Note: cleanup will be called when conversation is replaced
            del self.conversations[oldest_id]
            logger.info(f"Cleaned up oldest conversation {oldest_id}")

        self.conversations[conversation.conversation_id] = conversation
        return conversation

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get existing conversation"""
        return self.conversations.get(conversation_id)

    def get_or_create_conversation(self, conversation_id: str = None) -> Conversation:
        """Get existing or create new conversation"""
        if conversation_id and conversation_id in self.conversations:
            return self.conversations[conversation_id]
        return self.create_conversation(conversation_id)

    async def cleanup_conversation(self, conversation_id: str):
        """Clean up specific conversation"""
        if conversation_id in self.conversations:
            await self.conversations[conversation_id].cleanup()
            del self.conversations[conversation_id]
            logger.info(f"Cleaned up conversation {conversation_id}")


# Global conversation manager instance
conversation_manager = ConversationManager()


def get_conversation_manager() -> ConversationManager:
    """Get the global conversation manager instance"""
    global conversation_manager
    if conversation_manager is None:
        conversation_manager = ConversationManager()
    return conversation_manager
