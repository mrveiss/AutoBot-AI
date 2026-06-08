# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# backend/api/agent_config.py
"""
Agent Configuration API

Provides endpoints for configuring and monitoring AI agents used throughout the system.
Each agent can have its own LLM model configuration and status monitoring.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_agent import (
    AgentConfigAllAgentsResponse,
    AgentConfigDetailResponse,
    AgentConfigEnableDisableResponse,
    AgentConfigHealthResponse,
    AgentConfigListAgentsResponse,
    AgentConfigOverviewResponse,
    AgentConfigSpecializedDetailResponse,
    AgentConfigSpecializedListResponse,
    AgentConfigUpdateModelResponse,
    AgentConfigUsageResponse,
    AgentModelUpdate,
)
from api.schemas_common import DataResponse
from api.user_management.dependencies import get_db_session
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from autobot_shared.time_utils import parse_utc_iso
from services.config_revision_service import ConfigRevisionService
from services.config_service import ConfigService
from services.slm_client import get_slm_client

logger = get_logger(__name__)

# 6-tier model mapping (#2553) — all defaults from SSOT constants.

# Routing tier — orchestrator only, no tool use
ROUTING_TIER_MODEL = config.routing_model
# Classification tier — intent detection
CLASSIFICATION_TIER_MODEL = config.classification_model
# Light processing tier — extraction, formatting, lightweight tasks
LIGHT_TIER_MODEL = config.light_processing_model
# Instruction following tier — RAG, entity extraction, instruction following
INSTRUCTION_TIER_MODEL = config.instruction_model
# System/uncensored tier — system commands, security tasks
SYSTEM_TIER_MODEL = config.system_model
# Quality tier — user-facing chat, research, code analysis
QUALITY_TIER_MODEL = config.misc.default_llm_model or config.default_agent_model

router = APIRouter()


async def _get_agent_config_from_slm(agent_id: str) -> dict | None:
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
    Fetch available model names from all configured providers.

    Delegates to ModelManagerService (#3280) which caches results for 60 s
    and aggregates Ollama, OpenAI, Anthropic, and vLLM providers.

    Returns:
        list: List of available model name strings.
              Returns empty list if all providers are unreachable.
    """
    try:
        from services.model_manager_service import get_model_names

        return await get_model_names()
    except Exception as e:
        logger.warning("Could not fetch available models: %s", e)
        return []


async def _get_available_providers() -> list:
    """Return names of LLM providers that are currently reachable."""
    try:
        from services.provider_health import ProviderHealthManager

        results = await ProviderHealthManager.check_all_providers(timeout=3.0, use_cache=True)
        return [name for name, result in results.items() if result.available]
    except Exception as e:
        logger.warning("Could not check provider availability: %s", e)
        return []


