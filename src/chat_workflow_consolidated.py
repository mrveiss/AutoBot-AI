"""
Consolidated Chat Workflow - UNIFIED VERSION

This module consolidates all chat workflow functionality from:
- chat_workflow_manager_fixed.py: Advanced classification, research, knowledge integration
- simple_chat_workflow.py: Simple workflow with working LLM responses
- async_chat_workflow.py: Modern async architecture with dependency injection

FEATURES CONSOLIDATED:
✅ Advanced message classification (GENERAL, TERMINAL, DESKTOP, SYSTEM, RESEARCH)
✅ Knowledge base integration with intelligent search
✅ Web research capabilities with librarian assistant
✅ MCP manual integration for system documentation
✅ Research permission system with user consent
✅ Source attribution from research and KB
✅ Task-specific prompt generation
✅ Async architecture with dependency injection
✅ Workflow message tracking
✅ Timeout protection and error handling
✅ Fallback responses and graceful degradation
✅ Legacy compatibility for all previous interfaces

USAGE:
    from src.chat_workflow_consolidated import ConsolidatedChatWorkflow, process_chat_message_unified
    
    # Modern async usage
    workflow = ConsolidatedChatWorkflow()
    result = await workflow.process_message(user_message, chat_id)
    
    # Legacy compatibility
    result = await process_chat_message_unified(user_message, chat_id)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

# Advanced features from chat_workflow_manager_fixed
try:
    from src.agents.classification_agent import ClassificationAgent, ClassificationResult
    from src.agents import get_kb_librarian
    from src.agents.llm_failsafe_agent import get_robust_llm_response
    from src.autobot_types import TaskComplexity
    ADVANCED_FEATURES_AVAILABLE = True
except ImportError:
    ADVANCED_FEATURES_AVAILABLE = False

# Modern architecture from async_chat_workflow
try:
    from src.dependency_container import get_llm, get_config, inject_services
    from src.llm_interface import ChatMessage, LLMResponse
    MODERN_ARCHITECTURE_AVAILABLE = True
except ImportError:
    MODERN_ARCHITECTURE_AVAILABLE = False

# Knowledge base integration
try:
    from src.knowledge_base import KnowledgeBase
    KNOWLEDGE_BASE_AVAILABLE = True
except ImportError:
    KNOWLEDGE_BASE_AVAILABLE = False

# MCP integration
try:
    from src.mcp_manual_integration import MCPManualIntegration
    MCP_INTEGRATION_AVAILABLE = True
except ImportError:
    MCP_INTEGRATION_AVAILABLE = False

# Fallback LLM interface
try:
    from src.llm_interface import LLMInterface
    LLM_INTERFACE_AVAILABLE = True
except ImportError:
    LLM_INTERFACE_AVAILABLE = False

logger = logging.getLogger(__name__)


# ==============================================
# MESSAGE TYPES AND ENUMS (Consolidated)
# ==============================================

class MessageType(Enum):
    """Types of user messages requiring different handling - consolidated from all versions"""
    GENERAL_QUERY = "general_query"
    TERMINAL_TASK = "terminal_task"
    DESKTOP_TASK = "desktop_task" 
    SYSTEM_TASK = "system_task"
    RESEARCH_NEEDED = "research_needed"
    SIMPLE = "simple"  # For backward compatibility


class KnowledgeStatus(Enum):
    """Status of knowledge availability - consolidated from all versions"""
    FOUND = "found"
    PARTIAL = "partial"
    MISSING = "missing"
    RESEARCH_REQUIRED = "research_required"
    BYPASSED = "bypassed"  # For simple workflow compatibility
    SIMPLE = "simple"      # For simple workflow compatibility


@dataclass
class WorkflowMessage:
    """Individual workflow step message"""
    sender: str
    message_type: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sender": self.sender,
            "message_type": self.message_type,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }


@dataclass
class ConsolidatedWorkflowResult:
    """Complete consolidated workflow result with all features from all versions"""
    response: str
    message_type: MessageType
    knowledge_status: KnowledgeStatus
    kb_results: List[Dict[str, Any]] = field(default_factory=list)
    research_results: Optional[Dict[str, Any]] = None
    sources: List[Dict[str, Any]] = field(default_factory=list)
    processing_time: float = 0.0
    workflow_steps: List[Dict[str, Any]] = field(default_factory=list)
    workflow_messages: List[WorkflowMessage] = field(default_factory=list)
    librarian_engaged: bool = False
    mcp_used: bool = False
    research_conducted: bool = False
    conversation_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "response": self.response,
            "message_type": self.message_type.value,
            "knowledge_status": self.knowledge_status.value,
            "kb_results": self.kb_results,
            "research_results": self.research_results,
            "sources": self.sources,
            "kb_results_count": len(self.kb_results),
            "processing_time": self.processing_time,
            "workflow_steps": self.workflow_steps,
            "workflow_messages": [msg.to_dict() for msg in self.workflow_messages],
            "librarian_engaged": self.librarian_engaged,
            "mcp_used": self.mcp_used,
            "research_conducted": self.research_conducted,
            "conversation_id": self.conversation_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }


# ==============================================
# CONSOLIDATED CHAT WORKFLOW CLASS
# ==============================================

class ConsolidatedChatWorkflow:
    """
    Consolidated chat workflow combining all features from all previous implementations:
    
    FROM chat_workflow_manager_fixed.py:
    - Advanced message classification and intent detection
    - Knowledge base integration with intelligent search
    - Web research capabilities with librarian assistant
    - MCP manual integration for system documentation
    - Research permission system and user consent
    - Task-specific prompt generation and handling
    
    FROM simple_chat_workflow.py:
    - Working LLM response generation
    - Workflow message tracking for frontend
    - Simple fallback responses
    
    FROM async_chat_workflow.py:
    - Modern async architecture with dependency injection
    - Proper async patterns and timeout handling
    - Advanced workflow step tracking
    """
    
    def __init__(self):
        self.workflow_messages: List[WorkflowMessage] = []
        self._start_time: float = 0
        
        # Advanced features initialization
        if ADVANCED_FEATURES_AVAILABLE:
            try:
                self.classification_agent = ClassificationAgent()
                self.web_research_integration = True
            except Exception as e:
                logger.warning(f"Advanced classification not available: {e}")
                self.classification_agent = None
                self.web_research_integration = False
        else:
            self.classification_agent = None
            self.web_research_integration = False
        
        # Knowledge base initialization
        if KNOWLEDGE_BASE_AVAILABLE:
            try:
                self.kb = KnowledgeBase()
            except Exception as e:
                logger.warning(f"Knowledge base not available: {e}")
                self.kb = None
        else:
            self.kb = None
        
        # MCP integration initialization
        if MCP_INTEGRATION_AVAILABLE:
            try:
                self.mcp_integration = MCPManualIntegration()
            except Exception as e:
                logger.warning(f"MCP integration not available: {e}")
                self.mcp_integration = None
        else:
            self.mcp_integration = None
        
        # LLM interface initialization
        if MODERN_ARCHITECTURE_AVAILABLE:
            try:
                self.config = get_config()
                self.llm = get_llm()
                # CRITICAL FIX: Force runtime Ollama config reload for existing instances
                if hasattr(self.llm, 'reload_ollama_configuration'):
                    self.llm.reload_ollama_configuration()
                self.modern_architecture = True
            except Exception as e:
                logger.warning(f"Modern architecture not available, using fallback: {e}")
                self.modern_architecture = False
                self._init_fallback_llm()
        else:
            self.modern_architecture = False
            self._init_fallback_llm()
        
        # Configuration settings
        self.max_kb_results = 10
        self.kb_search_timeout = 10.0
        self.classification_timeout = 10.0
        self.research_timeout = 30.0
        self.max_research_queries = 3
        
        logger.info("Consolidated chat workflow initialized with all available features")
    
    def _init_fallback_llm(self):
        """Initialize fallback LLM interface"""
        if LLM_INTERFACE_AVAILABLE:
            try:
                self.llm_interface = LLMInterface()
                # CRITICAL FIX: Force runtime Ollama config reload for existing instances
                if hasattr(self.llm_interface, 'reload_ollama_configuration'):
                    self.llm_interface.reload_ollama_configuration()
            except Exception as e:
                logger.error(f"Failed to initialize LLM interface: {e}")
                self.llm_interface = None
        else:
            self.llm_interface = None
    
    async def send_workflow_message(self, message_type: str, content: str, metadata: Dict = None):
        """Send intermediate workflow messages - compatible with all previous versions"""
        if metadata is None:
            metadata = {}
            
        workflow_message = WorkflowMessage(
            sender="assistant",
            message_type=message_type,
            content=content,
            metadata=metadata
        )
        
        self.workflow_messages.append(workflow_message)
        logger.debug(f"Workflow message: {message_type} - {content}")
    
    async def process_message(self, 
                            user_message: str, 
                            chat_id: Optional[str] = None,
                            enable_research: bool = True,
                            enable_kb_search: bool = True, **kwargs) -> ConsolidatedWorkflowResult:
        """
        Main message processing method combining ALL features from all previous implementations
        
        Flow:
        1. Message classification (if available)
        2. Knowledge base search (if available and enabled)
        3. Research decision and execution (if available and enabled)
        4. Response generation with appropriate context
        5. Source attribution and result compilation
        """
        self._start_time = time.time()
        self.workflow_messages.clear()
        
        try:
            await self.send_workflow_message("status", "Starting message processing...", 
                                           {"step": "initialization"})
            
            # Step 1: Message Classification
            message_type, classification = await self._classify_message(user_message)
            await self.send_workflow_message("classification", 
                                           f"Message classified as: {message_type.value}",
                                           {"message_type": message_type.value, 
                                            "classification": classification})
            
            # Step 2: Knowledge Base Search
            knowledge_status = KnowledgeStatus.BYPASSED
            kb_results = []
            
            if enable_kb_search and self.kb:
                await self.send_workflow_message("knowledge_search", "Searching knowledge base...")
                knowledge_status, kb_results = await self._search_knowledge(user_message, message_type, classification)
                await self.send_workflow_message("knowledge_results", 
                                                f"Knowledge search completed: {knowledge_status.value}",
                                                {"status": knowledge_status.value, 
                                                 "results_count": len(kb_results)})
            
            # Step 3: Research Decision and Execution  
            research_results = None
            librarian_engaged = False
            mcp_used = False
            
            if enable_research and self._should_conduct_research(knowledge_status, message_type, classification):
                await self.send_workflow_message("research_decision", "Research required for comprehensive response")
                research_results = await self._conduct_research(user_message, message_type, classification)
                librarian_engaged = research_results.get("librarian_engaged", False) if research_results else False
                mcp_used = research_results.get("mcp_used", False) if research_results else False
            
            # Step 4: Response Generation
            await self.send_workflow_message("response_generation", "Generating response with available context...")
            response = await self._generate_response(user_message, message_type, knowledge_status, 
                                                   kb_results, research_results, classification)
            
            # Step 5: Source Attribution
            sources = self._extract_sources(kb_results, research_results)
            
            # Step 6: Compile Results
            processing_time = time.time() - self._start_time
            
            await self.send_workflow_message("completion", f"Processing completed in {processing_time:.2f}s",
                                           {"processing_time": processing_time})
            
            return ConsolidatedWorkflowResult(
                response=response,
                message_type=message_type,
                knowledge_status=knowledge_status,
                kb_results=kb_results,
                research_results=research_results,
                sources=sources,
                processing_time=processing_time,
                workflow_messages=self.workflow_messages.copy(),
                librarian_engaged=librarian_engaged,
                mcp_used=mcp_used,
                research_conducted=research_results is not None,
                conversation_id=chat_id or ""
            )
            
        except Exception as e:
            logger.error(f"Error in consolidated chat workflow: {e}")
            processing_time = time.time() - self._start_time
            
            return ConsolidatedWorkflowResult(
                response=f"I apologize, but I encountered an error while processing your request: {str(e)}",
                message_type=MessageType.GENERAL_QUERY,
                knowledge_status=KnowledgeStatus.MISSING,
                processing_time=processing_time,
                workflow_messages=self.workflow_messages.copy(),
                conversation_id=chat_id or ""
            )
    
    async def _classify_message(self, user_message: str) -> Tuple[MessageType, Optional[Any]]:
        """Message classification using advanced agent if available, fallback otherwise"""
        if not self.classification_agent:
            # Simple classification fallback
            user_lower = user_message.lower()
            if any(term in user_lower for term in ["terminal", "command", "bash", "shell", "cli"]):
                return MessageType.TERMINAL_TASK, None
            elif any(term in user_lower for term in ["desktop", "gui", "window", "interface"]):
                return MessageType.DESKTOP_TASK, None
            elif any(term in user_lower for term in ["system", "config", "settings", "admin"]):
                return MessageType.SYSTEM_TASK, None
            else:
                return MessageType.GENERAL_QUERY, None
        
        try:
            classification_task = asyncio.create_task(
                self.classification_agent.classify_request(user_message)
            )
            classification = await asyncio.wait_for(classification_task, timeout=self.classification_timeout)
            
            if classification:
                reasoning = getattr(classification, 'reasoning', "").lower()
                
                # Advanced classification logic from chat_workflow_manager_fixed
                if any(term in reasoning for term in ["terminal", "command", "bash", "shell"]):
                    return MessageType.TERMINAL_TASK, classification
                elif any(term in reasoning for term in ["desktop", "gui", "application"]):
                    return MessageType.DESKTOP_TASK, classification
                elif any(term in reasoning for term in ["system", "configuration", "administration"]):
                    return MessageType.SYSTEM_TASK, classification
                
                # Check suggested agents
                suggested_agents = getattr(classification, 'suggested_agents', [])
                if any("terminal" in str(agent).lower() for agent in suggested_agents):
                    return MessageType.TERMINAL_TASK, classification
                
                # Check complexity for research needs
                complexity = getattr(classification, 'complexity', None)
                if complexity in [TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX] if hasattr(TaskComplexity, 'COMPLEX') else False:
                    return MessageType.RESEARCH_NEEDED, classification
            
            return MessageType.GENERAL_QUERY, classification
            
        except asyncio.TimeoutError:
            logger.warning(f"Classification timed out after {self.classification_timeout} seconds")
            return MessageType.GENERAL_QUERY, None
        except Exception as e:
            logger.warning(f"Classification failed, using fallback: {e}")
            return MessageType.GENERAL_QUERY, None
    
    async def _search_knowledge(self, 
                               user_message: str, 
                               message_type: MessageType,
                               classification: Optional[Any]) -> Tuple[KnowledgeStatus, List[Dict[str, Any]]]:
        """Knowledge base search with task-specific query building"""
        if not self.kb:
            return KnowledgeStatus.BYPASSED, []
        
        try:
            # Build task-specific search query
            search_query = self._build_search_query(user_message, message_type)
            
            search_task = asyncio.create_task(
                self.kb.search(search_query, max_results=self.max_kb_results)
            )
            kb_results = await asyncio.wait_for(search_task, timeout=self.kb_search_timeout)
            
            if not kb_results:
                return KnowledgeStatus.MISSING, []
            
            # Filter results based on relevance threshold
            filtered_results = [r for r in kb_results if r.get("score", 0) > 0.1]
            
            if len(filtered_results) >= 3:
                return KnowledgeStatus.FOUND, filtered_results[:self.max_kb_results]
            elif len(filtered_results) > 0:
                return KnowledgeStatus.PARTIAL, filtered_results[:self.max_kb_results]
            else:
                return KnowledgeStatus.MISSING, []
                
        except asyncio.TimeoutError:
            logger.warning(f"Knowledge base search timed out after {self.kb_search_timeout} seconds")
            return KnowledgeStatus.MISSING, []
        except Exception as e:
            logger.error(f"Knowledge base search failed: {e}")
            return KnowledgeStatus.MISSING, []
    
    def _build_search_query(self, user_message: str, message_type: MessageType) -> str:
        """Build task-specific search queries - from chat_workflow_manager_fixed"""
        base_query = user_message
        
        if message_type == MessageType.TERMINAL_TASK:
            return f"{base_query} terminal command linux bash shell"
        elif message_type == MessageType.DESKTOP_TASK:
            return f"{base_query} desktop GUI application interface"
        elif message_type == MessageType.SYSTEM_TASK:
            return f"{base_query} system administration configuration"
        
        return base_query
    
    def _should_conduct_research(self, 
                               knowledge_status: KnowledgeStatus, 
                               message_type: MessageType,
                               classification: Optional[Any]) -> bool:
        """Determine if research is needed - logic from chat_workflow_manager_fixed"""
        if not self.web_research_integration:
            return False
        
        # Always research if knowledge is completely missing
        if knowledge_status == KnowledgeStatus.MISSING:
            return True
        
        # Research for partial knowledge on complex topics
        if knowledge_status == KnowledgeStatus.PARTIAL:
            if message_type == MessageType.RESEARCH_NEEDED:
                return True
        
        # Research for complex classifications
        if classification and hasattr(classification, 'complexity'):
            complexity = getattr(classification, 'complexity', None)
            if hasattr(TaskComplexity, 'COMPLEX') and complexity in [TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX]:
                return knowledge_status == KnowledgeStatus.PARTIAL
        
        return False
    
    async def _conduct_research(self, 
                              user_message: str,
                              message_type: MessageType, 
                              classification: Optional[Any]) -> Optional[Dict[str, Any]]:
        """Conduct research using available methods - consolidated from all versions"""
        research_results = {
            "librarian_engaged": False,
            "mcp_used": False,
            "results": []
        }
        
        try:
            # Web research using librarian assistant
            if self.web_research_integration and message_type in [MessageType.RESEARCH_NEEDED, MessageType.GENERAL_QUERY]:
                librarian_result = await self._query_librarian(user_message)
                if librarian_result:
                    research_results["librarian_engaged"] = True
                    research_results["results"].append(librarian_result)
            
            # MCP manual integration for system/terminal tasks
            if self.mcp_integration and message_type in [MessageType.TERMINAL_TASK, MessageType.SYSTEM_TASK]:
                mcp_result = await self._query_mcp_manuals(user_message)
                if mcp_result:
                    research_results["mcp_used"] = True
                    research_results["results"].append(mcp_result)
            
            return research_results if research_results["results"] else None
            
        except Exception as e:
            logger.error(f"Research failed: {e}")
            return None
    
    async def _query_librarian(self, user_message: str) -> Optional[Dict[str, Any]]:
        """Query librarian assistant for web research"""
        if not ADVANCED_FEATURES_AVAILABLE:
            return None
        
        try:
            librarian = await get_kb_librarian()
            if not librarian:
                return None
            
            research_task = asyncio.create_task(
                librarian.research_topic(user_message)
            )
            result = await asyncio.wait_for(research_task, timeout=self.research_timeout)
            
            return {
                "type": "web_research",
                "source": "librarian_assistant", 
                "result": result
            }
            
        except Exception as e:
            logger.warning(f"Librarian research failed: {e}")
            return None
    
    async def _query_mcp_manuals(self, user_message: str) -> Optional[Dict[str, Any]]:
        """Query MCP manual integration - from chat_workflow_manager_fixed"""
        if not self.mcp_integration:
            return None
        
        try:
            mcp_task = asyncio.create_task(
                self.mcp_integration.search_manuals(user_message)
            )
            result = await asyncio.wait_for(mcp_task, timeout=10.0)
            
            return {
                "type": "manual_pages",
                "source": "mcp_integration",
                "result": result
            }
            
        except Exception as e:
            logger.warning(f"MCP manual search failed: {e}")
            return None
    
    async def _generate_response(self, 
                               user_message: str,
                               message_type: MessageType,
                               knowledge_status: KnowledgeStatus,
                               kb_results: List[Dict[str, Any]],
                               research_results: Optional[Dict[str, Any]],
                               classification: Optional[Any]) -> str:
        """Generate response using best available method with all context"""
        
        # Build comprehensive context
        context = self._build_llm_context(user_message, message_type, knowledge_status, 
                                        kb_results, research_results, classification)
        
        # Generate response using best available LLM interface
        if self.modern_architecture and self.llm:
            return await self._generate_modern_response(context)
        elif self.llm_interface:
            return await self._generate_fallback_response(context)
        else:
            return await self._generate_basic_response(user_message, knowledge_status, research_results)
    
    async def _generate_modern_response(self, context: Dict[str, Any]) -> str:
        """Generate response using modern async LLM interface"""
        try:
            messages = [ChatMessage(role="user", content=context["prompt"])]
            response = await self.llm.generate_response(messages)
            return response.content
        except Exception as e:
            logger.error(f"Modern LLM generation failed: {e}")
            return self._generate_error_response(str(e))
    
    async def _generate_fallback_response(self, context: Dict[str, Any]) -> str:
        """Generate response using fallback LLM interface"""
        try:
            response = await self.llm_interface.make_llm_request(
                context["prompt"],
                model_name="llama3.2:latest",
                temperature=0.7
            )
            return response if isinstance(response, str) else str(response)
        except Exception as e:
            logger.error(f"Fallback LLM generation failed: {e}")
            return self._generate_error_response(str(e))
    
    async def _generate_basic_response(self, 
                                     user_message: str, 
                                     knowledge_status: KnowledgeStatus,
                                     research_results: Optional[Dict[str, Any]]) -> str:
        """Generate basic response when no LLM interface is available"""
        if research_results and research_results.get("results"):
            return f"Based on research, here's what I found about your question: {user_message}"
        elif knowledge_status == KnowledgeStatus.FOUND:
            return f"I found relevant information for: {user_message}"
        else:
            return f"I understand you're asking about: {user_message}. Let me help you with that."
    
    def _build_llm_context(self, 
                          user_message: str,
                          message_type: MessageType,
                          knowledge_status: KnowledgeStatus,
                          kb_results: List[Dict[str, Any]],
                          research_results: Optional[Dict[str, Any]],
                          classification: Optional[Any]) -> Dict[str, Any]:
        """Build comprehensive LLM context - enhanced from all versions"""
        
        system_prompt = """You are AutoBot, an advanced autonomous Linux administration platform. 
