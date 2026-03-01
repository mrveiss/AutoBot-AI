# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Seeder Service (Issue #939)

Seeds the agents table on first startup with all 29 AutoBot agents.
Mirrors DEFAULT_AGENT_CONFIGS from autobot-backend/api/agent_config.py
without requiring a cross-codebase import.

Called by main.py lifespan via _seed_default_agents().
"""
import logging

from models.database import Agent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Default Ollama endpoint used for all seeded agents
_DEFAULT_OLLAMA_ENDPOINT = "http://127.0.0.1:11434"

# Mirrors TIER_*_MODEL defaults from autobot-backend/api/agent_config.py
_TIER1 = "llama3.2:1b"
_TIER2 = "llama3.2:3b"
_TIER3 = "mistral:7b-instruct"
_TIER4 = "mistral:7b-instruct"

# Gemma model for classification agents (SSOT: agents.yaml llm.models.classification)
_GEMMA_MODEL = "gemma2:2b"

# All 29 AutoBot agents — mirrors DEFAULT_AGENT_CONFIGS exactly.
# model/provider/endpoint can be overridden via /agent-config in the SLM UI.
SEED_AGENT_CONFIGS: list[dict] = [
    # Tier 1: Core Agents
    {
        "agent_id": "orchestrator",
        "name": "Orchestrator Agent",
        "description": (
            "Central coordinator that routes requests to appropriate agents. "
            "Invoked automatically by AsyncChatWorkflow on every user message. "
            "Uses pattern matching and LLM-based routing (AgentRouter) to select agents."
        ),
        "llm_model": _TIER1,
        "is_default": True,
        "is_active": True,
    },
    {
        "agent_id": "chat",
        "name": "Chat Agent",
        "description": (
            "Handles conversational interactions, greetings, and simple Q&A. "
            "Invoked by AgentRouter when greeting patterns detected."
        ),
        "llm_model": _TIER1,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "classification",
        "name": "Classification Agent",
        "description": (
            "Classifies incoming requests by type and complexity. "
            "Invoked by Orchestrator to determine routing strategy."
        ),
        "llm_model": _GEMMA_MODEL,
        "is_default": False,
        "is_active": True,
    },
    # Tier 2: Processing Agents
    {
        "agent_id": "kb_librarian",
        "name": "Knowledge Base Librarian",
        "description": (
            "Manages knowledge base operations including document ingestion, search, "
            "and retrieval. Invoked by AsyncChatWorkflow when knowledge patterns detected."
        ),
        "llm_model": _TIER2,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "rag",
        "name": "RAG Agent",
        "description": (
            "Performs Retrieval-Augmented Generation by combining vector search with "
            "LLM synthesis. Uses ChromaDB for vector operations."
        ),
        "llm_model": _TIER2,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "research",
        "name": "Research Agent",
        "description": (
            "Conducts web research using browser automation. Invoked by AgentRouter "
            "when research patterns detected."
        ),
        "llm_model": _TIER2,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "knowledge_extraction",
        "name": "Knowledge Extraction Agent",
        "description": (
            "Extracts structured entities and relationships from unstructured text. "
            "Invoked by kb_librarian during document ingestion."
        ),
        "llm_model": _TIER2,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "knowledge_retrieval",
        "name": "Knowledge Retrieval Agent",
        "description": (
            "Fast semantic search using vector embeddings. Invoked by AgentRouter "
            "for knowledge queries."
        ),
        "llm_model": _TIER2,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "code_analysis",
        "name": "Code Analysis Agent",
        "description": (
            "Performs static code analysis, code review, and bug detection. "
            "Uses AST parsing and pattern matching."
        ),
        "llm_model": _TIER2,
        "is_default": False,
        "is_active": True,
    },
    # Tier 3: Specialized Agents
    {
        "agent_id": "system_commands",
        "name": "System Commands Agent",
        "description": (
            "Executes system commands with full terminal streaming and security validation. "
            "Invoked via SYSTEM_COMMAND_PATTERNS."
        ),
        "llm_model": _TIER3,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "enhanced_system_commands",
        "name": "Enhanced System Commands Agent",
        "description": (
            "Advanced system command generation with security-focused validation. "
            "Used when higher security assurance needed."
        ),
        "llm_model": _TIER3,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "security_scanner",
        "name": "Security Scanner Agent",
        "description": (
            "Performs defensive security scans including port scanning, service detection, "
            "SSL analysis, and DNS enumeration."
        ),
        "llm_model": _TIER3,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "network_discovery",
        "name": "Network Discovery Agent",
        "description": (
            "Discovers network assets and creates topology maps. Supports network scanning, "
            "host discovery, ARP scanning, and traceroute."
        ),
        "llm_model": _TIER3,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "interactive_terminal",
        "name": "Interactive Terminal Agent",
        "description": (
            "Manages full PTY terminal sessions with sudo handling and user takeover "
            "capability. Used for persistent shell sessions."
        ),
        "llm_model": _TIER3,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "web_research_assistant",
        "name": "Web Research Assistant",
        "description": (
            "Performs web research and integrates findings into knowledge base. "
            "Uses AdvancedWebResearcher for Playwright-based scraping."
        ),
        "llm_model": _TIER3,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "advanced_web_research",
        "name": "Advanced Web Research Agent",
        "description": (
            "Tier 2 web research with Playwright browser automation, anti-detection "
            "measures, and CAPTCHA handling via human-in-loop."
        ),
        "llm_model": _TIER3,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "development_speedup",
        "name": "Development Speedup Agent",
        "description": (
            "Accelerates development by finding code duplicates, patterns, and "
            "optimization opportunities."
        ),
        "llm_model": _TIER3,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "json_formatter",
        "name": "JSON Formatter Agent",
        "description": (
            "Parses, validates, and formats JSON responses from other LLMs. "
            "Provides robust JSON handling with fallback mechanisms."
        ),
        "llm_model": _TIER3,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "graph_entity_extractor",
        "name": "Graph Entity Extractor",
        "description": (
            "Automatically extracts entities and relationships from conversations "
            "to populate AutoBot Memory Graph."
        ),
        "llm_model": _TIER3,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "overseer",
        "name": "Overseer Agent",
        "description": (
            "Decomposes user queries into sequential executable tasks. "
            "Orchestrates step-by-step execution via StepExecutorAgent workers."
        ),
        "llm_model": _TIER3,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "step_executor",
        "name": "Step Executor Agent",
        "description": (
            "Executes individual tasks/steps from OverseerAgent plans. "
            "Handles command validation and PTY terminal execution with streaming output."
        ),
        "llm_model": _TIER3,
        "is_default": False,
        "is_active": True,
    },
    # Tier 4: Advanced Agents
    {
        "agent_id": "npu_code_search",
        "name": "NPU Code Search Agent",
        "description": (
            "High-performance semantic code search using NPU acceleration (OpenVINO) "
            "with Redis indexing."
        ),
        "llm_model": _TIER4,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "librarian_assistant",
        "name": "Librarian Assistant Agent",
        "description": (
            "Performs web research using Playwright and manages knowledge. "
            "Stores quality content in knowledge base for future reference."
        ),
        "llm_model": _TIER4,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "containerized_librarian",
        "name": "Containerized Librarian Agent",
        "description": (
            "Performs web research using containerized Playwright service. "
            "Provides isolated execution environment for secure document processing."
        ),
        "llm_model": _TIER4,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "system_knowledge_manager",
        "name": "System Knowledge Manager",
        "description": (
            "Manages immutable system knowledge templates and runtime copies. "
            "Handles intelligent change detection and backup creation."
        ),
        "llm_model": _TIER4,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "machine_aware_knowledge_manager",
        "name": "Machine-Aware Knowledge Manager",
        "description": (
            "Extends SystemKnowledgeManager with machine-specific adaptation. "
            "Detects OS type, distro, available tools, and hardware capabilities."
        ),
        "llm_model": _TIER4,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "man_page_knowledge_integrator",
        "name": "Man Page Knowledge Integrator",
        "description": (
            "Scrapes, parses, and integrates Linux man pages into machine-aware "
            "knowledge system."
        ),
        "llm_model": _TIER4,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "llm_failsafe",
        "name": "LLM Failsafe Agent",
        "description": (
            "Multi-tier failsafe system ensuring LLM communication even when primary "
            "systems fail. Implements PRIMARY → SECONDARY → BASIC → EMERGENCY fallback."
        ),
        "llm_model": _TIER4,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "gemma_classification",
        "name": "Gemma Classification Agent",
        "description": (
            "Ultra-fast classification using Google's Gemma models. "
            "Used by Orchestrator for advanced intent detection and multi-label tagging."
        ),
        "llm_model": _GEMMA_MODEL,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "standardized",
        "name": "Standardized Agent",
        "description": (
            "Base agent class providing automatic action routing, standardized error "
            "handling, and consistent response formatting. Parent class for 24+ agents."
        ),
        "llm_model": _TIER4,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "web_research_integration",
        "name": "Web Research Integration Agent",
        "description": (
            "Unified interface for web research integrating multiple research agents. "
            "Provides circuit breakers and rate limiting."
        ),
        "llm_model": _TIER4,
        "is_default": False,
        "is_active": True,
    },
]


async def seed_default_agents(db: AsyncSession) -> int:
    """Seed agents table with all AutoBot agents if not already present.

    Idempotent: skips agents that already exist by agent_id.

    Args:
        db: Active SQLAlchemy async session.

    Returns:
        Number of agents created.
    """
    created = 0
    for cfg in SEED_AGENT_CONFIGS:
        result = await db.execute(
            select(Agent).where(Agent.agent_id == cfg["agent_id"])
        )
        if result.scalar_one_or_none() is not None:
            continue

        agent = Agent(
            agent_id=cfg["agent_id"],
            name=cfg["name"],
            description=cfg["description"],
            llm_provider="ollama",
            llm_endpoint=_DEFAULT_OLLAMA_ENDPOINT,
            llm_model=cfg["llm_model"],
            llm_timeout=30,
            llm_temperature=0.7,
            llm_max_tokens=None,
            is_default=cfg["is_default"],
            is_active=cfg["is_active"],
        )
        db.add(agent)
        created += 1
        logger.debug("Seeding agent: %s (%s)", cfg["agent_id"], cfg["name"])

    if created:
        await db.commit()

    return created
