# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# backend/api/agent_config.py
"""
Agent Configuration API

Provides endpoints for configuring and monitoring AI agents used throughout the system.
Each agent can have its own LLM model configuration and status monitoring.
"""

import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.services.config_service import ConfigService
from backend.services.slm_client import get_slm_client
from backend.utils.connection_utils import ModelManager
from src.constants.model_constants import ModelConstants
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# Get default LLM model from environment - uses centralized model constants
DEFAULT_LLM_MODEL = os.getenv(
    "AUTOBOT_DEFAULT_LLM_MODEL",
    os.getenv("AUTOBOT_DEFAULT_AGENT_MODEL", ModelConstants.DEFAULT_OLLAMA_MODEL),
)

# Tiered default models for different agent categories
# Tier 1 (Core): Fast, lightweight models for quick responses
# Tier 2 (Processing): Medium models for data processing
# Tier 3 (Specialized): Default model for specialized tasks
# Tier 4 (Advanced): Larger models for complex reasoning
TIER_1_MODEL = os.getenv("AUTOBOT_TIER1_MODEL", "llama3.2:1b")  # Fast core ops
TIER_2_MODEL = os.getenv("AUTOBOT_TIER2_MODEL", "llama3.2:3b")  # Processing
TIER_3_MODEL = os.getenv("AUTOBOT_TIER3_MODEL", DEFAULT_LLM_MODEL)  # Specialized
TIER_4_MODEL = os.getenv("AUTOBOT_TIER4_MODEL", DEFAULT_LLM_MODEL)  # Advanced

router = APIRouter()


async def _get_agent_config_from_slm(agent_id: str) -> Optional[dict]:
    """
    Fetch agent config from SLM.

    Args:
        agent_id: Agent identifier

    Returns:
        Config dict or None if not found
    """
    client = get_slm_client()
    if not client:
        return None

    try:
        config = await client.get_agent_config(agent_id)
        if config:
            return {
                "model": config.get("llm_model"),
                "provider": config.get("llm_provider"),
                "endpoint": config.get("llm_endpoint"),
                "timeout": config.get("llm_timeout"),
                "temperature": config.get("llm_temperature"),
                "enabled": config.get("is_active", True),
            }
    except Exception as e:
        logger.warning("Failed to get agent %s from SLM: %s", agent_id, e)

    return None


async def _get_available_models() -> list:
    """
    Fetch available models from the model manager.

    Returns:
        list: List of available model names from Ollama or other providers.
              Returns empty list if model service is unavailable.
    """
    try:
        result = await ModelManager.get_available_models()
        if result and "models" in result:
            return [
                m.get("name", m) if isinstance(m, dict) else m for m in result["models"]
            ]
        return []
    except Exception as e:
        logger.warning("Could not fetch available models: %s", e)
        return []


class AgentConfig(BaseModel):
    """Agent configuration model"""

    agent_id: str
    name: str
    model: str
    provider: str
    enabled: bool
    priority: Optional[int] = 1


class AgentModelUpdate(BaseModel):
    """Agent model update request"""

    agent_id: str
    model: str
    provider: Optional[str] = "ollama"