# Define agent types and their default configurations
# Based on src/agents/ implementations - 29 specialized agents with MCP mappings
# MCP Bridges: knowledge_mcp, vnc_mcp, sequential_thinking_mcp, structured_thinking_mcp,
#              filesystem_mcp, browser_mcp, http_client_mcp, database_mcp, git_mcp, prometheus_mcp
DEFAULT_AGENT_CONFIGS = {
    # Tier 1: Core Agents (always available, priority 1)
    "orchestrator": {
        "name": "Orchestrator Agent",
        "description": "Central coordinator that routes requests to appropriate agents. Invoked automatically by AsyncChatWorkflow on every user message. Uses pattern matching and LLM-based routing (AgentRouter) to select agents.",
        "default_model": ROUTING_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 1,
        "tasks": ["workflow_planning", "task_classification", "agent_coordination"],
        "mcp_tools": [
            "memory_mcp",
            "sequential_thinking_mcp",
            "structured_thinking_mcp",
            "shrimp_task_manager_mcp",
        ],
        "invoked_by": "AsyncChatWorkflow (automatic on every request)",
        "source_file": "orchestrator.py, agents/agent_orchestration/coordinator.py",
    },
    "chat": {
        "name": "Chat Agent",
        "description": "Handles conversational interactions, greetings, and simple Q&A. Invoked by AgentRouter when greeting patterns detected (hello, hi, thank you) or for short queries under 10 words.",
        "default_model": QUALITY_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 1,
        "tasks": ["conversation", "user_assistance", "general_queries"],
        "mcp_tools": ["memory_mcp", "knowledge_mcp", "structured_thinking_mcp"],
        "invoked_by": "AgentRouter via GREETING_PATTERNS matching",
        "source_file": "src/agents/chat_agent.py",
    },
    "classification": {
        "name": "Classification Agent",
        "description": "Classifies incoming requests by type and complexity. Invoked by Orchestrator to determine routing strategy. Uses GemmaClassificationAgent for advanced intent detection.",
        "default_model": CLASSIFICATION_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 1,
        "tasks": ["request_classification", "complexity_assessment", "routing"],
        "mcp_tools": ["memory_mcp", "structured_thinking_mcp", "filesystem_mcp"],
        "invoked_by": "Orchestrator (automatic during routing phase)",
        "source_file": "src/agents/classification_agent.py, src/agents/gemma_classification_agent.py",
    },
    # Tier 2: Processing Agents (on-demand, priority 2)
    "kb_librarian": {
        "name": "Knowledge Base Librarian",
        "description": "Manages knowledge base operations including document ingestion, search, and retrieval. Invoked by AsyncChatWorkflow when knowledge patterns detected ('according to', 'based on documents'). Uses LlamaIndex for indexing.",
        "default_model": LIGHT_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["knowledge_search", "document_analysis", "information_retrieval"],
        "mcp_tools": [
            "memory_mcp",
            "knowledge_mcp",
            "filesystem_mcp",
            "shrimp_task_manager_mcp",
        ],
        "invoked_by": "AsyncChatWorkflow via KNOWLEDGE_PATTERNS, knowledge_mcp tools",
        "source_file": "src/agents/kb_librarian_agent.py, src/agents/kb_librarian/",
    },
    "rag": {
        "name": "RAG Agent",
        "description": "Performs Retrieval-Augmented Generation by combining vector search with LLM synthesis. Invoked as secondary agent when knowledge retrieval needs synthesis. Uses ChromaDB for vector operations.",
        "default_model": INSTRUCTION_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["rag_queries", "context_retrieval", "knowledge_synthesis"],
        "mcp_tools": [
            "memory_mcp",
            "knowledge_mcp",
            "database_mcp",
            "sequential_thinking_mcp",
        ],
        "invoked_by": "AgentRouter as secondary_agent with KNOWLEDGE_RETRIEVAL",
        "source_file": "src/agents/rag_agent.py",
    },
    "research": {
        "name": "Research Agent",
        "description": "Conducts web research using browser automation. Invoked by AgentRouter when research patterns detected ('search web', 'research', 'find online'). Orchestrates browser_mcp for web scraping.",
        "default_model": QUALITY_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["web_research", "fact_checking", "data_gathering"],
        "mcp_tools": [
            "memory_mcp",
            "browser_mcp",
            "http_client_mcp",
            "knowledge_mcp",
            "sequential_thinking_mcp",
        ],
        "invoked_by": "AgentRouter via RESEARCH_PATTERNS matching",
        "source_file": "src/agents/web_research_integration_agent.py",
    },
    "knowledge_extraction": {
        "name": "Knowledge Extraction Agent",
        "description": "Extracts structured entities and relationships from unstructured text. Invoked by kb_librarian during document ingestion. Feeds data to graph_entity_extractor for knowledge graphs.",
        "default_model": LIGHT_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["entity_extraction", "relation_extraction", "knowledge_structuring"],
        "mcp_tools": [
            "memory_mcp",
            "knowledge_mcp",
            "filesystem_mcp",
            "structured_thinking_mcp",
        ],
        "invoked_by": "kb_librarian during document processing",
        "source_file": "src/agents/knowledge_extraction_agent.py",
    },
    "knowledge_retrieval": {
        "name": "Knowledge Retrieval Agent",
        "description": "Fast semantic search using vector embeddings. Invoked by AgentRouter for knowledge queries. Primary agent for KNOWLEDGE_PATTERNS, often paired with RAG for synthesis.",
        "default_model": LIGHT_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["semantic_search", "similarity_matching", "context_retrieval"],
        "mcp_tools": [
            "memory_mcp",
            "knowledge_mcp",
            "database_mcp",
            "sequential_thinking_mcp",
        ],
        "invoked_by": "AgentRouter via KNOWLEDGE_PATTERNS as primary_agent",
        "source_file": "src/agents/knowledge_retrieval_agent.py",
    },
    "code_analysis": {
        "name": "Code Analysis Agent",
        "description": "Performs static code analysis, code review, and bug detection. Invoked via Codebase Analytics API or when code-related queries detected. Uses AST parsing and pattern matching.",
        "default_model": QUALITY_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["code_review", "static_analysis", "bug_detection"],
        "mcp_tools": [
            "memory_mcp",
            "filesystem_mcp",
            "git_mcp",
            "sequential_thinking_mcp",
            "shrimp_task_manager_mcp",
        ],
        "invoked_by": "Codebase Analytics API, CODE_SEARCH_TERMS patterns",
        "source_file": "src/code_intelligence/",
    },
    # Tier 3: Specialized Agents (task-specific, priority 3)
    "system_commands": {
        "name": "System Commands Agent",
        "description": "Executes system commands with full terminal streaming and security validation. Invoked by AgentRouter via SYSTEM_COMMAND_PATTERNS ('run', 'execute', 'command', 'shell', 'terminal'). Supports sudo handling and persistent sessions (ssh, tmux, screen).",
        "default_model": SYSTEM_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["command_execution", "system_operations", "tool_usage"],
        "mcp_tools": ["memory_mcp", "filesystem_mcp", "sequential_thinking_mcp"],
        "invoked_by": "AgentRouter via SYSTEM_COMMAND_PATTERNS matching",
        "source_file": "src/agents/system_command_agent.py",
    },
    "enhanced_system_commands": {
        "name": "Enhanced System Commands Agent",
        "description": "Advanced system command generation with security-focused validation. Extends StandardizedAgent with whitelisted commands and dangerous pattern detection. Used when higher security assurance needed.",
        "default_model": SYSTEM_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["safe_command_execution", "privilege_management", "audit_logging"],
        "mcp_tools": [
            "memory_mcp",
            "filesystem_mcp",
            "prometheus_mcp",
            "sequential_thinking_mcp",
        ],
        "invoked_by": "Orchestrator for security-sensitive system operations",
        "source_file": "src/agents/enhanced_system_commands_agent.py",
    },
    "security_scanner": {
        "name": "Security Scanner Agent",
        "description": "Performs defensive security scans including port scanning, service detection, SSL analysis, and DNS enumeration. Supports vulnerability assessments with restricted target validation (localhost only by default).",
        "default_model": SYSTEM_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["security_analysis", "vulnerability_scanning", "threat_assessment"],
        "mcp_tools": [
            "memory_mcp",
            "filesystem_mcp",
            "http_client_mcp",
            "database_mcp",
            "sequential_thinking_mcp",
        ],
        "invoked_by": "Security API endpoints, Orchestrator for security queries",
        "source_file": "src/agents/security_scanner_agent.py",
    },
    "network_discovery": {
        "name": "Network Discovery Agent",
        "description": "Discovers network assets and creates topology maps. Supports network scanning, host discovery, ARP scanning, traceroute, and asset inventory. Uses configurable default scan networks.",
        "default_model": INSTRUCTION_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["network_scanning", "service_discovery", "topology_mapping"],
        "mcp_tools": [
            "memory_mcp",
            "http_client_mcp",
            "prometheus_mcp",
            "sequential_thinking_mcp",
        ],
        "invoked_by": "Network API endpoints, Orchestrator for network queries",
        "source_file": "src/agents/network_discovery_agent.py",
    },
    "interactive_terminal": {
        "name": "Interactive Terminal Agent",
        "description": "Manages full PTY terminal sessions with sudo handling and user takeover capability. Provides interactive I/O for persistent shell sessions (ssh, tmux, docker exec). Used by SystemCommandAgent for complex operations.",
        "default_model": SYSTEM_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["terminal_sessions", "interactive_commands", "shell_management"],
        "mcp_tools": ["memory_mcp", "filesystem_mcp", "sequential_thinking_mcp"],
        "invoked_by": "SystemCommandAgent for persistent session commands",
        "source_file": "src/agents/interactive_terminal_agent.py",
    },
    "web_researcher": {
        "name": "Web Researcher",
        "description": "Consolidated web research with Playwright browser automation, anti-detection, CAPTCHA handling, circuit breakers, rate limiting, caching, and KB integration. Replaces advanced_web_research, research_agent, web_research_assistant, web_research_integration (Issue #1443).",
        "default_model": QUALITY_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": [
            "deep_research",
            "source_validation",
            "citation_management",
            "multi_source_research",
            "content_synthesis",
            "trend_analysis",
        ],
        "mcp_tools": [
            "memory_mcp",
            "browser_mcp",
            "http_client_mcp",
            "knowledge_mcp",
            "sequential_thinking_mcp",
            "shrimp_task_manager_mcp",
        ],
        "invoked_by": "workflow, security_scanner, kb_librarian",
        "source_file": "src/agents/web_researcher.py",
    },
    "development_speedup": {
        "name": "Development Speedup Agent",
        "description": "Accelerates development by finding code duplicates, patterns, and optimization opportunities. Uses NPU worker for semantic code search and Redis for indexing. Integrates with Codebase Analytics.",
        "default_model": QUALITY_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["code_generation", "boilerplate_creation", "workflow_automation"],
        "mcp_tools": [
            "memory_mcp",
            "filesystem_mcp",
            "git_mcp",
            "sequential_thinking_mcp",
            "shrimp_task_manager_mcp",
        ],
        "invoked_by": "Codebase Analytics API, Developer Tools UI",
        "source_file": "src/agents/development_speedup_agent.py",
    },
    "json_formatter": {
        "name": "JSON Formatter Agent",
        "description": "Parses, validates, and formats JSON responses from other LLMs. Provides robust JSON handling with fallback mechanisms, data type validation, and confidence scoring. Used for structured LLM output processing.",
        "default_model": LIGHT_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["json_formatting", "schema_validation", "data_transformation"],
        "mcp_tools": ["memory_mcp", "filesystem_mcp", "structured_thinking_mcp"],
        "invoked_by": "LLM response post-processing, structured output agents",
        "source_file": "src/agents/json_formatter_agent.py",
    },
    "graph_entity_extractor": {
        "name": "Graph Entity Extractor",
        "description": "Automatically extracts entities and relationships from conversations to populate AutoBot Memory Graph. Composes KnowledgeExtractionAgent for fact extraction and AutoBotMemoryGraph for storage. Uses co-occurrence and context for relationship inference.",
        "default_model": INSTRUCTION_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["entity_extraction", "relationship_mapping", "graph_construction"],
        "mcp_tools": [
            "memory_mcp",
            "knowledge_mcp",
            "database_mcp",
            "sequential_thinking_mcp",
        ],
        "invoked_by": "KnowledgeExtractionAgent, conversation processing pipeline",
        "source_file": "src/agents/graph_entity_extractor.py",
    },
    # Tier 4: Advanced Agents (multi-modal, priority 4) - Larger model for complex reasoning
    "npu_code_search": {
        "name": "NPU Code Search Agent",
        "description": "High-performance semantic code search using NPU acceleration (OpenVINO) with Redis indexing. Extends StandardizedAgent with hardware-optimized embeddings. Handles large codebase analysis efficiently on NPU Worker VM.",
        "default_model": LIGHT_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": [
            "semantic_code_search",
            "npu_acceleration",
            "large_codebase_analysis",
        ],
        "mcp_tools": [
            "memory_mcp",
            "filesystem_mcp",
            "git_mcp",
            "knowledge_mcp",
            "sequential_thinking_mcp",
        ],
        "invoked_by": "DevelopmentSpeedupAgent, Codebase Analytics for semantic search",
        "source_file": "src/agents/npu_code_search_agent.py",
    },
    "librarian_assistant": {
        "name": "Librarian Assistant Agent",
        "description": (
            "Performs web research via the browser VM Playwright service (.25). "
            "Searches the web, extracts page content, assesses quality, and stores "
            "high-quality results in the knowledge base. Called by the orchestrator "
            "when local KB results are insufficient or the query requires current data."
        ),
        "default_model": INSTRUCTION_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["web_research", "content_extraction", "knowledge_storage"],
        "mcp_tools": [
            "memory_mcp",
            "knowledge_mcp",
            "filesystem_mcp",
            "browser_mcp",
            "sequential_thinking_mcp",
        ],
        "invoked_by": "Orchestrator when external research is needed",
        "source_file": "src/agents/librarian_assistant.py",
    },
    "system_knowledge_manager": {
        "name": "System Knowledge Manager",
        "description": "Manages immutable system knowledge templates and runtime copies. Handles intelligent change detection, backup creation, and knowledge base integration. Uses the kb_librarian package for document processing.",
        "default_model": QUALITY_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": [
            "knowledge_integration",
            "system_documentation",
            "context_management",
        ],
        "mcp_tools": [
            "memory_mcp",
            "knowledge_mcp",
            "filesystem_mcp",
            "database_mcp",
            "prometheus_mcp",
            "sequential_thinking_mcp",
            "shrimp_task_manager_mcp",
        ],
        "invoked_by": "System initialization, knowledge base maintenance tasks",
        "source_file": "src/agents/system_knowledge_manager.py",
    },
    "machine_aware_knowledge_manager": {
        "name": "Machine-Aware Knowledge Manager",
        "description": "Extends SystemKnowledgeManager with machine-specific adaptation. Detects OS type, distro, available tools, and hardware capabilities. Provides hardware-aware processing with MachineProfile for adaptive behavior.",
        "default_model": QUALITY_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": [
            "hardware_optimization",
            "resource_aware_processing",
            "adaptive_caching",
        ],
        "mcp_tools": [
            "memory_mcp",
            "knowledge_mcp",
            "prometheus_mcp",
            "sequential_thinking_mcp",
        ],
        "invoked_by": "SystemKnowledgeManager for machine-specific operations",
        "source_file": "src/agents/machine_aware_system_knowledge_manager.py",
    },
    "man_page_knowledge_integrator": {
        "name": "Man Page Knowledge Integrator",
        "description": "Scrapes, parses, and integrates Linux man pages into machine-aware knowledge system. Extracts structured data (synopsis, options, examples, see_also) from man page content with machine_id tracking.",
        "default_model": INSTRUCTION_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["man_page_parsing", "command_documentation", "unix_knowledge"],
        "mcp_tools": [
            "memory_mcp",
            "knowledge_mcp",
            "filesystem_mcp",
            "sequential_thinking_mcp",
        ],
        "invoked_by": "MachineAwareKnowledgeManager, system initialization",
        "source_file": "src/agents/man_page_knowledge_integrator.py",
    },
    "llm_failsafe": {
        "name": "LLM Failsafe Agent",
        "description": "Multi-tier failsafe system ensuring LLM communication even when primary systems fail. Implements PRIMARY → SECONDARY → BASIC → EMERGENCY fallback tiers. Provides graceful degradation with rule-based and static responses.",
        "default_model": SYSTEM_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["failover_handling", "graceful_degradation", "error_recovery"],
        "mcp_tools": ["memory_mcp"],
        "invoked_by": "LLMInterface on primary LLM failure, all LLM-dependent agents",
        "source_file": "src/agents/llm_failsafe_agent.py",
    },
    "gemma_classification": {
        "name": "Gemma Classification Agent",
        "description": "Ultra-fast classification using Google's Gemma models. Extends StandardizedAgent with Redis caching and WorkflowClassifier for keyword-based pre-filtering. Used by Orchestrator for advanced intent detection and multi-label tagging.",
        "default_model": CLASSIFICATION_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["advanced_classification", "multi_label_tagging", "intent_detection"],
        "mcp_tools": ["memory_mcp", "structured_thinking_mcp", "filesystem_mcp"],
        "invoked_by": "ClassificationAgent, Orchestrator for complex intent analysis",
        "source_file": "src/agents/gemma_classification_agent.py",
    },
    "standardized": {
        "name": "Standardized Agent",
        "description": "Base agent class eliminating process_request duplication across 24+ agents. Provides automatic action routing, standardized error handling, performance monitoring, and consistent response formatting. Parent class for specialized agents.",
        "default_model": QUALITY_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["standard_processing", "template_execution", "protocol_compliance"],
        "mcp_tools": ["memory_mcp", "structured_thinking_mcp"],
        "invoked_by": "Base class - not invoked directly, inherited by other agents",
        "source_file": "src/agents/standardized_agent.py",
    },
    "web_research_integration": {
        "name": "Web Research Integration Agent",
        "description": "Unified interface for web research integrating multiple research agents. Provides async handling, circuit breakers (CLOSED→OPEN→HALF_OPEN), rate limiting, and user preference management for research method selection.",
        "default_model": QUALITY_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["research_integration", "knowledge_enrichment", "source_linking"],
        "mcp_tools": [
            "memory_mcp",
            "browser_mcp",
            "http_client_mcp",
            "knowledge_mcp",
            "sequential_thinking_mcp",
            "shrimp_task_manager_mcp",
        ],
        "invoked_by": "AsyncChatWorkflow for research queries, browser_mcp tools",
        "source_file": "src/agents/web_research_integration.py",
    },
    # Overseer Architecture: Task Decomposition & Execution
    "overseer": {
        "name": "Overseer Agent",
        "description": "Decomposes user queries into sequential executable tasks. Analyzes user intent, creates task plans with proper dependencies, and orchestrates step-by-step execution via StepExecutorAgent workers. Supports complex multi-step queries.",
        "default_model": QUALITY_TIER_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": [
            "task_decomposition",
            "plan_creation",
            "step_orchestration",
            "dependency_management",
        ],
        "mcp_tools": [
            "memory_mcp",
            "sequential_thinking_mcp",
            "structured_thinking_mcp",
            "shrimp_task_manager_mcp",
        ],
        "invoked_by": "AsyncChatWorkflow for complex multi-step queries requiring task planning",
        "source_file": "src/agents/overseer/overseer_agent.py",
    },
    "step_executor": {
        "name": "Step Executor Agent",
        "description": "Executes individual tasks/steps from OverseerAgent plans. Handles command validation, PTY terminal execution with streaming output, and generates two-part explanations (command explanation + output explanation). Supports security validation against dangerous patterns.",
        "default_model": INSTRUCTION_TIER_MODEL,
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
        "mcp_tools": [
            "memory_mcp",
            "filesystem_mcp",
            "sequential_thinking_mcp",
            "shrimp_task_manager_mcp",
        ],
        "invoked_by": "OverseerAgent during task plan execution",
        "source_file": "src/agents/overseer/step_executor_agent.py",
    },
}