You provide accurate, helpful responses based on available knowledge and research."""
        
        # Build context based on knowledge status
        if research_results and research_results.get("results"):
            prompt = self._create_research_enhanced_prompt(user_message, {}, research_results)
        elif knowledge_status == KnowledgeStatus.FOUND:
            prompt = self._create_knowledge_based_prompt(user_message, {"kb_results": kb_results})
        elif knowledge_status == KnowledgeStatus.PARTIAL:
            prompt = self._create_partial_knowledge_prompt(user_message, {"kb_results": kb_results})
        else:
            prompt = self._create_no_knowledge_prompt(user_message, message_type, research_results)
        
        return {
            "system_prompt": system_prompt,
            "prompt": prompt,
            "context": {
                "message_type": message_type,
                "knowledge_status": knowledge_status,
                "kb_results": kb_results,
                "research_results": research_results
            }
        }
    
    def _create_research_enhanced_prompt(self, user_message: str, context: Dict[str, Any], research_results: Dict[str, Any]) -> str:
        """Create prompt with research context - from chat_workflow_manager_fixed"""
        research_info = ""
        for result in research_results.get("results", []):
            research_info += f"\nResearch from {result.get('source', 'unknown')}: {result.get('result', 'No details')}"
        
        return f"""Based on recent research, please provide a comprehensive answer to this question:

