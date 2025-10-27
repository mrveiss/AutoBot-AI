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
from backend.utils.connection_utils import ConnectionTester
from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)

# Get default LLM model from environment (NO HARDCODING)
DEFAULT_LLM_MODEL = os.getenv("AUTOBOT_DEFAULT_LLM_MODEL", os.getenv("AUTOBOT_DEFAULT_AGENT_MODEL", "llama3.2:1b"))

router = APIRouter()


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
DEFAULT_AGENT_CONFIGS = {
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
    "kb_librarian": {
        "name": "Knowledge Base Librarian",
        "description": "Knowledge base search and document retrieval",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["knowledge_search", "document_analysis", "information_retrieval"],
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
    "system_commands": {
        "name": "System Commands Agent",
        "description": "Command execution and system operations",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["command_execution", "system_operations", "tool_usage"],
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
    "code_analysis": {
        "name": "Code Analysis Agent",
        "description": "Code review and analysis tasks",
        "default_model": DEFAULT_LLM_MODEL,
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["code_review", "static_analysis", "bug_detection"],
    },
}


@router.get("/agents")
async def list_agents():
    """Get list of all available agents with their configurations"""
    try:
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
                "last_used": "N/A",  # TODO: Track actual usage
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

    except Exception as e:
        logger.error(f"Failed to list agents: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list agents: {str(e)}")


@router.get("/agents/{agent_id}")
async def get_agent_config(agent_id: str):
    """Get detailed configuration for a specific agent"""
    try:
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
                "available_models": [],  # TODO: Get from model manager
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent config for {agent_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get agent config: {str(e)}"
        )


@router.post("/agents/{agent_id}/model")
async def update_agent_model(agent_id: str, update: AgentModelUpdate):
    """Update the LLM model for a specific agent"""
    try:
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent {agent_id} model: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to update agent model: {str(e)}"
        )


@router.post("/agents/{agent_id}/enable")
async def enable_agent(agent_id: str):
    """Enable a specific agent"""
    try:
        if agent_id not in DEFAULT_AGENT_CONFIGS:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

        from src.unified_config_manager import unified_config_manager

        unified_config_manager.set_nested(f"agents.{agent_id}.enabled", True)
        unified_config_manager.save_settings()
        ConfigService.clear_cache()

        logger.info(f"Enabled agent {agent_id}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": f"Agent {agent_id} enabled successfully",
                "agent_name": DEFAULT_AGENT_CONFIGS[agent_id]["name"],
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enable agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to enable agent: {str(e)}")


@router.post("/agents/{agent_id}/disable")
async def disable_agent(agent_id: str):
    """Disable a specific agent"""
    try:
        if agent_id not in DEFAULT_AGENT_CONFIGS:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

        from src.unified_config_manager import unified_config_manager

        unified_config_manager.set_nested(f"agents.{agent_id}.enabled", False)
        unified_config_manager.save_settings()
        ConfigService.clear_cache()

        logger.info(f"Disabled agent {agent_id}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": f"Agent {agent_id} disabled successfully",
                "agent_name": DEFAULT_AGENT_CONFIGS[agent_id]["name"],
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disable agent {agent_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to disable agent: {str(e)}"
        )


@router.get("/agents/{agent_id}/health")
async def check_agent_health(agent_id: str):
    """Perform health check on a specific agent"""
    try:
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
            )
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check health for agent {agent_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to check agent health: {str(e)}"
        )


@router.get("/status/overview")
async def get_agents_overview():
    """Get overview of all agents' status for dashboard"""
    try:
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

    except Exception as e:
        logger.error(f"Failed to get agents overview: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get agents overview: {str(e)}"
        )