async def _resolve_agent_effective_config(agent_id: str, config: dict, unified_config_manager) -> tuple:
    """Helper for list_agents and get_all_agents. Ref: #1088.

    Resolves model, provider, enabled, and config_source for an agent
    by checking SLM first and falling back to the local config manager.

    Returns:
        Tuple of (current_model, current_provider, enabled, config_source)
    """
    slm_config = await _get_agent_config_from_slm(agent_id)

    if slm_config:
        return (
            slm_config.get("model", config["default_model"]),
            slm_config.get("provider", config["provider"]),
            slm_config.get("enabled", True),
            "slm",
        )

    current_model = unified_config_manager.get_nested(f"agents.{agent_id}.model", config["default_model"])
    current_provider = unified_config_manager.get_nested(f"agents.{agent_id}.provider", config["provider"])
    enabled = unified_config_manager.get_nested(f"agents.{agent_id}.enabled", config["enabled"])
    return current_model, current_provider, enabled, "local"


@router.get("/agents", response_model=DataResponse[AgentConfigListAgentsResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_agents",
    error_code_prefix="AGENT_CONFIG",
)
async def list_agents(admin_check: bool = Depends(check_admin_permission)):
    """
    Get list of all available agents with their configurations

    Issue #744: Requires admin authentication.
    """
    from config import unified_config_manager

    llm_config = unified_config_manager.get_llm_config()
    provider_type = llm_config.get("provider_type", "local")

    agents = []
    for agent_id, agent_cfg in DEFAULT_AGENT_CONFIGS.items():
        (
            current_model,
            current_provider,
            enabled,
            config_source,
        ) = await _resolve_agent_effective_config(agent_id, agent_cfg, unified_config_manager)

        status = "connected" if enabled and current_model else "disconnected"

        agent_info = {
            "id": agent_id,
            "name": agent_cfg["name"],
            "description": agent_cfg["description"],
            "current_model": current_model,
            "provider": current_provider,
            "enabled": enabled,
            "status": status,
            "priority": agent_cfg["priority"],
            "tasks": agent_cfg["tasks"],
            "mcp_tools": agent_cfg.get("mcp_tools", []),
            "config_source": config_source,
            "last_used": None,
            "performance": {
                "avg_response_time": 0.0,
                "success_rate": 0.0,
                "total_requests": 0,
            },
        }
        agents.append(agent_info)

    # Enrich with live analytics (best-effort; missing data stays at defaults)
    try:
        from services.agent_analytics import get_agent_analytics

        analytics = get_agent_analytics()
        metrics_by_id = {m.agent_id: m for m in await analytics.get_all_agents_metrics()}
        for info in agents:
            m = metrics_by_id.get(info["id"])
            if m:
                info["last_used"] = m.last_activity
                info["performance"] = {
                    "avg_response_time": round(m.avg_duration_ms / 1000, 3),
                    "success_rate": round(m.success_rate / 100, 4),
                    "total_requests": m.total_tasks,
                }
    except Exception as _analytics_err:
        logger.debug("Analytics enrichment failed: %s", _analytics_err)

    return JSONResponse(
        status_code=200,
        content={
            "agents": agents,
            "total_count": len(agents),
            "global_provider_type": provider_type,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        },
    )


async def _resolve_agent_entry(agent_id: str, config: dict, unified_config_manager) -> dict:
    """Resolve model, enabled state, and config_source for a single agent. Ref: #2735.

    Tries SLM first; falls back to local unified config.
    """
    slm_config = await _get_agent_config_from_slm(agent_id)
    if slm_config:
        current_model = slm_config.get("model", config["default_model"])
        enabled = slm_config.get("enabled", True)
        config_source = "slm"
    else:
        current_model = unified_config_manager.get_nested(f"agents.{agent_id}.model", config["default_model"])
        enabled = unified_config_manager.get_nested(f"agents.{agent_id}.enabled", config["enabled"])
        config_source = "local"

    return {
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


@router.get("/agents/all", response_model=DataResponse[AgentConfigAllAgentsResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_all_agents",
    error_code_prefix="AGENT_CONFIG",
)
async def get_all_agents(admin_check: bool = Depends(check_admin_permission)):
    """
    Get all AutoBot agents for the Agent Registry dashboard.

    Returns list of backend agents with their configurations and status.

    Issue #744: Requires admin authentication.
    """
    from config import unified_config_manager

    backend_agents = []
    for agent_id, agent_cfg in DEFAULT_AGENT_CONFIGS.items():
        backend_agents.append(await _resolve_agent_entry(agent_id, agent_cfg, unified_config_manager))

    healthy_count = sum(1 for a in backend_agents if a["status"] == "connected")

    # Include specialized agents in the combined response (#1794)
    from services.specialized_agent_service import SpecializedAgentService

    spec_service = SpecializedAgentService()
    specialized_agents = spec_service.list_agents()

    return JSONResponse(
        status_code=200,
        content={
            "agents": backend_agents,
            "specialized_agents": specialized_agents,
            "summary": {
                "total": len(backend_agents),
                "total_specialized": len(specialized_agents),
                "healthy": healthy_count,
                "disconnected": len(backend_agents) - healthy_count,
            },
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        },
    )


@router.get(
    "/agents/specialized",
    response_model=DataResponse[AgentConfigSpecializedListResponse],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_specialized_agents",
    error_code_prefix="AGENT_CONFIG",
)
async def list_specialized_agents(
    admin_check: bool = Depends(check_admin_permission),
):
    """List all AutoBot specialized agents from .claude/agents/ (#1794).

    Returns agent definitions parsed from markdown files including
    name, description, tools, color, model, and category.

    Issue #744: Requires admin authentication.
    """
    from services.specialized_agent_service import SpecializedAgentService

    service = SpecializedAgentService()
    agents = service.list_agents()
    categories = service.get_categories_summary(agents)

    return JSONResponse(
        status_code=200,
        content={
            "agents": agents,
            "total_count": len(agents),
            "categories": categories,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        },
    )


@router.get(
    "/agents/specialized/{agent_id}",
    response_model=DataResponse[AgentConfigSpecializedDetailResponse],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_specialized_agent",
    error_code_prefix="AGENT_CONFIG",
)
async def get_specialized_agent(
    agent_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """Get a single AutoBot specialized agent by ID (#1794).

    Returns full agent definition including the system prompt.

    Issue #744: Requires admin authentication.
    """
    from services.specialized_agent_service import SpecializedAgentService

    service = SpecializedAgentService()
    agent = service.get_agent(agent_id)

    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"Specialized agent '{agent_id}' not found",
        )

    return JSONResponse(status_code=200, content=agent)


@router.get("/agents/usage", response_model=DataResponse[AgentConfigUsageResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agents_usage",
    error_code_prefix="AGENT_CONFIG",
)
async def get_agents_usage(
    agent_id: str | None = Query(None, description="Filter to a specific agent (all agents if omitted)"),
    days: int = Query(default=7, ge=1, le=90, description="Lookback window in days for trend data"),
    outcome: str | None = Query(None, description="Filter by outcome: completed, failed, timeout, cancelled"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Agent usage summary: invocation counts, success rates, and average latency.

    Returns per-agent aggregated metrics and daily trend data queryable by
    agent name, time range, and outcome.  Data is persisted by the
    AgentAnalytics service (Redis db=ANALYTICS) and populated automatically
    whenever an agent is invoked via BaseAgent.execute_with_tracking or the
    track_agent_usage() context manager.

    Issue #3289: Requires admin authentication.
    """
    from services.agent_analytics import TaskStatus, get_agent_analytics

    analytics = get_agent_analytics()

    if agent_id:
        metrics = await analytics.get_agent_metrics(agent_id)
        metrics_list = [metrics] if metrics else []
        history = await analytics.get_agent_history(agent_id, limit=500)
    else:
        metrics_list = await analytics.get_all_agents_metrics()
        history = await analytics.get_recent_tasks(limit=2000)

    # Filter history by outcome when requested
    if outcome:
        try:
            outcome_value = TaskStatus(outcome).value
        except ValueError:
            outcome_value = outcome
        history = [t for t in history if t.get("status") == outcome_value]

    # Build per-agent aggregated summary
    agents_summary = [m.to_dict() for m in metrics_list]

    # Daily trend buckets for the requested window
    from datetime import timedelta

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    window_tasks = []
    for task in history:
        try:
            started = parse_utc_iso(task["started_at"])
            if started >= cutoff:
                window_tasks.append(task)
        except (KeyError, ValueError):
            continue

    daily: dict = {}
    for task in window_tasks:
        day = task["started_at"][:10]
        bucket = daily.setdefault(day, {"total": 0, "completed": 0, "failed": 0, "total_duration_ms": 0.0})
        bucket["total"] += 1
        if task.get("status") == TaskStatus.COMPLETED.value:
            bucket["completed"] += 1
        elif task.get("status") == TaskStatus.FAILED.value:
            bucket["failed"] += 1
        if task.get("duration_ms"):
            bucket["total_duration_ms"] += task["duration_ms"]

    # Add derived rates to each day bucket
    for stats in daily.values():
        if stats["total"] > 0:
            stats["success_rate"] = round((stats["completed"] / stats["total"]) * 100, 2)
            stats["calls_per_day"] = stats["total"]
            stats["avg_latency_ms"] = round(stats["total_duration_ms"] / stats["total"], 2)
        else:
            stats["success_rate"] = 0.0
            stats["calls_per_day"] = 0
            stats["avg_latency_ms"] = 0.0

    total_calls = sum(b["total"] for b in daily.values())
    total_completed = sum(b["completed"] for b in daily.values())

    return JSONResponse(
        status_code=200,
        content={
            "agents": agents_summary,
            "daily_trends": daily,
            "summary": {
                "agent_id": agent_id,
                "period_days": days,
                "outcome_filter": outcome,
                "total_calls": total_calls,
                "total_agents": len(agents_summary),
                "overall_success_rate": round((total_completed / total_calls * 100) if total_calls else 0.0, 2),
            },
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        },
    )


@router.get("/agents/{agent_id}", response_model=AgentConfigDetailResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_config",
    error_code_prefix="AGENT_CONFIG",
)
async def get_agent_config(agent_id: str, admin_check: bool = Depends(check_admin_permission)):
    """
    Get detailed configuration for a specific agent

    Issue #744: Requires admin authentication.
    """
    if agent_id not in DEFAULT_AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    from config import unified_config_manager

    base_config = DEFAULT_AGENT_CONFIGS[agent_id]

    # Try SLM first, fallback to local config
    slm_config = await _get_agent_config_from_slm(agent_id)

    if slm_config:
        current_model = slm_config.get("model", base_config["default_model"])
        current_provider = slm_config.get("provider", base_config["provider"])
        enabled = slm_config.get("enabled", True)
        config_source = "slm"
    else:
        current_model = unified_config_manager.get_nested(f"agents.{agent_id}.model", base_config["default_model"])
        current_provider = unified_config_manager.get_nested(f"agents.{agent_id}.provider", base_config["provider"])
        enabled = unified_config_manager.get_nested(f"agents.{agent_id}.enabled", base_config["enabled"])
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
            "available_providers": await _get_available_providers(),
            "configurable_settings": ["model", "provider", "enabled", "priority"],
        },
        "health_check": {
            "last_check": datetime.now(tz=timezone.utc).isoformat(),
            "response_time": 0.0,
            "status": "healthy" if enabled else "disabled",
        },
    }

    return JSONResponse(status_code=200, content=agent_config)


async def _apply_agent_model_update(
    agent_id: str,
    update: "AgentModelUpdate",
    unified_config_manager,
    session: "AsyncSession",
) -> dict:
    """Persist model/provider change and record audit revision. Ref: #2735.

    Returns the ``updated_config`` dict ready for the API response.
    """
    base = DEFAULT_AGENT_CONFIGS[agent_id]
    before_config = {
        "model": unified_config_manager.get_nested(f"agents.{agent_id}.model", base["default_model"]),
        "provider": unified_config_manager.get_nested(f"agents.{agent_id}.provider", base["provider"]),
    }

    # Persist changes
    unified_config_manager.set_nested(f"agents.{agent_id}.model", update.model)
    if update.provider:
        unified_config_manager.set_nested(f"agents.{agent_id}.provider", update.provider)
    unified_config_manager.save_settings()
    ConfigService.clear_cache()

    # Issue #1747: Record audit revision
    after_config = {"model": update.model, "provider": update.provider}
    await ConfigRevisionService(session).create_revision(
        entity_type="agent",
        entity_id=agent_id,
        before_config=before_config,
        after_config=after_config,
        source="api",
        created_by="admin",
    )

    logger.info(
        "Updated agent %s model to %s (provider: %s)",
        agent_id,
        update.model,
        update.provider,
    )

    return {
        "agent_id": agent_id,
        "agent_name": DEFAULT_AGENT_CONFIGS[agent_id]["name"],
        "model": update.model,
        "provider": update.provider,
        "status": "updated",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/agents/{agent_id}/model", response_model=AgentConfigUpdateModelResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_agent_model",
    error_code_prefix="AGENT_CONFIG",
)
async def update_agent_model(
    agent_id: str,
    update: AgentModelUpdate,
    admin_check: bool = Depends(check_admin_permission),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Update the LLM model for a specific agent

    Issue #744: Requires admin authentication.
    Issue #1747: Records config revision for audit trail.
    """
    if agent_id not in DEFAULT_AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    from config import unified_config_manager

    if update.agent_id != agent_id:
        raise HTTPException(
            status_code=400,
            detail="Agent ID in URL must match agent ID in request body",
        )

    updated_config = await _apply_agent_model_update(agent_id, update, unified_config_manager, session)

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": f"Agent {agent_id} model updated successfully",
            "updated_config": updated_config,
        },
    )


@router.post("/agents/{agent_id}/enable", response_model=AgentConfigEnableDisableResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enable_agent",
    error_code_prefix="AGENT_CONFIG",
)
async def enable_agent(
    agent_id: str,
    admin_check: bool = Depends(check_admin_permission),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Enable a specific agent

    Issue #744: Requires admin authentication.
    Issue #1747: Records config revision for audit trail.
    """
    if agent_id not in DEFAULT_AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    from config import unified_config_manager

    before_enabled = unified_config_manager.get_nested(f"agents.{agent_id}.enabled", True)
    unified_config_manager.set_nested(f"agents.{agent_id}.enabled", True)
    unified_config_manager.save_settings()
    ConfigService.clear_cache()

    # Issue #1747: Record audit revision
    await ConfigRevisionService(session).create_revision(
        entity_type="agent",
        entity_id=agent_id,
        before_config={"enabled": before_enabled},
        after_config={"enabled": True},
        source="api",
        created_by="admin",
    )

    logger.info("Enabled agent %s", agent_id)

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": f"Agent {agent_id} enabled successfully",
            "agent_name": DEFAULT_AGENT_CONFIGS[agent_id]["name"],
        },
    )


@router.post("/agents/{agent_id}/disable", response_model=AgentConfigEnableDisableResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="disable_agent",
    error_code_prefix="AGENT_CONFIG",
)
async def disable_agent(
    agent_id: str,
    admin_check: bool = Depends(check_admin_permission),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Disable a specific agent

    Issue #744: Requires admin authentication.
    Issue #1747: Records config revision for audit trail.
    """
    if agent_id not in DEFAULT_AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    from config import unified_config_manager

    before_enabled = unified_config_manager.get_nested(f"agents.{agent_id}.enabled", True)
    unified_config_manager.set_nested(f"agents.{agent_id}.enabled", False)
    unified_config_manager.save_settings()
    ConfigService.clear_cache()

    # Issue #1747: Record audit revision
    await ConfigRevisionService(session).create_revision(
        entity_type="agent",
        entity_id=agent_id,
        before_config={"enabled": before_enabled},
        after_config={"enabled": False},
        source="api",
        created_by="admin",
    )

    logger.info("Disabled agent %s", agent_id)

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": f"Agent {agent_id} disabled successfully",
            "agent_name": DEFAULT_AGENT_CONFIGS[agent_id]["name"],
        },
    )


async def _check_provider_availability(agent_id: str) -> tuple:
    """Helper for check_agent_health. Ref: #1088.

    Checks whether the provider configured for the given agent is reachable
    via ProviderHealthManager.

    Returns:
        Tuple of (provider_available: bool, response_time: float)
    """
    provider_available = False
    start_time = datetime.now(tz=timezone.utc)

    try:
        from services.provider_health import ProviderHealthManager

        provider_config = DEFAULT_AGENT_CONFIGS[agent_id].get("provider", "ollama")
        health_result = await ProviderHealthManager.check_provider_health(
            provider=provider_config,
            timeout=3.0,
            use_cache=True,
        )
        provider_available = health_result.available
        if not provider_available:
            logger.warning(f"Provider {provider_config} unavailable for agent {agent_id}: " f"{health_result.message}")
    except Exception as e:
        logger.warning(f"Provider availability check failed for agent {agent_id}: {str(e)}")
        provider_available = False

    response_time = (datetime.now(tz=timezone.utc) - start_time).total_seconds()
    return provider_available, response_time


@router.get("/agents/{agent_id}/health", response_model=AgentConfigHealthResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_agent_health",
    error_code_prefix="AGENT_CONFIG",
)
async def check_agent_health(agent_id: str, admin_check: bool = Depends(check_admin_permission)):
    """
    Perform health check on a specific agent

    Issue #744: Requires admin authentication.
    """
    if agent_id not in DEFAULT_AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    from config import unified_config_manager

    enabled = unified_config_manager.get_nested(f"agents.{agent_id}.enabled", True)
    model = unified_config_manager.get_nested(
        f"agents.{agent_id}.model", DEFAULT_AGENT_CONFIGS[agent_id]["default_model"]
    )

    provider_available, response_time = await _check_provider_availability(agent_id)

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
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "response_time": response_time,
    }

    return JSONResponse(status_code=200, content=health_status)


@router.get("/status/overview", response_model=AgentConfigOverviewResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agents_overview",
    error_code_prefix="AGENT_CONFIG",
)
async def get_agents_overview(admin_check: bool = Depends(check_admin_permission)):
    """
    Get overview of all agents' status for dashboard

    Issue #744: Requires admin authentication.
    """
    from config import unified_config_manager

    total_agents = len(DEFAULT_AGENT_CONFIGS)
    enabled_agents = 0
    healthy_agents = 0

    agent_summary = []

    for agent_id, agent_cfg in DEFAULT_AGENT_CONFIGS.items():
        enabled = unified_config_manager.get_nested(f"agents.{agent_id}.enabled", agent_cfg["enabled"])
        model = unified_config_manager.get_nested(f"agents.{agent_id}.model", agent_cfg["default_model"])

        if enabled:
            enabled_agents += 1
            if model:
                healthy_agents += 1

        agent_summary.append(
            {
                "id": agent_id,
                "name": agent_cfg["name"],
                "enabled": enabled,
                "status": "healthy" if enabled and model else "unhealthy",
                "priority": agent_cfg["priority"],
            }
        )

    overview = {
        "total_agents": total_agents,
        "enabled_agents": enabled_agents,
        "healthy_agents": healthy_agents,
        "unhealthy_agents": enabled_agents - healthy_agents,
        "disabled_agents": total_agents - enabled_agents,
        "overall_health": ("good" if healthy_agents >= enabled_agents * 0.8 else "warning"),
        "agents": agent_summary,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }

    return JSONResponse(status_code=200, content=overview)
