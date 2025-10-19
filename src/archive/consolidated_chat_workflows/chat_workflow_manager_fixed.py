"""
Chat Workflow Manager - Proper Implementation with Web Research Integration
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from src.agents.classification_agent import ClassificationAgent, ClassificationResult
from src.agents import get_kb_librarian
from src.agents.llm_failsafe_agent import get_robust_llm_response
from src.conversation import Conversation
from src.autobot_types import TaskComplexity
from src.constants.network_constants import NetworkConstants

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
    research_conducted: bool = False
    error: Optional[str] = None


class ChatWorkflowManager:
    """
    Enhanced Chat Workflow Manager with Web Research Integration

    Implements the proper flow:
    1. Message classification and intent detection
    2. Knowledge base search with task-specific context
    3. Web research integration when knowledge is insufficient
    4. Response generation with clear knowledge status
    """

    def __init__(self):
        """Initialize the chat workflow manager"""
        self.classification_agent = ClassificationAgent()
        self.kb_librarian = None
        self.conversation_manager = None
        self.web_research_integration = None

        # Load settings using the proper config manager
        try:
            from src.utils.config_manager import config_manager

            settings_data = config_manager.get_all()
            self.settings = settings_data

            # Load agents config from unified configuration
            try:
                from src.config_helper import cfg

                # Load agents configuration from unified config
                agents_config = cfg.get("agents", {})
                web_research_config = cfg.get("web_research", {})
                mcp_config = cfg.get("mcp", {})

                # Merge configs into settings
                if "agents" not in self.settings:
                    self.settings["agents"] = {}
                self.settings["agents"].update(agents_config)

                if "web_research" not in self.settings:
                    self.settings["web_research"] = {}
                self.settings["web_research"].update(web_research_config)

                if "mcp" not in self.settings:
                    self.settings["mcp"] = {}
                self.settings["mcp"].update(mcp_config)

                logger.info("Loaded agents configuration from unified config system")
            except Exception as e:
                logger.info(
                    f"Could not load agents config from unified system (using defaults): {e}"
                )

        except Exception as e:
            logger.warning(f"Could not load settings: {e}")
            self.settings = {}

        # Initialize feature flags with new logic
        self.kb_librarian_enabled = (
            self.settings.get("agents", {}).get("kb_librarian", {}).get("enabled", True)
        )

        # Web research is now enabled by default but with user confirmation
        self.web_research_enabled = (
            self.settings.get("agents", {}).get("research", {}).get("enabled", True)
        )

        # Also check legacy web_research setting for backward compatibility
        if not self.web_research_enabled:
            self.web_research_enabled = self.settings.get("web_research", {}).get(
                "enabled", True
            )

        # User preference settings
        self.require_user_confirmation = self.settings.get("web_research", {}).get(
            "require_user_confirmation", True
        )
        self.auto_research_threshold = self.settings.get("web_research", {}).get(
            "auto_research_threshold", 0.3
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
        self.min_confidence_threshold = (
            self.settings.get("agents", {})
            .get("kb_librarian", {})
            .get("similarity_threshold", 0.3)
        )

        # Track research sessions for user confirmation
        self.pending_research_queries = {}

        logger.info(
            f"ChatWorkflowManager initialized - KB/Librarian enabled: {self.kb_librarian_enabled}, "
            f"Web Research available: {self.web_research_enabled}, "
            f"Requires user confirmation: {self.require_user_confirmation}"
        )

    def _is_research_response(self, user_message: str) -> Optional[bool]:
        """
        Check if user message is a yes/no response to research question.

        Returns:
            True if yes, False if no, None if not a research response
        """
        message_lower = user_message.lower().strip()

        # Direct yes/no responses
        if message_lower in [
            "yes",
            "y",
            "yeah",
            "yep",
            "sure",
            "ok",
            "okay",
            "please",
            "do it",
        ]:
            return True
        elif message_lower in [
            "no",
            "n",
            "nope",
            "nah",
            "never mind",
            "nevermind",
            "skip",
            "skip it",
        ]:
            return False

        # Phrase-based responses
        yes_phrases = [
            "yes please",
            "yes, please",
            "go ahead",
            "do it",
            "research it",
            "look it up",
            "search for it",
        ]
        no_phrases = [
            "no thanks",
            "no, thanks",
            "not needed",
            "skip it",
            "end workflow",
            "stop here",
            "dont research",
        ]

        if any(phrase in message_lower for phrase in yes_phrases):
            return True
        elif any(phrase in message_lower for phrase in no_phrases):
            return False

        return None

    async def _initialize_web_research(self):
        """Initialize web research integration if needed"""
        if self.web_research_integration is None and self.web_research_enabled:
            try:
                from src.agents.web_research_integration import (
                    get_web_research_integration,
                )

                # Get research config from settings
                research_config = self.settings.get("agents", {}).get("research", {})
                web_research_config = self.settings.get("web_research", {})

                # Merge configs
                merged_config = {**research_config, **web_research_config}

                self.web_research_integration = get_web_research_integration(
                    merged_config
                )
                logger.info("Web research integration initialized")

            except Exception as e:
                logger.error(f"Failed to initialize web research integration: {e}")
                self.web_research_enabled = False
                return False

        return self.web_research_integration is not None

    async def process_message(
        self,
        user_message: str,
        chat_id: Optional[str] = None,
        conversation: Optional[Conversation] = None,
    ) -> ChatWorkflowResult:
        """
        Process a user message through the complete chat workflow.
        """
        start_time = time.time()

        try:
            logger.info(
                f"Processing message: '{user_message[:100]}{'...' if len(user_message) > 100 else ''}'"
            )

            # Check if this is a yes/no response to research question
            research_decision = self._is_research_response(user_message)
            if research_decision is not None:
                return await self._handle_research_decision(
                    user_message, research_decision, chat_id, start_time
                )

            # Step 1: Classify the message and determine intent
            logger.info("WORKFLOW: Starting classification...")
            try:
                classify_task = asyncio.create_task(
                    self._classify_message(user_message)
                )
                message_type, classification = await asyncio.wait_for(
                    classify_task, timeout=self.classification_timeout
                )
                logger.info(
                    f"WORKFLOW: Classification completed! Message type: {message_type.value}"
                )
            except asyncio.TimeoutError:
                logger.error(
                    f"WORKFLOW: Classification timed out after {self.classification_timeout} seconds"
                )
                message_type = MessageType.GENERAL_QUERY
                classification = None
            except Exception as e:
                logger.error(f"WORKFLOW: Classification failed: {e}")
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

            # Step 3: Determine if research is needed and handle accordingly
            logger.info("WORKFLOW: Checking if research needed...")
            needs_research, should_ask_user = self._should_conduct_research(
                knowledge_status, kb_results, classification, user_message
            )

            research_results = None
            research_conducted = False
            librarian_engaged = False
            mcp_used = False

            if needs_research:
                if should_ask_user and self.require_user_confirmation:
                    # Ask user for permission to research
                    logger.info("WORKFLOW: Asking user permission for research")
                    return await self._ask_for_research_permission(
                        user_message,
                        message_type,
                        knowledge_status,
                        kb_results,
                        classification,
                        start_time,
                        chat_id,
                    )
                else:
                    # Conduct research immediately (auto-research or user doesn't require confirmation)
                    logger.info("WORKFLOW: Conducting research immediately")
                    (
                        research_results,
                        research_conducted,
                        librarian_engaged,
                        mcp_used,
                    ) = await self._conduct_research(
                        user_message, message_type, kb_results
                    )

            # Step 4: Generate response based on available information
            logger.info("WORKFLOW: Starting response generation...")
            response = await self._generate_response(
                user_message=user_message,
                message_type=message_type,
                knowledge_status=knowledge_status,
                kb_results=kb_results,
                research_results=research_results,
                classification=classification,
            )

            processing_time = time.time() - start_time
            logger.info(f"WORKFLOW: Completed in {processing_time:.2f}s")

            return ChatWorkflowResult(
                response=response,
                message_type=message_type,
                knowledge_status=knowledge_status,
                kb_results=kb_results,
                research_results=research_results,
                sources=self._extract_sources(kb_results, research_results),
                processing_time=processing_time,
                librarian_engaged=librarian_engaged,
                mcp_used=mcp_used,
                research_conducted=research_conducted,
            )

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

    async def _handle_research_decision(
        self,
        user_message: str,
        research_decision: bool,
        chat_id: Optional[str],
        start_time: float,
    ) -> ChatWorkflowResult:
        """Handle user's yes/no response to research question"""

        if research_decision:
            logger.info("WORKFLOW: User agreed to research - conducting research")

            # Get the original query from pending research
            original_query = self.pending_research_queries.get(chat_id, user_message)

            # Initialize web research if needed
            await self._initialize_web_research()

            if self.web_research_integration:
                try:
                    # Conduct web research
                    research_task = asyncio.create_task(
                        self.web_research_integration.conduct_research(original_query)
                    )
                    research_result = await asyncio.wait_for(
                        research_task, timeout=self.research_timeout
                    )

                    # Clean up pending query
                    if chat_id in self.pending_research_queries:
                        del self.pending_research_queries[chat_id]

                    # Generate response based on research results
                    if research_result.get("status") == "success":
                        response = await self._generate_research_response(
                            research_result, original_query
                        )
                        return ChatWorkflowResult(
                            response=response,
                            message_type=MessageType.RESEARCH_NEEDED,
                            knowledge_status=KnowledgeStatus.RESEARCH_REQUIRED,
                            kb_results=[],
                            research_results=research_result,
                            processing_time=time.time() - start_time,
                            research_conducted=True,
                        )
                    else:
                        # Research failed
                        response = f"I attempted to research '{original_query}' but encountered an issue: {research_result.get('message', 'Unknown error')}. I can only provide information from my local knowledge base for now."
                        return ChatWorkflowResult(
                            response=response,
                            message_type=MessageType.RESEARCH_NEEDED,
                            knowledge_status=KnowledgeStatus.MISSING,
                            kb_results=[],
                            processing_time=time.time() - start_time,
                        )

                except asyncio.TimeoutError:
                    response = f"Research for '{original_query}' timed out after {self.research_timeout} seconds. I can only provide information from my local knowledge base for now."
                    return ChatWorkflowResult(
                        response=response,
                        message_type=MessageType.RESEARCH_NEEDED,
                        knowledge_status=KnowledgeStatus.MISSING,
                        kb_results=[],
                        processing_time=time.time() - start_time,
                    )

                except Exception as e:
                    logger.error(f"Research failed: {e}")
                    response = f"Research for '{original_query}' failed: {str(e)}. I can only provide information from my local knowledge base for now."
                    return ChatWorkflowResult(
                        response=response,
                        message_type=MessageType.RESEARCH_NEEDED,
                        knowledge_status=KnowledgeStatus.MISSING,
                        kb_results=[],
                        processing_time=time.time() - start_time,
                        error=str(e),
                    )
            else:
                response = "I'm unable to conduct web research at the moment. Please try again later or ask me about something from my knowledge base."
                return ChatWorkflowResult(
                    response=response,
                    message_type=MessageType.RESEARCH_NEEDED,
                    knowledge_status=KnowledgeStatus.MISSING,
                    kb_results=[],
                    processing_time=time.time() - start_time,
                )
        else:
            logger.info("WORKFLOW: User declined research - ending workflow")

            # Clean up pending query
            if chat_id in self.pending_research_queries:
                original_query = self.pending_research_queries[chat_id]
                del self.pending_research_queries[chat_id]
            else:
                original_query = "this topic"

            response = f"Understood. I don't have information about '{original_query}' in my knowledge base, so I'll end this workflow here. Feel free to ask me about something else!"
            return ChatWorkflowResult(
                response=response,
                message_type=MessageType.GENERAL_QUERY,
                knowledge_status=KnowledgeStatus.MISSING,
                kb_results=[],
                processing_time=time.time() - start_time,
            )

    async def _classify_message(
        self, user_message: str
    ) -> Tuple[MessageType, Optional[ClassificationResult]]:
        """Classify the user message to determine appropriate handling."""
        try:
            classification = await self.classification_agent.classify_request(
                user_message
            )

            if classification:
                reasoning = (
                    classification.reasoning.lower()
                    if hasattr(classification, "reasoning")
                    else ""
                )

                # Check for task-specific classifications
                if any(
                    keyword in reasoning
                    for keyword in ["terminal", "command", "shell", "bash", "cli"]
                ):
                    return MessageType.TERMINAL_TASK, classification

                if any(
                    keyword in reasoning
                    for keyword in ["desktop", "gui", "window", "application", "app"]
                ):
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
                    return MessageType.SYSTEM_TASK, classification

                # Check for suggested agents that indicate task types
                suggested_agents = getattr(classification, "suggested_agents", [])
                if any("terminal" in agent for agent in suggested_agents):
                    return MessageType.TERMINAL_TASK, classification

                # Check complexity for research needs
                complexity = getattr(classification, "complexity", None)
                if complexity in [TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX]:
                    return MessageType.RESEARCH_NEEDED, classification

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
        """Search for relevant knowledge based on message type and classification."""

        if not self.kb_librarian_enabled:
            logger.info("Knowledge Base/Librarian is disabled in settings")
            return KnowledgeStatus.MISSING, []

        try:
            # Initialize KB librarian if needed - ASYNC TO PREVENT BLOCKING
            if self.kb_librarian is None:
                logger.info("WORKFLOW: Initializing KB Librarian asynchronously...")
                init_task = asyncio.create_task(asyncio.to_thread(get_kb_librarian))
                try:
                    self.kb_librarian = await asyncio.wait_for(init_task, timeout=2.0)
                    logger.info("WORKFLOW: KB Librarian initialized successfully")
                except asyncio.TimeoutError:
                    logger.warning("WORKFLOW: KB Librarian initialization timed out")
                    # Cancel the background task to avoid resource leaks
                    init_task.cancel()
                    try:
                        await init_task
                    except asyncio.CancelledError:
                        logger.info(
                            "WORKFLOW: KB Librarian initialization task cancelled successfully"
                        )
                    return KnowledgeStatus.MISSING, []
                except Exception as e:
                    logger.warning(f"WORKFLOW: KB Librarian initialization failed: {e}")
                    return KnowledgeStatus.MISSING, []

            # Build search query based on message type
            search_query = self._build_search_query(user_message, message_type)
            logger.info(f"WORKFLOW: Searching with query: {search_query}")

            # Search with timeout protection
            search_task = asyncio.create_task(
                self.kb_librarian.search_knowledge_base(search_query)
            )

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
        """Build an optimized search query based on message type."""
        base_query = user_message

        # Add context-specific search terms
        if message_type == MessageType.TERMINAL_TASK:
            base_query = f"terminal command linux bash shell {user_message}"
        elif message_type == MessageType.DESKTOP_TASK:
            base_query = f"desktop GUI application interface {user_message}"
        elif message_type == MessageType.SYSTEM_TASK:
            base_query = f"system administration configuration setup {user_message}"

        return base_query

    def _should_conduct_research(
        self,
        knowledge_status: KnowledgeStatus,
        kb_results: List[Dict[str, Any]],
        classification: Optional[ClassificationResult],
        user_message: str,
    ) -> Tuple[bool, bool]:
        """
        Determine if research should be conducted and if user should be asked.

        Returns:
            Tuple of (should_conduct_research, should_ask_user)
        """
        if not self.web_research_enabled:
            logger.info("Research is disabled in settings")
            return False, False

        # Auto-research conditions (no user confirmation needed)
        auto_research_triggers = [
            "latest",
            "current",
            "recent",
            "new",
            "updated",
            "today",
            "now",
            "search web",
            "look up",
            "research",
            "find online",
            "check online",
        ]

        user_message_lower = user_message.lower()
        auto_research_requested = any(
            trigger in user_message_lower for trigger in auto_research_triggers
        )

        # If knowledge is completely missing or very low confidence
        if knowledge_status == KnowledgeStatus.MISSING:
            if auto_research_requested:
                return True, False  # Research immediately, no confirmation needed
            else:
                return True, True  # Research after user confirmation

        # If knowledge is partial and low confidence
        if knowledge_status == KnowledgeStatus.PARTIAL:
            if kb_results:
                avg_confidence = sum(r.get("score", 0) for r in kb_results) / len(
                    kb_results
                )
                if avg_confidence < self.auto_research_threshold:
                    if auto_research_requested:
                        return True, False  # Research immediately
                    else:
                        return True, True  # Ask user

        # Complex queries that might benefit from current information
        if classification and classification.complexity in [
            TaskComplexity.COMPLEX,
            TaskComplexity.VERY_COMPLEX,
        ]:
            if auto_research_requested:
                return True, False
            elif knowledge_status == KnowledgeStatus.PARTIAL:
                return True, True

        return False, False

    async def _ask_for_research_permission(
        self,
        user_message: str,
        message_type: MessageType,
        knowledge_status: KnowledgeStatus,
        kb_results: List[Dict[str, Any]],
        classification: Optional[ClassificationResult],
        start_time: float,
        chat_id: Optional[str],
    ) -> ChatWorkflowResult:
        """Ask user for permission to conduct web research"""

        # Store the query for when user responds
        if chat_id:
            self.pending_research_queries[chat_id] = user_message

        # Generate appropriate question based on knowledge status
        if knowledge_status == KnowledgeStatus.MISSING:
            research_question = (
                f"I don't have specific information about '{user_message}' in my knowledge base. "
                "Would you like me to research this topic online? (yes/no)"
            )
        elif knowledge_status == KnowledgeStatus.PARTIAL:
            research_question = (
                f"I found some information about '{user_message}' in my knowledge base, "
                "but it might not be complete or current. "
                "Would you like me to research additional information online? (yes/no)"
            )
        else:
            research_question = (
                f"I have information about '{user_message}' in my knowledge base. "
                "Would you like me to supplement it with current online research? (yes/no)"
            )

        return ChatWorkflowResult(
            response=research_question,
            message_type=message_type,
            knowledge_status=KnowledgeStatus.RESEARCH_REQUIRED,
            kb_results=kb_results,
            processing_time=time.time() - start_time,
        )

    async def _conduct_research(
        self,
        user_message: str,
        message_type: MessageType,
        existing_kb_results: List[Dict[str, Any]],
    ) -> Tuple[Optional[Dict[str, Any]], bool, bool, bool]:
        """
        Conduct research using web research integration and MCP.

        Returns:
            Tuple of (research_results, research_conducted, librarian_engaged, mcp_used)
        """
        research_results = {}
        research_conducted = False
        librarian_engaged = False
        mcp_used = False

        try:
            # Initialize web research integration
            await self._initialize_web_research()

            # Strategy 1: Web research for general queries
            if self.web_research_integration and message_type in [
                MessageType.RESEARCH_NEEDED,
                MessageType.GENERAL_QUERY,
            ]:
                try:
                    logger.info("WORKFLOW: Conducting web research")
                    research_task = asyncio.create_task(
                        self.web_research_integration.conduct_research(user_message)
                    )
                    web_research_result = await asyncio.wait_for(
                        research_task, timeout=self.research_timeout
                    )

                    if web_research_result.get("status") == "success":
                        research_results["web_research"] = web_research_result
                        research_conducted = True
                        logger.info("WORKFLOW: Web research completed successfully")
                    else:
                        logger.warning(
                            f"Web research failed: {web_research_result.get('message', 'Unknown error')}"
                        )

                except asyncio.TimeoutError:
                    logger.warning(
                        f"Web research timed out after {self.research_timeout}s"
                    )
                except Exception as e:
                    logger.error(f"Web research failed: {e}")

            # Strategy 2: Use MCP for manual/help lookups (terminal/system tasks)
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
                research_conducted,
                librarian_engaged,
                mcp_used,
            )

        except Exception as e:
            logger.error(f"Research orchestration failed: {e}")
            return None, research_conducted, librarian_engaged, mcp_used

    async def _query_mcp_manuals(self, user_message: str) -> Optional[Dict[str, Any]]:
        """Query MCP servers for manual pages and help information."""
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
        """Generate the final response based on available information."""

        try:
            # Build context for LLM
            context = self._build_llm_context(
                user_message,
                message_type,
                knowledge_status,
                kb_results,
                research_results,
            )

            # Create prompt based on knowledge status and research results
            if research_results:
                prompt = self._create_research_enhanced_prompt(
                    user_message, context, research_results
                )
            elif knowledge_status == KnowledgeStatus.FOUND:
                prompt = self._create_knowledge_based_prompt(user_message, context)
            elif knowledge_status == KnowledgeStatus.PARTIAL:
                prompt = self._create_partial_knowledge_prompt(user_message, context)
            else:  # MISSING
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
                )
                llm_response = await asyncio.wait_for(llm_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.error("LLM response timed out after 10 seconds")
                return self._generate_fallback_response(
                    knowledge_status, research_results
                )
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
                    else self._generate_fallback_response(
                        knowledge_status, research_results
                    )
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
                web_res = research_results["web_research"]
                if web_res.get("status") == "success":
                    results = web_res.get("results", [])
                    if results:
                        research_parts.append("Web Research Results:\n")
                        for i, result in enumerate(results[:3], 1):
                            title = result.get("title", "Unknown")
                            content = result.get("snippet", result.get("content", ""))[
                                :200
                            ]
                            research_parts.append(f"{i}. {title}: {content}...")

            if "mcp_manuals" in research_results:
                research_parts.append(
                    "Manual Pages:\n" + str(research_results["mcp_manuals"])[:500]
                )

            context["research_context"] = "\n\n".join(research_parts)

        return context

    def _create_research_enhanced_prompt(
        self,
        user_message: str,
        context: Dict[str, Any],
        research_results: Dict[str, Any],
    ) -> str:
        """Create prompt when research results are available"""
        return f"""You are AutoBot, an advanced autonomous AI platform designed for Linux system administration and intelligent task automation. You are NOT a Meta AI model or related to Transformers - you are an enterprise-grade automation platform with 20+ specialized AI agents.

The user asked: "{user_message}"

I have gathered comprehensive information from multiple sources:

Knowledge Base Information:
{context['kb_context'] if context['kb_context'] else 'No relevant information found in knowledge base'}

Web Research Results:
{context['research_context']}

Please provide a comprehensive response based on this combined information. Prioritize the most recent and accurate information from web research while also incorporating relevant knowledge base content. Cite your sources when appropriate and indicate when information comes from web research vs. local knowledge.

Remember: You are AutoBot - a Linux system administration expert and automation platform, NOT a chatbot or fictional character."""

    def _create_knowledge_based_prompt(
        self, user_message: str, context: Dict[str, Any]
    ) -> str:
        """Create prompt when sufficient knowledge is available"""
        return f"""You are AutoBot, an advanced autonomous AI platform designed for Linux system administration and intelligent task automation. You are NOT a Meta AI model or related to Transformers - you are an enterprise-grade automation platform with 20+ specialized AI agents.

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
        return f"""You are AutoBot, an advanced autonomous AI platform designed for Linux system administration and intelligent task automation. You are NOT a Meta AI model or related to Transformers - you are an enterprise-grade automation platform with 20+ specialized AI agents.

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

        base_response = f"""You are AutoBot, an advanced autonomous AI platform designed for Linux system administration and intelligent task automation. You are NOT a Meta AI model or related to Transformers - you are an enterprise-grade automation platform with 20+ specialized AI agents.

The user asked: "{user_message}"

I don't have specific knowledge about this topic in my knowledge base."""

        if research_results and "web_research" in research_results:
            web_res = research_results["web_research"]
            if web_res.get("status") == "success":
                base_response += f"""

However, I conducted web research and found:
{research_results}

Based on this research, I can provide some guidance, but I recommend verifying this information from authoritative sources."""
        else:
            base_response += """

I can provide general guidance based on my training, but for specific, current, or detailed information about this topic, you might want to:

1. Consult the official documentation
2. Check relevant community resources
3. Ask me to research this topic online (I can do web research if you'd like)

Is there a more specific aspect of this topic I can help you with based on my available knowledge?"""

        return base_response

    async def _generate_research_response(
        self, research_result: Dict[str, Any], original_query: str
    ) -> str:
        """Generate response based on research results"""

        if research_result.get("status") != "success":
            return f"I attempted to research '{original_query}' but encountered issues. I can only provide information from my local knowledge base."

        results = research_result.get("results", [])
        if not results:
            return f"I researched '{original_query}' but didn't find substantial results. The topic might be very specific or new."

        # Build response from research results
        response_parts = [
            f"Based on my web research for '{original_query}', here's what I found:"
        ]

        for i, result in enumerate(results[:3], 1):  # Top 3 results
            title = result.get("title", "Unknown Source")
            content = result.get("snippet", result.get("content", ""))
            if content:
                content_preview = (
                    content[:200] + "..." if len(content) > 200 else content
                )
                response_parts.append(f"\n{i}. **{title}**\n   {content_preview}")

        if len(results) > 3:
            response_parts.append(f"\n(Found {len(results)} total results)")

        # Add method information
        method_used = research_result.get("method_used", "web research")
        response_parts.append(
            f"\n*This information was gathered through {method_used}. Please verify important details from authoritative sources.*"
        )

        return "\n".join(response_parts)

    def _generate_fallback_response(
        self,
        knowledge_status: KnowledgeStatus,
        research_results: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate fallback response when LLM fails"""
        if research_results:
            return "I found some information through research but had trouble processing it. Please try rephrasing your question."
        elif knowledge_status == KnowledgeStatus.MISSING:
            return "I don't have information about this topic in my knowledge base. Would you like me to research it for you?"
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
                web_res = research_results["web_research"]
                if web_res.get("status") == "success":
                    for result in web_res.get("results", []):
                        sources.append(
                            {
                                "type": "web_research",
                                "title": result.get("title", "Web Research"),
                                "url": result.get("url", ""),
                                "confidence": result.get("quality_score", 0.8),
                                "content_preview": (
                                    result.get("snippet", "")[:100] + "..."
                                    if result.get("snippet")
                                    else ""
                                ),
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


# Global instance for easy access
chat_workflow_manager = ChatWorkflowManager()


async def process_chat_message(
    user_message: str,
    chat_id: Optional[str] = None,
    conversation: Optional[Conversation] = None,
) -> ChatWorkflowResult:
    """
    Convenience function to process a chat message through the workflow.
    """
    return await chat_workflow_manager.process_message(
        user_message, chat_id, conversation
    )