# Define agent types and their default configurations
# Based on src/agents/ implementations - 29 specialized agents with MCP mappings
# MCP Bridges: knowledge_mcp, vnc_mcp, sequential_thinking_mcp, structured_thinking_mcp,
#              filesystem_mcp, browser_mcp, http_client_mcp, database_mcp, git_mcp, prometheus_mcp
DEFAULT_AGENT_CONFIGS = {
    # Tier 1: Core Agents (always available, priority 1) - Fast model for quick responses
    "orchestrator": {
        "name": "Orchestrator Agent",
        "description": "Central coordinator that routes requests to appropriate agents. Invoked automatically by AsyncChatWorkflow on every user message. Uses pattern matching and LLM-based routing (AgentRouter) to select agents.",
        "default_model": TIER_1_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 1,
        "tasks": ["workflow_planning", "task_classification", "agent_coordination"],
        "mcp_tools": ["sequential_thinking_mcp", "structured_thinking_mcp"],
        "invoked_by": "AsyncChatWorkflow (automatic on every request)",
        "source_file": "src/orchestrator.py, src/agents/agent_orchestrator.py",
    },
    "chat": {
        "name": "Chat Agent",
        "description": "Handles conversational interactions, greetings, and simple Q&A. Invoked by AgentRouter when greeting patterns detected (hello, hi, thank you) or for short queries under 10 words.",
        "default_model": TIER_1_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 1,
        "tasks": ["conversation", "user_assistance", "general_queries"],
        "mcp_tools": ["knowledge_mcp"],
        "invoked_by": "AgentRouter via GREETING_PATTERNS matching",
        "source_file": "src/agents/chat_agent.py",
    },
    "classification": {
        "name": "Classification Agent",
        "description": "Classifies incoming requests by type and complexity. Invoked by Orchestrator to determine routing strategy. Uses GemmaClassificationAgent for advanced intent detection.",
        "default_model": TIER_1_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 1,
        "tasks": ["request_classification", "complexity_assessment", "routing"],
        "mcp_tools": ["structured_thinking_mcp"],
        "invoked_by": "Orchestrator (automatic during routing phase)",
        "source_file": "src/agents/classification_agent.py, src/agents/gemma_classification_agent.py",
    },
    # Tier 2: Processing Agents (on-demand, priority 2) - Medium model for data processing
    "kb_librarian": {
        "name": "Knowledge Base Librarian",
        "description": "Manages knowledge base operations including document ingestion, search, and retrieval. Invoked by AsyncChatWorkflow when knowledge patterns detected ('according to', 'based on documents'). Uses LlamaIndex for indexing.",
        "default_model": TIER_2_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["knowledge_search", "document_analysis", "information_retrieval"],
        "mcp_tools": ["knowledge_mcp", "filesystem_mcp"],
        "invoked_by": "AsyncChatWorkflow via KNOWLEDGE_PATTERNS, knowledge_mcp tools",
        "source_file": "src/agents/kb_librarian_agent.py, src/agents/kb_librarian/",
    },
    "rag": {
        "name": "RAG Agent",
        "description": "Performs Retrieval-Augmented Generation by combining vector search with LLM synthesis. Invoked as secondary agent when knowledge retrieval needs synthesis. Uses ChromaDB for vector operations.",
        "default_model": TIER_2_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["rag_queries", "context_retrieval", "knowledge_synthesis"],
        "mcp_tools": ["knowledge_mcp", "database_mcp"],
        "invoked_by": "AgentRouter as secondary_agent with KNOWLEDGE_RETRIEVAL",
        "source_file": "src/agents/rag_agent.py",
    },
    "research": {
        "name": "Research Agent",
        "description": "Conducts web research using browser automation. Invoked by AgentRouter when research patterns detected ('search web', 'research', 'find online'). Orchestrates browser_mcp for web scraping.",
        "default_model": TIER_2_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["web_research", "fact_checking", "data_gathering"],
        "mcp_tools": ["browser_mcp", "http_client_mcp", "knowledge_mcp"],
        "invoked_by": "AgentRouter via RESEARCH_PATTERNS matching",
        "source_file": "src/agents/web_research_integration_agent.py",
    },
    "knowledge_extraction": {
        "name": "Knowledge Extraction Agent",
        "description": "Extracts structured entities and relationships from unstructured text. Invoked by kb_librarian during document ingestion. Feeds data to graph_entity_extractor for knowledge graphs.",
        "default_model": TIER_2_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["entity_extraction", "relation_extraction", "knowledge_structuring"],
        "mcp_tools": ["knowledge_mcp", "filesystem_mcp"],
        "invoked_by": "kb_librarian during document processing",
        "source_file": "src/agents/knowledge_extraction_agent.py",
    },
    "knowledge_retrieval": {
        "name": "Knowledge Retrieval Agent",
        "description": "Fast semantic search using vector embeddings. Invoked by AgentRouter for knowledge queries. Primary agent for KNOWLEDGE_PATTERNS, often paired with RAG for synthesis.",
        "default_model": TIER_2_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["semantic_search", "similarity_matching", "context_retrieval"],
        "mcp_tools": ["knowledge_mcp", "database_mcp"],
        "invoked_by": "AgentRouter via KNOWLEDGE_PATTERNS as primary_agent",
        "source_file": "src/agents/knowledge_retrieval_agent.py",
    },
    "code_analysis": {
        "name": "Code Analysis Agent",
        "description": "Performs static code analysis, code review, and bug detection. Invoked via Codebase Analytics API or when code-related queries detected. Uses AST parsing and pattern matching.",
        "default_model": TIER_2_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["code_review", "static_analysis", "bug_detection"],
        "mcp_tools": ["filesystem_mcp", "git_mcp"],
        "invoked_by": "Codebase Analytics API, CODE_SEARCH_TERMS patterns",
        "source_file": "src/code_intelligence/",
    },
    # Tier 3: Specialized Agents (task-specific, priority 3) - Default model for specialized tasks
    "system_commands": {
        "name": "System Commands Agent",
        "description": "Executes system commands with full terminal streaming and security validation. Invoked by AgentRouter via SYSTEM_COMMAND_PATTERNS ('run', 'execute', 'command', 'shell', 'terminal'). Supports sudo handling and persistent sessions (ssh, tmux, screen).",
        "default_model": TIER_3_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["command_execution", "system_operations", "tool_usage"],
        "mcp_tools": ["filesystem_mcp"],
        "invoked_by": "AgentRouter via SYSTEM_COMMAND_PATTERNS matching",
        "source_file": "src/agents/system_command_agent.py",
    },
    "enhanced_system_commands": {
        "name": "Enhanced System Commands Agent",
        "description": "Advanced system command generation with security-focused validation. Extends StandardizedAgent with whitelisted commands and dangerous pattern detection. Used when higher security assurance needed.",
        "default_model": TIER_3_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["safe_command_execution", "privilege_management", "audit_logging"],
        "mcp_tools": ["filesystem_mcp", "prometheus_mcp"],
        "invoked_by": "Orchestrator for security-sensitive system operations",
        "source_file": "src/agents/enhanced_system_commands_agent.py",
    },
    "security_scanner": {
        "name": "Security Scanner Agent",
        "description": "Performs defensive security scans including port scanning, service detection, SSL analysis, and DNS enumeration. Supports vulnerability assessments with restricted target validation (localhost only by default).",
        "default_model": TIER_3_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["security_analysis", "vulnerability_scanning", "threat_assessment"],
        "mcp_tools": ["filesystem_mcp", "http_client_mcp", "database_mcp"],
        "invoked_by": "Security API endpoints, Orchestrator for security queries",
        "source_file": "src/agents/security_scanner_agent.py",
    },
    "network_discovery": {
        "name": "Network Discovery Agent",
        "description": "Discovers network assets and creates topology maps. Supports network scanning, host discovery, ARP scanning, traceroute, and asset inventory. Uses configurable default scan networks.",
        "default_model": TIER_3_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["network_scanning", "service_discovery", "topology_mapping"],
        "mcp_tools": ["http_client_mcp", "prometheus_mcp"],
        "invoked_by": "Network API endpoints, Orchestrator for network queries",
        "source_file": "src/agents/network_discovery_agent.py",
    },
    "interactive_terminal": {
        "name": "Interactive Terminal Agent",
        "description": "Manages full PTY terminal sessions with sudo handling and user takeover capability. Provides interactive I/O for persistent shell sessions (ssh, tmux, docker exec). Used by SystemCommandAgent for complex operations.",
        "default_model": TIER_3_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["terminal_sessions", "interactive_commands", "shell_management"],
        "mcp_tools": ["filesystem_mcp"],
        "invoked_by": "SystemCommandAgent for persistent session commands",
        "source_file": "src/agents/interactive_terminal_agent.py",
    },
    "web_research_assistant": {
        "name": "Web Research Assistant",
        "description": "Performs web research and integrates findings into knowledge base. Uses AdvancedWebResearcher for Playwright-based scraping. Includes search caching and quality threshold filtering for KB storage.",
        "default_model": TIER_3_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["deep_research", "source_validation", "citation_management"],
        "mcp_tools": ["browser_mcp", "http_client_mcp", "knowledge_mcp"],
        "invoked_by": "ResearchAgent, WebResearchIntegration module",
        "source_file": "src/agents/web_research_assistant.py",
    },
    "advanced_web_research": {
        "name": "Advanced Web Research Agent",
        "description": "Tier 2 web research with Playwright browser automation, anti-detection measures, and CAPTCHA handling via human-in-loop. Runs on Browser VM for isolated execution.",
        "default_model": TIER_3_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["multi_source_research", "content_synthesis", "trend_analysis"],
        "mcp_tools": [
            "browser_mcp",
            "http_client_mcp",
            "knowledge_mcp",
            "sequential_thinking_mcp",
        ],
        "invoked_by": "WebResearchAssistant, browser_mcp tools",
        "source_file": "src/agents/advanced_web_research.py",
    },
    "development_speedup": {
        "name": "Development Speedup Agent",
        "description": "Accelerates development by finding code duplicates, patterns, and optimization opportunities. Uses NPU worker for semantic code search and Redis for indexing. Integrates with Codebase Analytics.",
        "default_model": TIER_3_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["code_generation", "boilerplate_creation", "workflow_automation"],
        "mcp_tools": ["filesystem_mcp", "git_mcp"],
        "invoked_by": "Codebase Analytics API, Developer Tools UI",
        "source_file": "src/agents/development_speedup_agent.py",
    },
    "json_formatter": {
        "name": "JSON Formatter Agent",
        "description": "Parses, validates, and formats JSON responses from other LLMs. Provides robust JSON handling with fallback mechanisms, data type validation, and confidence scoring. Used for structured LLM output processing.",
        "default_model": TIER_3_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["json_formatting", "schema_validation", "data_transformation"],
        "mcp_tools": ["filesystem_mcp"],
        "invoked_by": "LLM response post-processing, structured output agents",
        "source_file": "src/agents/json_formatter_agent.py",
    },
    "graph_entity_extractor": {
        "name": "Graph Entity Extractor",
        "description": "Automatically extracts entities and relationships from conversations to populate AutoBot Memory Graph. Composes KnowledgeExtractionAgent for fact extraction and AutoBotMemoryGraph for storage. Uses co-occurrence and context for relationship inference.",
        "default_model": TIER_3_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["entity_extraction", "relationship_mapping", "graph_construction"],
        "mcp_tools": ["knowledge_mcp", "database_mcp"],
        "invoked_by": "KnowledgeExtractionAgent, conversation processing pipeline",
        "source_file": "src/agents/graph_entity_extractor.py",
    },
    # Tier 4: Advanced Agents (multi-modal, priority 4) - Larger model for complex reasoning
    "npu_code_search": {
        "name": "NPU Code Search Agent",
        "description": "High-performance semantic code search using NPU acceleration (OpenVINO) with Redis indexing. Extends StandardizedAgent with hardware-optimized embeddings. Handles large codebase analysis efficiently on NPU Worker VM.",
        "default_model": TIER_4_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": [
            "semantic_code_search",
            "npu_acceleration",
            "large_codebase_analysis",
        ],
        "mcp_tools": ["filesystem_mcp", "git_mcp", "knowledge_mcp"],
        "invoked_by": "DevelopmentSpeedupAgent, Codebase Analytics for semantic search",
        "source_file": "src/agents/npu_code_search_agent.py",
    },
    "librarian_assistant": {
        "name": "Librarian Assistant Agent",
        "description": "Performs web research using Playwright and manages knowledge. Finds relevant information, presents with source attribution, and stores quality content (above threshold) in knowledge base for future reference.",
        "default_model": TIER_4_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["document_organization", "metadata_management", "library_curation"],
        "mcp_tools": ["knowledge_mcp", "filesystem_mcp", "database_mcp"],
        "invoked_by": "ResearchAgent, knowledge_mcp tools for web research",
        "source_file": "src/agents/librarian_assistant_agent.py",
    },
    "containerized_librarian": {
        "name": "Containerized Librarian Agent",
        "description": "Performs web research using containerized Playwright service (Docker). Provides isolated execution environment for secure document processing. Connects to playwright-vnc service for browser automation.",
        "default_model": TIER_4_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": [
            "isolated_processing",
            "secure_document_handling",
            "container_orchestration",
        ],
        "mcp_tools": ["filesystem_mcp", "knowledge_mcp"],
        "invoked_by": "LibrarianAssistant when containerized mode configured",
        "source_file": "src/agents/containerized_librarian_assistant.py",
    },
    "system_knowledge_manager": {
        "name": "System Knowledge Manager",
        "description": "Manages immutable system knowledge templates and runtime copies. Handles intelligent change detection, backup creation, and knowledge base integration. Uses EnhancedKBLibrarian for document processing.",
        "default_model": TIER_4_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": [
            "knowledge_integration",
            "system_documentation",
            "context_management",
        ],
        "mcp_tools": [
            "knowledge_mcp",
            "filesystem_mcp",
            "database_mcp",
            "prometheus_mcp",
        ],
        "invoked_by": "System initialization, knowledge base maintenance tasks",
        "source_file": "src/agents/system_knowledge_manager.py",
    },
    "machine_aware_knowledge_manager": {
        "name": "Machine-Aware Knowledge Manager",
        "description": "Extends SystemKnowledgeManager with machine-specific adaptation. Detects OS type, distro, available tools, and hardware capabilities. Provides hardware-aware processing with MachineProfile for adaptive behavior.",
        "default_model": TIER_4_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": [
            "hardware_optimization",
            "resource_aware_processing",
            "adaptive_caching",
        ],
        "mcp_tools": ["knowledge_mcp", "prometheus_mcp"],
        "invoked_by": "SystemKnowledgeManager for machine-specific operations",
        "source_file": "src/agents/machine_aware_system_knowledge_manager.py",
    },
    "man_page_knowledge_integrator": {
        "name": "Man Page Knowledge Integrator",
        "description": "Scrapes, parses, and integrates Linux man pages into machine-aware knowledge system. Extracts structured data (synopsis, options, examples, see_also) from man page content with machine_id tracking.",
        "default_model": TIER_4_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["man_page_parsing", "command_documentation", "unix_knowledge"],
        "mcp_tools": ["knowledge_mcp", "filesystem_mcp"],
        "invoked_by": "MachineAwareKnowledgeManager, system initialization",
        "source_file": "src/agents/man_page_knowledge_integrator.py",
    },
    "llm_failsafe": {
        "name": "LLM Failsafe Agent",
        "description": "Multi-tier failsafe system ensuring LLM communication even when primary systems fail. Implements PRIMARY → SECONDARY → BASIC → EMERGENCY fallback tiers. Provides graceful degradation with rule-based and static responses.",
        "default_model": TIER_4_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["failover_handling", "graceful_degradation", "error_recovery"],
        "mcp_tools": [],
        "invoked_by": "LLMInterface on primary LLM failure, all LLM-dependent agents",
        "source_file": "src/agents/llm_failsafe_agent.py",
    },
    "gemma_classification": {
        "name": "Gemma Classification Agent",
        "description": "Ultra-fast classification using Google's Gemma models. Extends StandardizedAgent with Redis caching and WorkflowClassifier for keyword-based pre-filtering. Used by Orchestrator for advanced intent detection and multi-label tagging.",
        "default_model": TIER_4_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["advanced_classification", "multi_label_tagging", "intent_detection"],
        "mcp_tools": ["structured_thinking_mcp"],
        "invoked_by": "ClassificationAgent, Orchestrator for complex intent analysis",
        "source_file": "src/agents/gemma_classification_agent.py",
    },
    "standardized": {
        "name": "Standardized Agent",
        "description": "Base agent class eliminating process_request duplication across 24+ agents. Provides automatic action routing, standardized error handling, performance monitoring, and consistent response formatting. Parent class for specialized agents.",
        "default_model": TIER_4_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["standard_processing", "template_execution", "protocol_compliance"],
        "mcp_tools": [],
        "invoked_by": "Base class - not invoked directly, inherited by other agents",
        "source_file": "src/agents/standardized_agent.py",
    },
    "web_research_integration": {
        "name": "Web Research Integration Agent",
        "description": "Unified interface for web research integrating multiple research agents. Provides async handling, circuit breakers (CLOSED→OPEN→HALF_OPEN), rate limiting, and user preference management for research method selection.",
        "default_model": TIER_4_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["research_integration", "knowledge_enrichment", "source_linking"],
        "mcp_tools": ["browser_mcp", "http_client_mcp", "knowledge_mcp"],
        "invoked_by": "AsyncChatWorkflow for research queries, browser_mcp tools",
        "source_file": "src/agents/web_research_integration.py",
    },
    # Overseer Architecture: Task Decomposition & Execution
    "overseer": {
        "name": "Overseer Agent",
        "description": "Decomposes user queries into sequential executable tasks. Analyzes user intent, creates task plans with proper dependencies, and orchestrates step-by-step execution via StepExecutorAgent workers. Supports complex multi-step queries.",
        "default_model": TIER_3_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": [
            "task_decomposition",
            "plan_creation",
            "step_orchestration",
            "dependency_management",
        ],
        "mcp_tools": ["sequential_thinking_mcp", "structured_thinking_mcp"],
        "invoked_by": "AsyncChatWorkflow for complex multi-step queries requiring task planning",
        "source_file": "src/agents/overseer/overseer_agent.py",
    },
    "step_executor": {
        "name": "Step Executor Agent",
        "description": "Executes individual tasks/steps from OverseerAgent plans. Handles command validation, PTY terminal execution with streaming output, and generates two-part explanations (command explanation + output explanation). Supports security validation against dangerous patterns.",
        "default_model": TIER_3_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": [
            "step_execution",
            "command_validation",
            "pty_terminal",
            "output_streaming",
            "explanation_generation",
        ],
        "mcp_tools": ["filesystem_mcp"],
        "invoked_by": "OverseerAgent during task plan execution",
        "source_file": "src/agents/overseer/step_executor_agent.py",
    },
}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_agents",
    error_code_prefix="AGENT_CONFIG",
)
@router.get("/agents")
async def list_agents():
    """Get list of all available agents with their configurations"""
    from src.config import unified_config_manager

    llm_config = unified_config_manager.get_llm_config()
    provider_type = llm_config.get("provider_type", "local")

    agents = []
    for agent_id, config in DEFAULT_AGENT_CONFIGS.items():
        # Try SLM first, fallback to local config
        slm_config = await _get_agent_config_from_slm(agent_id)

        if slm_config:
            current_model = slm_config.get("model", config["default_model"])
            current_provider = slm_config.get("provider", config["provider"])
            enabled = slm_config.get("enabled", True)
            config_source = "slm"
        else:
            # Fallback to local unified_config_manager
            current_model = unified_config_manager.get_nested(
                f"agents.{agent_id}.model", config["default_model"]
            )
            current_provider = unified_config_manager.get_nested(
                f"agents.{agent_id}.provider", config["provider"]
            )
            enabled = unified_config_manager.get_nested(
                f"agents.{agent_id}.enabled", config["enabled"]
            )
            config_source = "local"

        # Determine status based on configuration
        status = "connected" if enabled and current_model else "disconnected"

        agent_info = {
            "id": agent_id,
            "name": config["name"],
            "description": config["description"],
            "current_model": current_model,
            "provider": current_provider,
            "enabled": enabled,
            "status": status,
            "priority": config["priority"],
            "tasks": config["tasks"],
            "mcp_tools": config.get("mcp_tools", []),
            "config_source": config_source,
            # Usage tracking requires Redis-based agent metrics service
            # See: backend/services/agent_metrics_service.py (to be implemented)
            "last_used": "N/A",
            "performance": {
                "avg_response_time": 0.0,
                "success_rate": 1.0,
                "total_requests": 0,
            },
        }
        agents.append(agent_info)

    return JSONResponse(
        status_code=200,
        content={
            "agents": agents,
            "total_count": len(agents),
            "global_provider_type": provider_type,
            "timestamp": datetime.now().isoformat(),
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_all_agents",
    error_code_prefix="AGENT_CONFIG",
)
@router.get("/agents/all")
async def get_all_agents():
    """
    Get all AutoBot agents for the Agent Registry dashboard.

    Returns list of backend agents with their configurations and status.
    """
    from src.config import unified_config_manager

    backend_agents = []
    for agent_id, config in DEFAULT_AGENT_CONFIGS.items():
        # Try SLM first, fallback to local config
        slm_config = await _get_agent_config_from_slm(agent_id)

        if slm_config:
            current_model = slm_config.get("model", config["default_model"])
            enabled = slm_config.get("enabled", True)
            config_source = "slm"
        else:
            current_model = unified_config_manager.get_nested(
                f"agents.{agent_id}.model", config["default_model"]
            )
            enabled = unified_config_manager.get_nested(
                f"agents.{agent_id}.enabled", config["enabled"]
            )
            config_source = "local"

        backend_agents.append(
            {
                "id": agent_id,
                "name": config["name"],
                "description": config["description"],
                "type": "backend",
                "model": current_model,
                "enabled": enabled,
                "status": "connected" if enabled and current_model else "disconnected",
                "priority": config["priority"],
                "tasks": config["tasks"],
                "mcp_tools": config.get("mcp_tools", []),
                "invoked_by": config.get("invoked_by", ""),
                "source_file": config.get("source_file", ""),
                "config_source": config_source,
            }
        )

    healthy_count = sum(1 for a in backend_agents if a["status"] == "connected")

    return JSONResponse(
        status_code=200,
        content={
            "agents": backend_agents,
            "summary": {
                "total": len(backend_agents),
                "healthy": healthy_count,
                "disconnected": len(backend_agents) - healthy_count,
            },
            "timestamp": datetime.now().isoformat(),
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_config",
    error_code_prefix="AGENT_CONFIG",
)
@router.get("/agents/{agent_id}")
async def get_agent_config(agent_id: str):
    """Get detailed configuration for a specific agent"""
    if agent_id not in DEFAULT_AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    from src.config import unified_config_manager

    base_config = DEFAULT_AGENT_CONFIGS[agent_id]

    # Try SLM first, fallback to local config
    slm_config = await _get_agent_config_from_slm(agent_id)

    if slm_config:
        current_model = slm_config.get("model", base_config["default_model"])
        current_provider = slm_config.get("provider", base_config["provider"])
        enabled = slm_config.get("enabled", True)
        config_source = "slm"
    else:
        current_model = unified_config_manager.get_nested(
            f"agents.{agent_id}.model", base_config["default_model"]
        )
        current_provider = unified_config_manager.get_nested(
            f"agents.{agent_id}.provider", base_config["provider"]
        )
        enabled = unified_config_manager.get_nested(
            f"agents.{agent_id}.enabled", base_config["enabled"]
        )
        config_source = "local"

    # Build detailed response
    agent_config = {
        "id": agent_id,
        "name": base_config["name"],
        "description": base_config["description"],
        "current_model": current_model,
        "provider": current_provider,
        "enabled": enabled,
        "priority": base_config["priority"],
        "tasks": base_config["tasks"],
        "mcp_tools": base_config.get("mcp_tools", []),
        "default_model": base_config["default_model"],
        "status": "connected" if enabled and current_model else "disconnected",
        "config_source": config_source,
        "configuration_options": {
            "available_models": await _get_available_models(),
            "available_providers": ["ollama", "openai", "anthropic"],
            "configurable_settings": ["model", "provider", "enabled", "priority"],
        },
        "health_check": {
            "last_check": datetime.now().isoformat(),
            "response_time": 0.0,
            "status": "healthy" if enabled else "disabled",
        },
    }

    return JSONResponse(status_code=200, content=agent_config)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_agent_model",
    error_code_prefix="AGENT_CONFIG",
)
@router.post("/agents/{agent_id}/model")
async def update_agent_model(agent_id: str, update: AgentModelUpdate):
    """Update the LLM model for a specific agent"""
    if agent_id not in DEFAULT_AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    from src.config import unified_config_manager

    # Validate the update request
    if update.agent_id != agent_id:
        raise HTTPException(
            status_code=400,
            detail="Agent ID in URL must match agent ID in request body",
        )

    # Update the configuration
    unified_config_manager.set_nested(f"agents.{agent_id}.model", update.model)
    if update.provider:
        unified_config_manager.set_nested(
            f"agents.{agent_id}.provider", update.provider
        )

    # Save the configuration and clear cache
    unified_config_manager.save_settings()
    ConfigService.clear_cache()

    logger.info(
        f"Updated agent {agent_id} model to {update.model} "
        f"(provider: {update.provider})"
    )

    # Return updated configuration
    updated_config = {
        "agent_id": agent_id,
        "agent_name": DEFAULT_AGENT_CONFIGS[agent_id]["name"],
        "model": update.model,
        "provider": update.provider,
        "status": "updated",
        "timestamp": datetime.now().isoformat(),
    }

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": f"Agent {agent_id} model updated successfully",
            "updated_config": updated_config,
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enable_agent",
    error_code_prefix="AGENT_CONFIG",
)
@router.post("/agents/{agent_id}/enable")
async def enable_agent(agent_id: str):
    """Enable a specific agent"""
    if agent_id not in DEFAULT_AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    from src.config import unified_config_manager

    unified_config_manager.set_nested(f"agents.{agent_id}.enabled", True)
    unified_config_manager.save_settings()
    ConfigService.clear_cache()

    logger.info("Enabled agent %s", agent_id)

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": f"Agent {agent_id} enabled successfully",
            "agent_name": DEFAULT_AGENT_CONFIGS[agent_id]["name"],
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="disable_agent",
    error_code_prefix="AGENT_CONFIG",
)
@router.post("/agents/{agent_id}/disable")
async def disable_agent(agent_id: str):
    """Disable a specific agent"""
    if agent_id not in DEFAULT_AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    from src.config import unified_config_manager

    unified_config_manager.set_nested(f"agents.{agent_id}.enabled", False)
    unified_config_manager.save_settings()
    ConfigService.clear_cache()

    logger.info("Disabled agent %s", agent_id)

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": f"Agent {agent_id} disabled successfully",
            "agent_name": DEFAULT_AGENT_CONFIGS[agent_id]["name"],
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_agent_health",
    error_code_prefix="AGENT_CONFIG",
)
@router.get("/agents/{agent_id}/health")
async def check_agent_health(agent_id: str):
    """Perform health check on a specific agent"""
    if agent_id not in DEFAULT_AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    from src.config import unified_config_manager

    enabled = unified_config_manager.get_nested(f"agents.{agent_id}.enabled", True)
    model = unified_config_manager.get_nested(
        f"agents.{agent_id}.model", DEFAULT_AGENT_CONFIGS[agent_id]["default_model"]
    )

    # Check provider availability using ProviderHealthManager
    provider_available = False
    start_time = datetime.now()

    try:
        from backend.services.provider_health import ProviderHealthManager

        provider_config = DEFAULT_AGENT_CONFIGS[agent_id].get("provider", "ollama")

        # Check provider health using unified health manager
        health_result = await ProviderHealthManager.check_provider_health(
            provider=provider_config,
            timeout=3.0,  # Quick check for agent status endpoint
            use_cache=True,  # Use caching to avoid excessive checks
        )

        provider_available = health_result.available

        # Log if provider is unavailable
        if not provider_available:
            logger.warning(
                f"Provider {provider_config} unavailable for agent {agent_id}: "
                f"{health_result.message}"
            )

    except Exception as e:
        logger.warning(
            f"Provider availability check failed for agent {agent_id}: {str(e)}"
        ),
        provider_available = False

    response_time = (datetime.now() - start_time).total_seconds()

    # Health check: enabled + model configured + provider available
    is_healthy = enabled and bool(model) and provider_available

    health_status = {
        "agent_id": agent_id,
        "agent_name": DEFAULT_AGENT_CONFIGS[agent_id]["name"],
        "status": "healthy" if is_healthy else "unhealthy",
        "enabled": enabled,
        "model": model,
        "checks": {
            "enabled": enabled,
            "model_configured": bool(model),
            "provider_available": provider_available,
        },
        "timestamp": datetime.now().isoformat(),
        "response_time": response_time,
    }

    return JSONResponse(status_code=200, content=health_status)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agents_overview",
    error_code_prefix="AGENT_CONFIG",
)
@router.get("/status/overview")
async def get_agents_overview():
    """Get overview of all agents' status for dashboard"""
    from src.config import unified_config_manager

    total_agents = len(DEFAULT_AGENT_CONFIGS)
    enabled_agents = 0
    healthy_agents = 0

    agent_summary = []

    for agent_id, config in DEFAULT_AGENT_CONFIGS.items():
        enabled = unified_config_manager.get_nested(
            f"agents.{agent_id}.enabled", config["enabled"]
        )
        model = unified_config_manager.get_nested(
            f"agents.{agent_id}.model", config["default_model"]
        )

        if enabled:
            enabled_agents += 1
            if model:
                healthy_agents += 1

        agent_summary.append(
            {
                "id": agent_id,
                "name": config["name"],
                "enabled": enabled,
                "status": "healthy" if enabled and model else "unhealthy",
                "priority": config["priority"],
            }
        )

    overview = {
        "total_agents": total_agents,
        "enabled_agents": enabled_agents,
        "healthy_agents": healthy_agents,
        "unhealthy_agents": enabled_agents - healthy_agents,
        "disabled_agents": total_agents - enabled_agents,
        "overall_health": (
            "good" if healthy_agents >= enabled_agents * 0.8 else "warning"
        ),
        "agents": agent_summary,
        "timestamp": datetime.now().isoformat(),
    }

    return JSONResponse(status_code=200, content=overview)
