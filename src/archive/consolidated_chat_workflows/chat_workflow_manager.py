"""
Chat Workflow Manager - Proper Implementation of User Request → Knowledge → Response Flow

This module implements the correct chat workflow as specified:
1. User writes message
2. Get response to any topic
3. Check knowledge base for relevant information
4. If task-related, look for system/terminal knowledge
5. If no knowledge exists, engage librarian for research
6. Use MCP for manual/help lookups
7. Never hallucinate - communicate knowledge gaps clearly
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.agents import get_kb_librarian
from src.agents.classification_agent import ClassificationAgent, ClassificationResult
from src.agents.llm_failsafe_agent import get_robust_llm_response
from src.autobot_types import TaskComplexity
from src.constants.network_constants import NetworkConstants
from src.conversation import Conversation

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of user messages requiring different handling"""

    GENERAL_QUERY = "general_query"
    DESKTOP_TASK = "desktop_task"
    TERMINAL_TASK = "terminal_task"
    SYSTEM_TASK = "system_task"
    RESEARCH_NEEDED = "research_needed"


class KnowledgeStatus(Enum):
    """Status of knowledge availability"""

    FOUND = "found"
    PARTIAL = "partial"
    MISSING = "missing"
    RESEARCH_REQUIRED = "research_required"


@dataclass
class ChatWorkflowResult:
    """Result of processing a chat message through the workflow"""

    response: str
    message_type: MessageType
    knowledge_status: KnowledgeStatus
    kb_results: List[Dict[str, Any]]
    research_results: Optional[Dict[str, Any]] = None
    sources: List[Dict[str, Any]] = None
    processing_time: float = 0.0
    librarian_engaged: bool = False
    mcp_used: bool = False
    error: Optional[str] = None