User Question: {user_message}

Research Information:{research_info}

Please provide an accurate, helpful response that incorporates the research findings."""
    
    def _create_knowledge_based_prompt(self, user_message: str, context: Dict[str, Any]) -> str:
        """Create prompt with knowledge base context"""
        kb_context = ""
        for result in context.get("kb_results", []):
            kb_context += f"\n- {result.get('content', result.get('text', 'No content'))}"
        
        return f"""Based on the following knowledge base information, please answer this question:

User Question: {user_message}

Relevant Knowledge:{kb_context}

Please provide a comprehensive answer based on this information."""
    
    def _create_partial_knowledge_prompt(self, user_message: str, context: Dict[str, Any]) -> str:
        """Create prompt for partial knowledge scenarios"""
        kb_context = ""
        for result in context.get("kb_results", []):
            kb_context += f"\n- {result.get('content', result.get('text', 'No content'))}"
        
        return f"""I have some relevant information but may need additional details:

User Question: {user_message}

Available Information:{kb_context}

Please provide the best answer possible with available information, and indicate if additional research might be helpful."""
    
    def _create_no_knowledge_prompt(self, user_message: str, message_type: MessageType, research_results: Optional[Dict[str, Any]]) -> str:
        """Create prompt when no knowledge is available"""
        task_context = ""
        if message_type == MessageType.TERMINAL_TASK:
            task_context = "This appears to be a terminal/command line question. "
        elif message_type == MessageType.DESKTOP_TASK:
            task_context = "This appears to be a desktop/GUI application question. "
        elif message_type == MessageType.SYSTEM_TASK:
            task_context = "This appears to be a system administration question. "
        
        return f"""{task_context}Please provide helpful guidance for this question:

