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
from backend.utils.connection_utils import ModelManager
from src.constants.model_constants import ModelConstants
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# Get default LLM model from environment - uses centralized model constants
DEFAULT_LLM_MODEL = os.getenv(
    "AUTOBOT_DEFAULT_LLM_MODEL",
    os.getenv("AUTOBOT_DEFAULT_AGENT_MODEL", ModelConstants.DEFAULT_OLLAMA_MODEL),
)

router = APIRouter()


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
            return [m.get("name", m) if isinstance(m, dict) else m for m in result["models"]]
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
# Based on src/agents/ implementations - 31 specialized agents
DEFAULT_AGENT_CONFIGS = {
    # Tier 1: Core Agents (always available, priority 1)
    "orchestrator": {
        "name": "Orchestrator Agent",
        "description": "Main workflow coordination and task classification",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 1,
        "tasks": ["workflow_planning", "task_classification", "agent_coordination"],
    },
    "chat": {
        "name": "Chat Agent",
        "description": "Conversational responses and user interaction",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 1,
        "tasks": ["conversation", "user_assistance", "general_queries"],
    },
    "classification": {
        "name": "Classification Agent",
        "description": "Request classification and routing decisions",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 1,
        "tasks": ["request_classification", "complexity_assessment", "routing"],
    },
    # Tier 2: Processing Agents (on-demand, priority 2)
    "kb_librarian": {
        "name": "Knowledge Base Librarian",
        "description": "Knowledge base search and document retrieval",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["knowledge_search", "document_analysis", "information_retrieval"],
    },
    "rag": {
        "name": "RAG Agent",
        "description": "Retrieval-Augmented Generation for knowledge queries",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["rag_queries", "context_retrieval", "knowledge_synthesis"],
    },
    "research": {
        "name": "Research Agent",
        "description": "Web research and information gathering",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["web_research", "fact_checking", "data_gathering"],
    },
    "knowledge_extraction": {
        "name": "Knowledge Extraction Agent",
        "description": "Extract structured knowledge from documents",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["entity_extraction", "relation_extraction", "knowledge_structuring"],
    },
    "knowledge_retrieval": {
        "name": "Knowledge Retrieval Agent",
        "description": "Semantic search and knowledge retrieval",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["semantic_search", "similarity_matching", "context_retrieval"],
    },
    "code_analysis": {
        "name": "Code Analysis Agent",
        "description": "Code review and analysis tasks",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["code_review", "static_analysis", "bug_detection"],
    },
    # Tier 3: Specialized Agents (task-specific, priority 3)
    "system_commands": {
        "name": "System Commands Agent",
        "description": "Command execution and system operations",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["command_execution", "system_operations", "tool_usage"],
    },
    "enhanced_system_commands": {
        "name": "Enhanced System Commands Agent",
        "description": "Advanced system operations with safety checks",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["safe_command_execution", "privilege_management", "audit_logging"],
    },
    "security_scanner": {
        "name": "Security Scanner Agent",
        "description": "Security analysis and vulnerability assessment",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["security_analysis", "vulnerability_scanning", "threat_assessment"],
    },
    "network_discovery": {
        "name": "Network Discovery Agent",
        "description": "Network scanning and topology mapping",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["network_scanning", "service_discovery", "topology_mapping"],
    },
    "interactive_terminal": {
        "name": "Interactive Terminal Agent",
        "description": "Interactive terminal session management",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["terminal_sessions", "interactive_commands", "shell_management"],
    },
    "web_research_assistant": {
        "name": "Web Research Assistant",
        "description": "Advanced web research with source validation",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["deep_research", "source_validation", "citation_management"],
    },
    "advanced_web_research": {
        "name": "Advanced Web Research Agent",
        "description": "Multi-source web research with synthesis",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["multi_source_research", "content_synthesis", "trend_analysis"],
    },
    "development_speedup": {
        "name": "Development Speedup Agent",
        "description": "Accelerate development workflows",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["code_generation", "boilerplate_creation", "workflow_automation"],
    },
    "json_formatter": {
        "name": "JSON Formatter Agent",
        "description": "JSON formatting and validation",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["json_formatting", "schema_validation", "data_transformation"],
    },
    "graph_entity_extractor": {
        "name": "Graph Entity Extractor",
        "description": "Extract entities and relationships for knowledge graphs",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["entity_extraction", "relationship_mapping", "graph_construction"],
    },
    # Tier 4: Advanced Agents (multi-modal, priority 4)
    "npu_code_search": {
        "name": "NPU Code Search Agent",
        "description": "Hardware-accelerated code search using NPU",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["semantic_code_search", "npu_acceleration", "large_codebase_analysis"],
    },
    "librarian_assistant": {
        "name": "Librarian Assistant Agent",
        "description": "Document organization and library management",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["document_organization", "metadata_management", "library_curation"],
    },
    "containerized_librarian": {
        "name": "Containerized Librarian Agent",
        "description": "Isolated document processing in containers",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["isolated_processing", "secure_document_handling", "container_orchestration"],
    },
    "system_knowledge_manager": {
        "name": "System Knowledge Manager",
        "description": "System-wide knowledge integration",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["knowledge_integration", "system_documentation", "context_management"],
    },
    "machine_aware_knowledge_manager": {
        "name": "Machine-Aware Knowledge Manager",
        "description": "Hardware-aware knowledge processing",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["hardware_optimization", "resource_aware_processing", "adaptive_caching"],
    },
    "man_page_knowledge_integrator": {
        "name": "Man Page Knowledge Integrator",
        "description": "Unix/Linux man page knowledge extraction",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["man_page_parsing", "command_documentation", "unix_knowledge"],
    },
    "llm_failsafe": {
        "name": "LLM Failsafe Agent",
        "description": "Fallback handling for LLM failures",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["failover_handling", "graceful_degradation", "error_recovery"],
    },
    "gemma_classification": {
        "name": "Gemma Classification Agent",
        "description": "Specialized classification using Gemma models",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["advanced_classification", "multi_label_tagging", "intent_detection"],
    },
    "standardized": {
        "name": "Standardized Agent",
        "description": "Base standardized agent implementation",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["standard_processing", "template_execution", "protocol_compliance"],
    },
    "web_research_integration": {
        "name": "Web Research Integration Agent",
        "description": "Integrate web research with knowledge base",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 4,
        "tasks": ["research_integration", "knowledge_enrichment", "source_linking"],
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
    from src.unified_config_manager import unified_config_manager

    llm_config = unified_config_manager.get_llm_config()
    provider_type = llm_config.get("provider_type", "local")

    agents = []
    for agent_id, config in DEFAULT_AGENT_CONFIGS.items():
        # Get current model from config or use default
        current_model = unified_config_manager.get_nested(
            f"agents.{agent_id}.model", config["default_model"]
        )
        current_provider = unified_config_manager.get_nested(
            f"agents.{agent_id}.provider", config["provider"]
        )
        enabled = unified_config_manager.get_nested(
            f"agents.{agent_id}.enabled", config["enabled"]
        )

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
    from src.unified_config_manager import unified_config_manager

    backend_agents = []
    for agent_id, config in DEFAULT_AGENT_CONFIGS.items():
        current_model = unified_config_manager.get_nested(
            f"agents.{agent_id}.model", config["default_model"]
        )
        enabled = unified_config_manager.get_nested(
            f"agents.{agent_id}.enabled", config["enabled"]
        )

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

    from src.unified_config_manager import unified_config_manager

    base_config = DEFAULT_AGENT_CONFIGS[agent_id]

    # Get current configuration
    current_model = unified_config_manager.get_nested(
        f"agents.{agent_id}.model", base_config["default_model"]
    )
    current_provider = unified_config_manager.get_nested(
        f"agents.{agent_id}.provider", base_config["provider"]
    )
    enabled = unified_config_manager.get_nested(
        f"agents.{agent_id}.enabled", base_config["enabled"]
    )

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
        "default_model": base_config["default_model"],
        "status": "connected" if enabled and current_model else "disconnected",
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

    from src.unified_config_manager import unified_config_manager

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

    from src.unified_config_manager import unified_config_manager

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

    from src.unified_config_manager import unified_config_manager

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

    from src.unified_config_manager import unified_config_manager

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
    from src.unified_config_manager import unified_config_manager

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