class ChatWorkflowManager:
    """
    Manages the complete chat workflow from user input to final response.

    Implements the proper flow:
    1. Message classification and intent detection
    2. Knowledge base search with task-specific context
    3. System knowledge lookup for terminal/desktop tasks
    4. Research orchestration when knowledge is missing
    5. Response generation with clear knowledge status
    """

    def __init__(self):
        """Initialize the chat workflow manager"""
        self.classification_agent = ClassificationAgent()
        self.kb_librarian = None
        self.conversation_manager = None

        # Load settings using the proper config manager
        try:
            from src.utils.config_manager import config_manager

            settings_data = config_manager.get_all()
            self.settings = settings_data
        except Exception as e:
            logger.warning(f"Could not load settings: {e}")
            self.settings = {}

        # Check if features are enabled in settings
        # KB and Librarian are one function - librarian manages the knowledge base
        self.kb_librarian_enabled = (
            self.settings.get("agents", {}).get("kb_librarian", {}).get("enabled", True)
        )
        # Research agent is subordinate to librarian - called by librarian when needed
        self.web_research_enabled = (
            self.settings.get("agents", {}).get("research", {}).get("enabled", False)
        )

        # Also check legacy web_research setting for backward compatibility
        if not self.web_research_enabled:
            self.web_research_enabled = self.settings.get("web_research", {}).get(
                "enabled", False
            )

        # Workflow configuration - use agent-specific timeouts from settings
        self.kb_search_timeout = (
            self.settings.get("agents", {})
            .get("kb_librarian", {})
            .get("timeout_seconds", 15.0)
        )
        self.research_timeout = (
            self.settings.get("agents", {})
            .get("research", {})
            .get("timeout_seconds", 30.0)
        )
        self.classification_timeout = (
            self.settings.get("agents", {})
            .get("classification", {})
            .get("timeout_seconds", 10.0)
        )
        self.max_kb_results = (
            self.settings.get("agents", {})
            .get("kb_librarian", {})
            .get("max_results", 5)
        )
        self.min_confidence_threshold = 0.3

        logger.info(
            f"ChatWorkflowManager initialized - KB/Librarian enabled: {self.kb_librarian_enabled}, Research agent available: {self.web_research_enabled}"
        )

    def _is_research_response(self, user_message: str) -> Optional[bool]:
        """
        Check if user message is a yes/no response to research question.

        Returns:
            True if yes, False if no, None if not a research response
        """
        message_lower = user_message.lower().strip()

        # Direct yes/no responses
        if message_lower in ["yes", "y", "yeah", "yep", "sure", "ok", "okay"]:
            return True
        elif message_lower in ["no", "n", "nope", "nah", "never mind", "nevermind"]:
            return False

        # Phrase-based responses
        yes_phrases = [
            "yes please",
            "yes, please",
            "go ahead",
            "do it",
            "research it",
            "look it up",
        ]
        no_phrases = [
            "no thanks",
            "no, thanks",
            "not needed",
            "skip it",
            "end workflow",
            "stop here",
        ]

        if any(phrase in message_lower for phrase in yes_phrases):
            return True
        elif any(phrase in message_lower for phrase in no_phrases):
            return False

        return None

    async def process_message(
        self,
        user_message: str,
        chat_id: Optional[str] = None,
        conversation: Optional[Conversation] = None,
    ) -> ChatWorkflowResult:
        """
        Process a user message through the complete chat workflow.

        Args:
            user_message: The user's input message
            chat_id: Optional chat session ID
            conversation: Optional existing conversation instance

        Returns:
            ChatWorkflowResult with response and metadata
        """
        start_time = time.time()

        try:
            logger.info(
                f"Processing message: '{user_message[:100]}{'...' if len(user_message) > 100 else ''}'"
            )

            # Check if this is a yes/no response to research question
            research_decision = self._is_research_response(user_message)
            if research_decision is not None:
                if research_decision:
                    logger.info(
                        "WORKFLOW: User agreed to research - proceeding with research workflow"
                    )
                    # TODO: Implement research workflow with user guidance
                    return ChatWorkflowResult(
                        response="Great! I'll help you research this topic. Please provide more details about what specifically you'd like me to look into, or guide me to specific sources you'd like me to check.",
                        message_type=MessageType.RESEARCH_NEEDED,
                        knowledge_status=KnowledgeStatus.RESEARCH_REQUIRED,
                        kb_results=[],
                        processing_time=time.time() - start_time,
                    )
                else:
                    logger.info("WORKFLOW: User declined research - ending workflow")
                    return ChatWorkflowResult(
                        response="Understood. I don't have information about this topic in my knowledge base, so I'll end this workflow here. Feel free to ask me about something else!",
                        message_type=MessageType.GENERAL_QUERY,
                        knowledge_status=KnowledgeStatus.MISSING,
                        kb_results=[],
                        processing_time=time.time() - start_time,
                    )

            # Step 1: Classify the message and determine intent
            logger.info("WORKFLOW: Starting classification...")
            try:
                logger.info("WORKFLOW: Creating classification task...")
                classify_task = asyncio.create_task(
                    self._classify_message(user_message)
                )
                logger.info("WORKFLOW: Waiting for classification with timeout...")
                message_type, classification = await asyncio.wait_for(
                    classify_task, timeout=self.classification_timeout
                )
                logger.info(
                    f"WORKFLOW: Classification completed successfully! Message type: {message_type.value}"
                )
                if classification:
                    logger.info(
                        f"WORKFLOW: Classification details - complexity: {classification.complexity}, confidence: {classification.confidence}"
                    )
                else:
                    logger.info("WORKFLOW: No classification details returned")
            except asyncio.TimeoutError:
                logger.error(
                    f"WORKFLOW: Classification timed out after {self.classification_timeout} seconds"
                ),
                message_type = MessageType.GENERAL_QUERY
                classification = None
            except Exception as e:
                logger.error(f"WORKFLOW: Classification failed: {e}")
                import traceback

                logger.error(
                    f"WORKFLOW: Classification traceback: {traceback.format_exc()}"
                ),
                message_type = MessageType.GENERAL_QUERY
                classification = None

            # Step 2: Search for relevant knowledge
            logger.info("WORKFLOW: Starting knowledge search...")
            knowledge_status, kb_results = await self._search_knowledge(
                user_message, message_type, classification
            )
            logger.info(
                f"WORKFLOW: Knowledge status: {knowledge_status.value}, found {len(kb_results)} results"
            )

            # Step 3: Determine if research is needed
            logger.info("WORKFLOW: Checking if research needed...")
            needs_research = self._needs_research(
                knowledge_status, kb_results, classification
            )
            logger.info(f"WORKFLOW: Research needed: {needs_research}")

            research_results = None
            librarian_engaged = False
            mcp_used = False

            if needs_research:
                # Step 4: Engage research if knowledge is insufficient
                logger.info("WORKFLOW: Starting research...")
                try:
                    research_task = asyncio.create_task(
                        self._conduct_research(user_message, message_type, kb_results)
                    )
                    research_results, librarian_engaged, mcp_used = (
                        await asyncio.wait_for(research_task, timeout=10.0)
                    )
                    logger.info(
                        f"WORKFLOW: Research completed: librarian={librarian_engaged}, mcp={mcp_used}"
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "WORKFLOW: Research timed out after 10 seconds, proceeding without research"
                    ),
                    research_results = None
                    librarian_engaged = False
                    mcp_used = False
                except Exception as e:
                    logger.error(
                        f"WORKFLOW: Research failed: {e}, proceeding without research"
                    ),
                    research_results = None
                    librarian_engaged = False
                    mcp_used = False

            # Step 5: Generate response based on available information
            logger.info("WORKFLOW: Starting response generation...")
            try:
                response_task = asyncio.create_task(
                    self._generate_response(
                        user_message=user_message,
                        message_type=message_type,
                        knowledge_status=knowledge_status,
                        kb_results=kb_results,
                        research_results=research_results,
                        classification=classification,
                    )
                ),
                response = await asyncio.wait_for(response_task, timeout=15.0)
                logger.info(
                    f"WORKFLOW: Response generated successfully, length: {len(response)}"
                )
            except asyncio.TimeoutError:
                logger.error("WORKFLOW: Response generation timed out after 15 seconds")
                response = "I apologize, but I'm having trouble generating a response. Please try again."
            except Exception as e:
                logger.error(f"WORKFLOW: Response generation failed: {e}")
                response = f"I encountered an error: {str(e)}. Please try again."

            processing_time = time.time() - start_time
            logger.info(f"WORKFLOW: Completed in {processing_time:.2f}s")

            result = ChatWorkflowResult(
                response=response,
                message_type=message_type,
                knowledge_status=knowledge_status,
                kb_results=kb_results,
                research_results=research_results,
                sources=self._extract_sources(kb_results, research_results),
                processing_time=processing_time,
                librarian_engaged=librarian_engaged,
                mcp_used=mcp_used,
            )

            logger.info(
                f"WORKFLOW: Returning result with response length: {len(result.response)}"
            )
            return result

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Error in chat workflow: {e}")

            return ChatWorkflowResult(
                response=self._generate_error_response(str(e)),
                message_type=MessageType.GENERAL_QUERY,
                knowledge_status=KnowledgeStatus.MISSING,
                kb_results=[],
                processing_time=processing_time,
                error=str(e),
            )

    async def _classify_message(
        self, user_message: str
    ) -> Tuple[MessageType, Optional[ClassificationResult]]:
        """
        Classify the user message to determine appropriate handling.

        Returns:
            Tuple of (MessageType, ClassificationResult)
        """
        try:
            logger.info("WORKFLOW: Calling classification agent...")
            # Get classification from agent
            classification = await self.classification_agent.classify_request(
                user_message
            )
            logger.info(
                f"WORKFLOW: Classification agent returned: {type(classification)}"
            )

            # Map classification to our workflow message types
            if classification:
                logger.info("WORKFLOW: Processing classification result...")
                try:
                    reasoning = (
                        classification.reasoning.lower()
                        if hasattr(classification, "reasoning")
                        else ""
                    )
                    logger.info(f"WORKFLOW: Reasoning: {reasoning[:100]}...")

                    # Check for terminal/system tasks based on reasoning and suggested agents
                    if any(
                        keyword in reasoning
                        for keyword in ["terminal", "command", "shell", "bash", "cli"]
                    ):
                        logger.info("WORKFLOW: Classified as TERMINAL_TASK")
                        return MessageType.TERMINAL_TASK, classification

                    if any(
                        keyword in reasoning
                        for keyword in [
                            "desktop",
                            "gui",
                            "window",
                            "application",
                            "app",
                        ]
                    ):
                        logger.info("WORKFLOW: Classified as DESKTOP_TASK")
                        return MessageType.DESKTOP_TASK, classification

                    if any(
                        keyword in reasoning
                        for keyword in [
                            "system",
                            "config",
                            "install",
                            "setup",
                            "administration",
                        ]
                    ):
                        logger.info("WORKFLOW: Classified as SYSTEM_TASK")
                        return MessageType.SYSTEM_TASK, classification

                    # Check for suggested agents that indicate task types
                    suggested_agents = getattr(classification, "suggested_agents", [])
                    if any("terminal" in agent for agent in suggested_agents):
                        logger.info("WORKFLOW: Classified as TERMINAL_TASK (by agents)")
                        return MessageType.TERMINAL_TASK, classification

                except Exception as attr_error:
                    logger.error(
                        f"WORKFLOW: Error processing classification attributes: {attr_error}"
                    )
                    # Continue with fallback classification

                # Check complexity for research needs
                try:
                    complexity = getattr(classification, "complexity", None)
                    if complexity in [
                        TaskComplexity.COMPLEX,
                        TaskComplexity.VERY_COMPLEX,
                    ]:
                        logger.info("WORKFLOW: Classified as RESEARCH_NEEDED (complex)")
                        return MessageType.RESEARCH_NEEDED, classification
                except Exception as complexity_error:
                    logger.error(
                        f"WORKFLOW: Error checking complexity: {complexity_error}"
                    )

            logger.info("WORKFLOW: Defaulting to GENERAL_QUERY")
            return MessageType.GENERAL_QUERY, classification

        except Exception as e:
            logger.warning(f"Classification failed, defaulting to general query: {e}")
            return MessageType.GENERAL_QUERY, None

    async def _search_knowledge(
        self,
        user_message: str,
        message_type: MessageType,
        classification: Optional[ClassificationResult],
    ) -> Tuple[KnowledgeStatus, List[Dict[str, Any]]]:
        """
        Search for relevant knowledge based on message type and classification.

        Returns:
            Tuple of (KnowledgeStatus, kb_results)
        """
        # Check if KB/Librarian is enabled in settings
        if not self.kb_librarian_enabled:
            logger.info(
                "Knowledge Base/Librarian is disabled in settings - falling back to file search"
            )
            return await self._fallback_file_search(user_message, message_type)

        # ORIGINAL CODE BELOW - Re-enable when KB initialization is fixed
        try:
            # Initialize KB librarian if needed - ASYNC TO PREVENT BLOCKING
            if self.kb_librarian is None:
                logger.info("WORKFLOW: Initializing KB Librarian asynchronously...")
                # Run KB librarian initialization in background thread to prevent blocking
                init_task = asyncio.create_task(asyncio.to_thread(get_kb_librarian))
                try:
                    # Give it 2 seconds to initialize, otherwise skip
                    self.kb_librarian = await asyncio.wait_for(init_task, timeout=2.0)
                    logger.info("WORKFLOW: KB Librarian initialized successfully")
                except asyncio.TimeoutError:
                    logger.warning(
                        "WORKFLOW: KB Librarian initialization timed out after 2s, skipping KB search"
                    )
                    return KnowledgeStatus.MISSING, []
                except Exception as e:
                    logger.warning(
                        f"WORKFLOW: KB Librarian initialization failed: {e}, skipping KB search"
                    )
                    return KnowledgeStatus.MISSING, []

            logger.info(
                "WORKFLOW: KB Librarian ready, checking initialization status..."
            )

            # CRITICAL FIX: Check if KB is initialized before searching to prevent blocking
            # This prevents the chat from hanging during KB initialization
            if (
                hasattr(self.kb_librarian, "knowledge_base")
                and self.kb_librarian.knowledge_base
            ):
                kb = self.kb_librarian.knowledge_base
                if hasattr(kb, "index") and kb.index is None:
                    logger.warning(
                        "WORKFLOW: KnowledgeBase not initialized yet, skipping search to prevent blocking"
                    )
                    return KnowledgeStatus.MISSING, []

            logger.info("WORKFLOW: Proceeding with knowledge base search...")

            # Build search query based on message type
            search_query = self._build_search_query(user_message, message_type)
            logger.info(f"WORKFLOW: Searching with query: {search_query}")

            # Search with timeout protection
            logger.info("WORKFLOW: Creating search task...")
            search_task = asyncio.create_task(
                self.kb_librarian.search_knowledge_base(search_query)
            )

            logger.info(
                f"WORKFLOW: Waiting for search results with {self.kb_search_timeout}s timeout..."
            )
            # Use configured timeout to prevent hanging
            kb_results = await asyncio.wait_for(
                search_task, timeout=self.kb_search_timeout
            )
            logger.info(
                f"WORKFLOW: Search completed, got {len(kb_results) if kb_results else 0} results"
            )

            if not kb_results:
                return KnowledgeStatus.MISSING, []

            # Filter results by confidence threshold
            filtered_results = [
                result
                for result in kb_results
                if result.get("score", 0) >= self.min_confidence_threshold
            ]

            if not filtered_results:
                return KnowledgeStatus.MISSING, kb_results[: self.max_kb_results]

            # Determine knowledge status based on results quality
            high_confidence_results = [
                result for result in filtered_results if result.get("score", 0) >= 0.7
            ]

            if len(high_confidence_results) >= 2:
                return KnowledgeStatus.FOUND, filtered_results[: self.max_kb_results]
            elif len(filtered_results) > 0:
                return KnowledgeStatus.PARTIAL, filtered_results[: self.max_kb_results]
            else:
                return KnowledgeStatus.MISSING, []

        except asyncio.TimeoutError:
            logger.warning(f"KB search timed out after {self.kb_search_timeout}s")
            return KnowledgeStatus.MISSING, []
        except Exception as e:
            logger.error(f"KB search failed: {e}")
            return KnowledgeStatus.MISSING, []

    def _build_search_query(self, user_message: str, message_type: MessageType) -> str:
        """
        Build an optimized search query based on message type.

        Args:
            user_message: Original user message
            message_type: Classified message type

        Returns:
            Optimized search query string
        """
        base_query = user_message

        # Add context-specific search terms
        if message_type == MessageType.TERMINAL_TASK:
            base_query = f"terminal command linux bash shell {user_message}"
        elif message_type == MessageType.DESKTOP_TASK:
            base_query = f"desktop GUI application interface {user_message}"
        elif message_type == MessageType.SYSTEM_TASK:
            base_query = f"system administration configuration setup {user_message}"

        return base_query

    def _needs_research(
        self,
        knowledge_status: KnowledgeStatus,
        kb_results: List[Dict[str, Any]],
        classification: Optional[ClassificationResult],
    ) -> bool:
        """
        Determine if additional research is needed based on knowledge status.

        Returns:
            True if research should be conducted
        """
        # Research agent is subordinate to librarian - only called when librarian determines need
        if not self.web_research_enabled:
            logger.info(
                "Research agent is disabled in settings - librarian will use KB/local sources only"
            )
            return False

        # Librarian determines if research agent is needed based on knowledge gaps
        if knowledge_status == KnowledgeStatus.MISSING:
            # For complex tasks that might need external research
            if classification and classification.complexity in [
                TaskComplexity.COMPLEX,
                TaskComplexity.VERY_COMPLEX,
            ]:
                # Check if it's a research-heavy request that needs web data
                if any(
                    keyword in classification.reasoning.lower()
                    for keyword in [
                        "latest",
                        "current",
                        "news",
                        "search",
                        "browse",
                        "website",
                        "online",
                    ]
                ):
                    logger.info(
                        "Librarian determining research agent is needed for missing knowledge"
                    )
                    return True

        # Use local knowledge base and file search primarily
        return False

    async def _conduct_research(
        self,
        user_message: str,
        message_type: MessageType,
        existing_kb_results: List[Dict[str, Any]],
    ) -> Tuple[Optional[Dict[str, Any]], bool, bool]:
        """
        Conduct research using available tools and agents.

        Returns:
            Tuple of (research_results, librarian_engaged, mcp_used)
        """
        research_results = {}
        librarian_engaged = False
        mcp_used = False

        try:
            # Strategy 1: Note research capability but don't execute until user confirms
            if self.web_research_enabled and message_type in [
                MessageType.RESEARCH_NEEDED,
                MessageType.GENERAL_QUERY,
            ]:
                logger.info(
                    "Research capability available - will ask user before proceeding"
                )
                # Don't execute research automatically - ask user first via yes/no dialogue
                research_results["research_available"] = True

            # Strategy 2: Use MCP for manual/help lookups (terminal tasks)
            if message_type in [MessageType.TERMINAL_TASK, MessageType.SYSTEM_TASK]:
                try:
                    mcp_results = await self._query_mcp_manuals(user_message)
                    if mcp_results:
                        research_results["mcp_manuals"] = mcp_results
                        mcp_used = True
                        logger.info("MCP manual lookup completed successfully")

                except Exception as e:
                    logger.warning(f"MCP manual lookup failed: {e}")

            return (
                research_results if research_results else None,
                librarian_engaged,
                mcp_used,
            )

        except Exception as e:
            logger.error(f"Research orchestration failed: {e}")
            return None, librarian_engaged, mcp_used

    async def _query_mcp_manuals(self, user_message: str) -> Optional[Dict[str, Any]]:
        """
        Query MCP servers for manual pages and help information.

        Returns:
            Dictionary containing manual/help information
        """
        try:
            from src.mcp_manual_integration import lookup_system_manual

            logger.info(f"Looking up system manuals for: {user_message}")
            manual_result = await lookup_system_manual(user_message)

            if manual_result:
                return {
                    "manual_data": manual_result,
                    "source": "mcp_manual_service",
                    "query": user_message,
                }

            return None

        except Exception as e:
            logger.error(f"MCP manual lookup failed: {e}")
            return None

    async def _generate_response(
        self,
        user_message: str,
        message_type: MessageType,
        knowledge_status: KnowledgeStatus,
        kb_results: List[Dict[str, Any]],
        research_results: Optional[Dict[str, Any]],
        classification: Optional[ClassificationResult],
    ) -> str:
        """
        Generate the final response based on available information.

        Args:
            user_message: Original user message
            message_type: Classified message type
            knowledge_status: Status of knowledge availability
            kb_results: Results from knowledge base search
            research_results: Results from research if conducted
            classification: Message classification results

        Returns:
            Generated response string
        """
        try:
            # Build context for LLM
            context = self._build_llm_context(
                user_message,
                message_type,
                knowledge_status,
                kb_results,
                research_results,
            )

            # Create prompt based on knowledge status
            if knowledge_status == KnowledgeStatus.FOUND:
                prompt = self._create_knowledge_based_prompt(user_message, context)
            elif knowledge_status == KnowledgeStatus.PARTIAL:
                prompt = self._create_partial_knowledge_prompt(user_message, context)
            else:  # MISSING or RESEARCH_REQUIRED
                prompt = self._create_no_knowledge_prompt(
                    user_message, message_type, research_results
                )

            # Get LLM response with failsafe and timeout
            try:
                llm_task = asyncio.create_task(
                    get_robust_llm_response(
                        prompt,
                        context={
                            "message_type": message_type.value,
                            "knowledge_status": knowledge_status.value,
                            "kb_documents_found": len(kb_results),
                            "research_conducted": research_results is not None,
                        },
                    )
                ),
                llm_response = await asyncio.wait_for(llm_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.error("LLM response timed out after 10 seconds")
                return self._generate_fallback_response(knowledge_status)
            except Exception as e:
                logger.error(f"LLM response failed: {e}")
                return self._generate_error_response(str(e))

            if llm_response and hasattr(llm_response, "content"):
                return llm_response.content
            elif (
                llm_response
                and isinstance(llm_response, dict)
                and "content" in llm_response
            ):
                return llm_response["content"]
            else:
                return (
                    str(llm_response)
                    if llm_response
                    else self._generate_fallback_response(knowledge_status)
                )

        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return self._generate_error_response(str(e))

    def _build_llm_context(
        self,
        user_message: str,
        message_type: MessageType,
        knowledge_status: KnowledgeStatus,
        kb_results: List[Dict[str, Any]],
        research_results: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build context dictionary for LLM processing"""

        context = {
            "user_query": user_message,
            "message_type": message_type.value,
            "knowledge_status": knowledge_status.value,
            "kb_context": "",
            "research_context": "",
        }

        # Add KB context
        if kb_results:
            kb_context_parts = []
            for i, result in enumerate(kb_results[:3], 1):  # Top 3 results
                title = result.get("title", f"Document {i}")
                content = result.get("content", "")[:300]  # Limit content
                confidence = result.get("score", 0)
                kb_context_parts.append(
                    f"{i}. {title} (confidence: {confidence:.2f}):\n{content}..."
                )

            context["kb_context"] = "\n\n".join(kb_context_parts)

        # Add research context
        if research_results:
            research_parts = []
            if "web_research" in research_results:
                research_parts.append(
                    "Web Research Results:\n"
                    + str(research_results["web_research"])[:500]
                )
            if "mcp_manuals" in research_results:
                research_parts.append(
                    "Manual Pages:\n" + str(research_results["mcp_manuals"])[:500]
                )

            context["research_context"] = "\n\n".join(research_parts)

        return context

    def _create_knowledge_based_prompt(
        self, user_message: str, context: Dict[str, Any]
    ) -> str:
        """Create prompt when sufficient knowledge is available"""
        return """You are AutoBot, an advanced autonomous AI platform designed for Linux system administration and intelligent task automation. You are NOT a Meta AI model or related to Transformers - you are an enterprise-grade automation platform with 20+ specialized AI agents.

The user asked: "{user_message}"

I found relevant information in my knowledge base:

{context['kb_context']}

{context['research_context'] if context['research_context'] else ''}

Please provide a comprehensive response based on this knowledge. Be specific and accurate, and cite the information sources when appropriate. If the user is asking about a terminal or desktop task, provide step-by-step instructions where applicable.

Remember: You are AutoBot - a Linux system administration expert and automation platform, NOT a chatbot or fictional character."""

    def _create_partial_knowledge_prompt(
        self, user_message: str, context: Dict[str, Any]
    ) -> str:
        """Create prompt when only partial knowledge is available"""
        return """You are AutoBot, an advanced autonomous AI platform designed for Linux system administration and intelligent task automation. You are NOT a Meta AI model or related to Transformers - you are an enterprise-grade automation platform with 20+ specialized AI agents.

The user asked: "{user_message}"

I found some relevant information, but it may not be complete:

{context['kb_context']}

{context['research_context'] if context['research_context'] else ''}

Please provide a helpful response based on the available information. If the information is incomplete, clearly indicate what additional details might be needed and suggest how the user could obtain more specific information.

Remember: You are AutoBot - a Linux system administration expert and automation platform, NOT a chatbot or fictional character."""

    def _create_no_knowledge_prompt(
        self,
        user_message: str,
        message_type: MessageType,
        research_results: Optional[Dict[str, Any]],
    ) -> str:
        """Create prompt when no knowledge is available - avoid hallucination"""

        base_response = """You are AutoBot, an advanced autonomous AI platform designed for Linux system administration and intelligent task automation. You are NOT a Meta AI model or related to Transformers - you are an enterprise-grade automation platform with 20+ specialized AI agents.

The user asked: "{user_message}"

I don't have specific knowledge about this topic in my knowledge base."""

        if research_results and "web_research" in research_results:
            base_response += """

However, I conducted research and found:
{research_results}

Based on this research, I can provide some guidance, but I recommend verifying this information from authoritative sources."""
        elif research_results and research_results.get("research_available"):
            base_response += """

Do you want me to research this topic? (yes/no)

If you answer 'no', I'll end this workflow here. If you answer 'yes', I can help research this topic with your guidance."""
        else:
            # Research agent disabled or unavailable
            if not self.web_research_enabled:
                base_response += """

Currently, the research agent is disabled in settings. I can only provide information from my local knowledge base and documentation files."""
            else:
                base_response += """

Currently, the research agent is not available. I can only provide information from my local knowledge base and documentation files."""

        return base_response

    def _generate_fallback_response(self, knowledge_status: KnowledgeStatus) -> str:
        """Generate fallback response when LLM fails"""
        if knowledge_status == KnowledgeStatus.MISSING:
            return "I don't have information about this topic in my knowledge base. Let me know if you'd like me to research it for you."
        else:
            return "I found some relevant information but had trouble processing it. Please try rephrasing your question."

    def _generate_error_response(self, error: str) -> str:
        """Generate error response"""
        return f"I encountered an error while processing your request: {error}. Please try again or rephrase your question."

    def _extract_sources(
        self,
        kb_results: List[Dict[str, Any]],
        research_results: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Extract source information for attribution"""
        sources = []

        # Add KB sources
        for result in kb_results:
            sources.append(
                {
                    "type": "knowledge_base",
                    "title": result.get("title", "Knowledge Base Entry"),
                    "confidence": result.get("score", 0),
                    "content_preview": (
                        result.get("content", "")[:100] + "..."
                        if result.get("content")
                        else ""
                    ),
                }
            )

        # Add research sources
        if research_results:
            if "web_research" in research_results:
                sources.append(
                    {
                        "type": "web_research",
                        "title": "Web Research",
                        "confidence": 0.8,
                        "content_preview": "Research conducted via browser automation",
                    }
                )
            if "mcp_manuals" in research_results:
                sources.append(
                    {
                        "type": "manual_pages",
                        "title": "System Manuals",
                        "confidence": 0.9,
                        "content_preview": "Information from system manual pages",
                    }
                )

        return sources

    async def _fallback_file_search(
        self, user_message: str, message_type: MessageType
    ) -> Tuple[KnowledgeStatus, List[Dict[str, Any]]]:
        """
        Fallback file-based search when librarian is not available.

        This is a simple grep-like search through documentation files.
        """
        try:
            import glob
            import os

            # Define search paths for different message types
            search_paths = []
            if message_type == MessageType.TERMINAL_TASK:
                search_paths.extend(
                    [
                        "docs/*terminal*.md",
                        "docs/*command*.md",
                        "docs/*bash*.md",
                        "data/system_knowledge/**/*.md",
                        "data/system_knowledge/**/*.txt",
                    ]
                )
            elif message_type == MessageType.SYSTEM_TASK:
                search_paths.extend(
                    [
                        "docs/*system*.md",
                        "docs/*admin*.md",
                        "docs/*config*.md",
                        "README.md",
                        "CLAUDE.md",
                        "docs/**/*.md",
                    ]
                )
            else:
                # General search paths
                search_paths.extend(
                    [
                        "README.md",
                        "CLAUDE.md",
                        "docs/**/*.md",
                        "data/system_knowledge/**/*.md",
                    ]
                )

            results = []
            search_terms = user_message.lower().split()[
                :3
            ]  # Use first 3 words as search terms

            for pattern in search_paths[:5]:  # Limit to 5 patterns to prevent slowness
                try:
                    files = glob.glob(pattern, recursive=True)[
                        :10
                    ]  # Max 10 files per pattern

                    for file_path in files:
                        if not os.path.exists(file_path):
                            continue

                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                content = f.read()[:5000]  # Limit content size

                                # Simple relevance scoring
                                score = 0
                                for term in search_terms:
                                    score += content.lower().count(term) * 0.1

                                if score > 0:
                                    results.append(
                                        {
                                            "title": os.path.basename(file_path),
                                            "content": (
                                                content[:500] + "..."
                                                if len(content) > 500
                                                else content
                                            ),
                                            "score": min(score, 1.0),
                                            "source": "file_search",
                                            "file_path": file_path,
                                        }
                                    )
                        except Exception as e:
                            continue  # Skip files that can't be read

                except Exception as e:
                    continue  # Skip invalid patterns

            # Sort by score and limit results
            results = sorted(results, key=lambda x: x["score"], reverse=True)[
                : self.max_kb_results
            ]

            if results:
                logger.info(f"File search found {len(results)} results")
                return KnowledgeStatus.PARTIAL, results
            else:
                logger.info("File search found no results")
                return KnowledgeStatus.MISSING, []

        except Exception as e:
            logger.error(f"Fallback file search failed: {e}")
            return KnowledgeStatus.MISSING, []


# Global instance for easy access
chat_workflow_manager = ChatWorkflowManager()


async def process_chat_message(
    user_message: str,
    chat_id: Optional[str] = None,
    conversation: Optional[Conversation] = None,
) -> ChatWorkflowResult:
    """
    Convenience function to process a chat message through the workflow.

    Args:
        user_message: The user's input message
        chat_id: Optional chat session ID
        conversation: Optional existing conversation instance

    Returns:
        ChatWorkflowResult with response and metadata
    """
    return await chat_workflow_manager.process_message(
        user_message, chat_id, conversation
    )