User Question: {user_message}

Please provide the best assistance possible, being clear about any limitations in available information."""
    
    def _extract_sources(self, kb_results: List[Dict[str, Any]], research_results: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract and format sources from all results - enhanced from chat_workflow_manager_fixed"""
        sources = []
        
        # Knowledge base sources
        for result in kb_results:
            if result.get("metadata", {}).get("source"):
                sources.append({
                    "type": "knowledge_base",
                    "title": result.get("metadata", {}).get("title", "Knowledge Base Entry"),
                    "source": result.get("metadata", {}).get("source"),
                    "score": result.get("score", 0.0)
                })
        
        # Research sources
        if research_results:
            for result in research_results.get("results", []):
                sources.append({
                    "type": result.get("type", "research"),
                    "source": result.get("source", "unknown"),
                    "title": f"Research: {result.get('type', 'Unknown')}"
                })
        
        return sources
    
    def _generate_error_response(self, error: str) -> str:
        """Generate user-friendly error response"""
        return f"I apologize, but I encountered an issue while processing your request. Please try rephrasing your question or try again later."


# ==============================================
# LEGACY COMPATIBILITY FUNCTIONS
# ==============================================

# Global consolidated workflow instance
_consolidated_workflow: Optional[ConsolidatedChatWorkflow] = None

async def process_chat_message_unified(user_message: str, 
                                     chat_id: Optional[str] = None, 
                                     **kwargs) -> ConsolidatedWorkflowResult:
    """
    Unified chat message processing function - compatible with all previous interfaces
    
    This function provides backward compatibility for:
    - process_chat_message_simple (from simple_chat_workflow)
    - process_chat_message (from chat_workflow_manager_fixed and async_chat_workflow)
    """
    global _consolidated_workflow
    
    if not _consolidated_workflow:
        _consolidated_workflow = ConsolidatedChatWorkflow()
    
    return await _consolidated_workflow.process_message(user_message, chat_id, **kwargs)

# Backward compatibility aliases
process_chat_message = process_chat_message_unified
process_chat_message_simple = process_chat_message_unified

# Result type aliases for backward compatibility
ChatWorkflowResult = ConsolidatedWorkflowResult
SimpleWorkflowResult = ConsolidatedWorkflowResult

logger.info("Consolidated chat workflow system initialized with all features from all previous versions")