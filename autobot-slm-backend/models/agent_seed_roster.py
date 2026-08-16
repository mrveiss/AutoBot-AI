# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The canonical SLM agent roster (#14321).

Extracted from ``services/agent_seeder.py`` so it can be read without importing
the service layer.

``services/__init__.py`` eagerly imports ``.auth``, ``.database``,
``.deployment`` and ``.reconciler``, so ``from services.agent_seeder import
SEED_AGENT_CONFIGS`` pulls the whole web stack — including FastAPI — behind it.
The migration runner has no FastAPI (nor should it: a schema migration must not
depend on the HTTP layer), so importing the roster through the service package
failed the SLM migration gate with ``No module named 'fastapi'``.

This module holds data and nothing else: no imports, no side effects, importable
from a migration and from the running service alike. ``agent_seeder`` re-exports
it, so the roster stays a single definition rather than being duplicated into
the migration — the duplication #14321 explicitly set out to avoid.
"""

from __future__ import annotations

from autobot_shared.ssot_config import (
    CLASSIFICATION_MODEL,
    INSTRUCTION_MODEL,
    LIGHT_PROCESSING_MODEL,
    QUALITY_MODEL,
    ROUTING_MODEL,
    SYSTEM_MODEL,
)

# 6-tier model mapping from SSOT constants (#2553). These moved here with the
# roster: they are referenced by the entries below and by nothing else, so
# leaving them in `services/agent_seeder.py` would have meant the roster could
# not be read without importing the service package — the exact FastAPI drag
# this extraction removes.
#
# `autobot_shared.ssot_config` is safe from a migration: it pulls pydantic, not
# the HTTP layer, and the SLM migration gate already installs pydantic for it.
_ROUTING = ROUTING_MODEL
_CLASSIFICATION = CLASSIFICATION_MODEL
_LIGHT = LIGHT_PROCESSING_MODEL
_INSTRUCTION = INSTRUCTION_MODEL
_SYSTEM = SYSTEM_MODEL
_QUALITY = QUALITY_MODEL

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
        "llm_model": _ROUTING,
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
        "llm_model": _QUALITY,
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
        "llm_model": _CLASSIFICATION,
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
        "llm_model": _LIGHT,
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
        "llm_model": _INSTRUCTION,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "research",
        "name": "Research Agent",
        "description": (
            "Conducts web research using browser automation. Invoked by AgentRouter " "when research patterns detected."
        ),
        "llm_model": _QUALITY,
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
        "llm_model": _LIGHT,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "knowledge_retrieval",
        "name": "Knowledge Retrieval Agent",
        "description": (
            "Fast semantic search using vector embeddings. Invoked by AgentRouter " "for knowledge queries."
        ),
        "llm_model": _LIGHT,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "code_analysis",
        "name": "Code Analysis Agent",
        "description": (
            "Performs static code analysis, code review, and bug detection. " "Uses AST parsing and pattern matching."
        ),
        "llm_model": _QUALITY,
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
        "llm_model": _SYSTEM,
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
        "llm_model": _SYSTEM,
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
        "llm_model": _SYSTEM,
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
        "llm_model": _INSTRUCTION,
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
        "llm_model": _SYSTEM,
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
        "llm_model": _QUALITY,
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
        "llm_model": _QUALITY,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "development_speedup",
        "name": "Development Speedup Agent",
        "description": (
            "Accelerates development by finding code duplicates, patterns, and " "optimization opportunities."
        ),
        "llm_model": _QUALITY,
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
        "llm_model": _LIGHT,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "graph_entity_extractor",
        "name": "Graph Entity Extractor",
        "description": (
            "Automatically extracts entities and relationships from conversations " "to populate AutoBot Memory Graph."
        ),
        "llm_model": _INSTRUCTION,
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
        "llm_model": _QUALITY,
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
        "llm_model": _INSTRUCTION,
        "is_default": False,
        "is_active": True,
    },
    # Tier 4: Advanced Agents
    {
        "agent_id": "npu_code_search",
        "name": "NPU Code Search Agent",
        "description": (
            "High-performance semantic code search using NPU acceleration (OpenVINO) " "with Redis indexing."
        ),
        "llm_model": _LIGHT,
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
        "llm_model": _INSTRUCTION,
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
        "llm_model": _QUALITY,
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
        "llm_model": _QUALITY,
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
        "llm_model": _QUALITY,
        "is_default": False,
        "is_active": True,
    },
    {
        "agent_id": "man_page_knowledge_integrator",
        "name": "Man Page Knowledge Integrator",
        "description": ("Scrapes, parses, and integrates Linux man pages into machine-aware " "knowledge system."),
        "llm_model": _INSTRUCTION,
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
        "llm_model": _SYSTEM,
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
        "llm_model": _CLASSIFICATION,
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
        "llm_model": _QUALITY,
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
        "llm_model": _QUALITY,
        "is_default": False,
        "is_active": True,
    },
]
