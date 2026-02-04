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
from src.config import config as global_config_manager
from src.constants.network_constants import NetworkConstants
from src.constants.threshold_constants import TimingConstants
from src.research_browser_manager import research_browser_manager
from src.source_attribution import (
    SourceType,
    clear_sources,
    get_attribution,
    source_manager,
    track_source,
)

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for comparison query keywords (Issue #326)
COMPARISON_QUERY_KEYWORDS = {"compare", "vs", "versus"}

# Issue #380: Module-level tuple for default message types in get_messages
_DEFAULT_MESSAGE_TYPES = ("chat", "source")


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
        """Initialize default values for metadata and sources fields."""
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
        """Initialize default values for kb_context and sources_used fields."""
        if self.kb_context is None:
            self.kb_context = []
        if self.sources_used is None:
            self.sources_used = []


class Conversation:
    """
    Comprehensive conversation management with KB integration and source tracking
    """

    def __init__(self, conversation_id: str = None):
        """Initialize conversation with unique ID and default state."""
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
        # KB timeout should be longer than KB circuit breaker (Issue #376 - use named constant)
        self.kb_timeout = float(
            TimingConstants.LONG_DELAY
        )  # 10s - allows for circuit breaker recovery
        self.include_sources = True

        logger.info("Created conversation %s", self.conversation_id)

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
                    logger.warning("Failed to load Gemma classification agent: %s", e)
                except Exception as e:
                    logger.warning("Gemma classification agent error: %s", e)

            # Fallback to standard classification agent
            self.classification_agent = ClassificationAgent()
            logger.info("Using standard classification agent")

        except Exception as e:
            logger.error("Error initializing classification agent: %s", e)
            # Ultimate fallback
            self.classification_agent = ClassificationAgent()

    async def process_user_message(self, user_message: str, **kwargs) -> Dict[str, Any]:
        """
        Process a user message with full KB integration and source tracking.

        Issue #281: Refactored to use extracted helpers.

        Returns:
            Dict containing response, sources, and metadata
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # Clear previous sources and add user message
            clear_sources()
            self._create_user_message(user_message)

            # Step 1: Classify and search KB
            await self._classify_message(user_message)
            kb_results = await self._search_knowledge_base(user_message)

            # Step 2: Conduct research if needed
            research_results = None
            if (
                self.state.classification
                and self.state.classification.complexity == TaskComplexity.COMPLEX
                and self._needs_external_research(user_message, kb_results)
            ):
                research_results = await self._conduct_research(user_message)

            # Step 3: Generate response and add attribution
            response = await self._generate_response(
                user_message, kb_results, research_results
            )
            sources_block = get_attribution()

            # Step 4: Create messages and update state
            assistant_msg = self._create_assistant_message(
                response, source_manager.current_response_sources
            )
            self._add_source_message(sources_block)

            # Update conversation state
            self.state.processing_time = asyncio.get_event_loop().time() - start_time
            self.state.sources_used = [
                s.to_dict() for s in source_manager.current_response_sources
            ]
            self.updated_at = datetime.now()

            return self._build_process_result(
                response, sources_block, kb_results, assistant_msg, research_results
            )

        except Exception as e:
            return self._handle_process_error(e)

    def _create_user_message(self, user_message: str) -> ConversationMessage:
        """Create and store user message (Issue #281 - extracted helper)."""
        user_msg = ConversationMessage(
            message_id=str(uuid.uuid4()),
            role="user",
            content=user_message,
            timestamp=datetime.now(),
            message_type="chat",
        )
        self.messages.append(user_msg)
        return user_msg

    def _create_assistant_message(
        self, response: str, sources: List[Dict[str, Any]]
    ) -> ConversationMessage:
        """Create assistant response message (Issue #281 - extracted helper)."""
        assistant_msg = ConversationMessage(
            message_id=str(uuid.uuid4()),
            role="assistant",
            content=response,
            timestamp=datetime.now(),
            message_type="chat",
            sources=sources,
        )
        self.messages.append(assistant_msg)
        return assistant_msg

    def _add_source_message(self, sources_block: str) -> None:
        """Add source attribution message if applicable (Issue #281 - extracted helper)."""
        if sources_block and self.include_sources:
            source_msg = ConversationMessage(
                message_id=str(uuid.uuid4()),
                role="system",
                content=sources_block,
                timestamp=datetime.now(),
                message_type="source",
            )
            self.messages.append(source_msg)

    def _build_process_result(
        self,
        response: str,
        sources_block: str,
        kb_results: List[Dict[str, Any]],
        assistant_msg: ConversationMessage,
        research_results: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build result dictionary for process_user_message (Issue #281 - extracted helper)."""
        result = {
            "response": response,
            "sources": sources_block,
            "classification": (
                asdict(self.state.classification) if self.state.classification else None
            ),
            "kb_results_count": len(kb_results),
            "processing_time": self.state.processing_time,
            "conversation_id": self.conversation_id,
            "message_id": assistant_msg.message_id,
        }
        if research_results:
            result["research"] = research_results
        return result

    def _handle_process_error(self, error: Exception) -> Dict[str, Any]:
        """Handle error during message processing (Issue #281 - extracted helper)."""
        logger.error(
            f"Error processing message in conversation {self.conversation_id}: {error}"
        )
        self.state.status = "error"

        error_msg = ConversationMessage(
            message_id=str(uuid.uuid4()),
            role="system",
            content=f"Error processing request: {str(error)}",
            timestamp=datetime.now(),
            message_type="debug",
            metadata={"error": True},
        )
        self.messages.append(error_msg)

        return {
            "response": (
                "I encountered an error processing your request. Please try again."
            ),
            "error": str(error),
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
            logger.error("Classification failed: %s", e)
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

    def _process_kb_results(self, results: List[Dict[str, Any]]) -> None:
        """Process KB results and track sources (Issue #665: extracted helper)."""
        self.state.kb_context = results

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

        utility_msg = ConversationMessage(
            message_id=str(uuid.uuid4()),
            role="system",
            content=f"Found {len(results)} relevant knowledge base entries",
            timestamp=datetime.now(),
            message_type="utility",
            metadata={"kb_results": len(results)},
        )
        self.messages.append(utility_msg)

    def _add_kb_error_message(self, error_type: str, error_detail: str) -> None:
        """Add KB error/timeout message to conversation (Issue #665: extracted helper)."""
        msg_type = "utility" if error_type == "timeout" else "debug"
        error_msg = ConversationMessage(
            message_id=str(uuid.uuid4()),
            role="system",
            content=error_detail,
            timestamp=datetime.now(),
            message_type=msg_type,
            metadata={error_type: True},
        )
        self.messages.append(error_msg)

    async def _search_knowledge_base(self, query: str) -> List[Dict[str, Any]]:
        """Search Knowledge Base with timeout protection"""
        try:
            if self.kb_librarian is None:
                self.kb_librarian = get_kb_librarian()

            planning_msg = ConversationMessage(
                message_id=str(uuid.uuid4()),
                role="system",
                content=f"Searching Knowledge Base for: '{query}'",
                timestamp=datetime.now(),
                message_type="planning",
            )
            self.messages.append(planning_msg)

            search_task = asyncio.create_task(
                self.kb_librarian.search_knowledge_base(query)
            )

            kb_result = await asyncio.wait_for(search_task, timeout=self.kb_timeout)

            if kb_result:
                self._process_kb_results(kb_result)
                logger.info("KB search found %s results", len(kb_result))
                return kb_result
            else:
                logger.info("No KB results found")
                return []

        except asyncio.TimeoutError:
            logger.warning("KB search timed out after %ss", self.kb_timeout)
            self._add_kb_error_message(
                "timeout",
                "Knowledge base search timed out, proceeding without KB context",
            )
            return []

        except Exception as e:
            logger.error("KB search failed: %s", e)
            self._add_kb_error_message(
                "error", f"Knowledge base search failed: {str(e)}"
            )
            return []

    def _build_kb_context(self, kb_results: List[Dict[str, Any]]) -> str:
        """Build context from KB results. Issue #383: Uses list.join()."""
        if not kb_results:
            return ""

        kb_lines = ["", "", "RELEVANT KNOWLEDGE BASE INFORMATION:"]
        for i, doc in enumerate(kb_results[:3], 1):  # Limit to top 3 for context
            title = doc.get("title", f"Document {i}")
            content = doc.get("content", "")[:300]  # Limit content length
            kb_lines.extend(["", f"{i}. {title}:", f"{content}..."])
        return "\n".join(kb_lines)

    def _build_research_context(
        self, research_results: Optional[Dict[str, Any]]
    ) -> str:
        """Build context from research results. Issue #383: Uses list.join()."""
        if not research_results or not research_results.get("success"):
            return ""
        if not research_results.get("results"):
            return ""

        research_lines = ["", "", "EXTERNAL RESEARCH RESULTS:"]
        for i, result in enumerate(
            research_results["results"][:2], 1
        ):  # Limit to top 2
            content_data = result.get("content", {})
            if content_data.get("success"):
                text_content = content_data.get("text_content", "")[:400]
                research_lines.extend(
                    [
                        "",
                        f"{i}. Research Query: {result.get('query', 'Unknown')}",
                        f"   Content: {text_content}...",
                    ]
                )

                if result.get("interaction_required"):
                    research_lines.extend(
                        [
                            "   ⚠️ Browser session available for manual verification",
                            f"   🌐 Browser URL: {result.get('browser_url', '')}",
                        ]
                    )
        return "\n".join(research_lines)

    def _get_system_prompt(self) -> str:
        """Get the system prompt for response generation."""
        return (
            "You are AutoBot, an intelligent AI assistant. You have access to a "
            "knowledge base and can conduct external research.\n\n"
            "IMPORTANT INSTRUCTIONS:\n"
            "1. Always prioritize information from the Knowledge Base when available\n"
            "2. Use external research results to supplement KB information, "
            "especially for current/recent topics\n"
            "3. If research requires user interaction (CAPTCHA, verification), "
            "inform the user about browser session availability\n"
            "4. Cite sources when referencing specific information\n"
            "5. Be conversational but accurate\n"
            "6. If you don't know something and it's not in KB or research, say so clearly"
        )

    def _build_user_prompt(
        self, user_message: str, kb_context: str, research_context: str
    ) -> str:
        """Build user prompt with contexts. Issue #382: Uses f-string for substitution."""
        instructions = (
            "Please provide a helpful, accurate response based on the available "
            "information. If you reference information from the knowledge base, "
            "mention AutoBot's documentation. If you reference research results, "
            "mention external sources. If research requires user interaction, "
            "explain how they can access the browser session."
        )
        return f"User Message: {user_message}\n\n{kb_context}\n\n{research_context}\n\n{instructions}"

    def _add_planning_message(self) -> None:
        """Add planning message to conversation."""
        planning_msg = ConversationMessage(
            message_id=str(uuid.uuid4()),
            role="system",
            content="Generating response with KB context and LLM",
            timestamp=datetime.now(),
            message_type="planning",
        )
        self.messages.append(planning_msg)

    def _add_utility_message(self, llm_response) -> None:
        """Add utility message about LLM tier used."""
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

    def _track_llm_source(self, llm_response) -> None:
        """Track LLM as a source for attribution. Issue #620."""
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

    def _build_llm_context(self, kb_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build context dictionary for LLM request. Issue #620."""
        return {
            "conversation_id": self.conversation_id,
            "classification": (
                self.state.classification.complexity.value
                if self.state.classification
                else "simple"
            ),
            "kb_results_count": len(kb_results),
        }

    async def _generate_response(
        self,
        user_message: str,
        kb_results: List[Dict[str, Any]],
        research_results: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate response with KB context and source attribution. Issue #620."""
        try:
            kb_context = self._build_kb_context(kb_results)
            research_context = self._build_research_context(research_results)
            system_prompt = self._get_system_prompt()
            user_prompt = self._build_user_prompt(
                user_message, kb_context, research_context
            )

            self._add_planning_message()
            llm_response = await get_robust_llm_response(
                f"{system_prompt}\n\n{user_prompt}",
                context=self._build_llm_context(kb_results),
            )

            self._track_llm_source(llm_response)
            self._add_utility_message(llm_response)
            logger.info(
                "Response generated using %s tier", llm_response.tier_used.value
            )
            return llm_response.content

        except Exception as e:
            logger.error("Response generation failed: %s", e)
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

    def _add_system_message(
        self,
        content: str,
        message_type: str = "system",
        metadata: Optional[Dict] = None,
    ) -> None:
        """Add a system message to conversation (Issue #398: extracted)."""
        msg = ConversationMessage(
            message_id=str(uuid.uuid4()),
            role="system",
            content=content,
            timestamp=datetime.now(),
            message_type=message_type,
            metadata=metadata,
        )
        self.messages.append(msg)

    async def _research_single_query(self, query: str) -> Optional[Dict[str, Any]]:
        """Research a single query and return result (Issue #398: extracted)."""
        search_url = (
            f"{NetworkConstants.GOOGLE_SEARCH_BASE_URL}?q={query.replace(' ', '+')}"
        )
        try:
            research_result = await research_browser_manager.research_url(
                self.conversation_id, search_url, extract_content=True
            )
            if research_result.get("success"):
                track_source(
                    SourceType.WEB_SEARCH,
                    f"External research: {query}",
                    reliability="medium",
                    metadata={
                        "query": query,
                        "url": search_url,
                        "research_session": research_result.get("session_id"),
                        "interaction_required": research_result.get("status")
                        == "interaction_required",
                    },
                )
                return {
                    "query": query,
                    "url": search_url,
                    "status": research_result.get("status"),
                    "content": research_result.get("content", {}),
                    "session_id": research_result.get("session_id"),
                    "browser_url": research_result.get("browser_url"),
                    "interaction_required": research_result.get("status")
                    == "interaction_required",
                }
        except Exception as e:
            logger.warning("Research query '%s' failed: %s", query, e)
        return None

    async def _conduct_research(self, user_message: str) -> Dict[str, Any]:
        """Conduct external research using browser automation (Issue #398: refactored)."""
        try:
            self._add_system_message(
                "Conducting external research with browser automation", "planning"
            )

            search_queries = self._generate_search_queries(user_message)

            # Issue #370: Research queries in parallel (limit to 2)
            results = await asyncio.gather(
                *[self._research_single_query(q) for q in search_queries[:2]],
                return_exceptions=True,
            )

            research_results = [
                r for r in results if r and not isinstance(r, Exception)
            ]

            if research_results:
                self._add_system_message(
                    f"Completed external research with {len(research_results)} queries",
                    "utility",
                    {"research_queries": len(research_results)},
                )

            return {
                "success": True,
                "queries": search_queries,
                "results": research_results,
                "total_results": len(research_results),
            }

        except Exception as e:
            logger.error("Research failed: %s", e)
            self._add_system_message(
                f"External research failed: {str(e)}", "debug", {"error": True}
            )
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
        elif any(word in user_message.lower() for word in COMPARISON_QUERY_KEYWORDS):
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
            message_types = _DEFAULT_MESSAGE_TYPES  # Issue #380: use module constant

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
        logger.info("Cleaned up conversation %s", self.conversation_id)


# Conversation Manager for handling multiple conversations
class ConversationManager:
    """Manages multiple conversations"""

    def __init__(self):
        """Initialize conversation manager with empty conversations dict."""
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
            logger.info("Cleaned up oldest conversation %s", oldest_id)

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
            logger.info("Cleaned up conversation %s", conversation_id)


# Global conversation manager instance
conversation_manager = ConversationManager()


def get_conversation_manager() -> ConversationManager:
    """Get the global conversation manager instance"""
    global conversation_manager
    if conversation_manager is None:
        conversation_manager = ConversationManager()
    return conversation_manager
