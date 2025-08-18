# backend/api/agent_config.py
"""
Agent Configuration API

Provides endpoints for configuring and monitoring AI agents used throughout the system.
Each agent can have its own LLM model configuration and status monitoring.
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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
        "default_model": "llama3.2:1b-instruct-q4_K_M",
        "provider": "ollama",
        "enabled": True,
        "priority": 1,
        "tasks": ["workflow_planning", "task_classification", "agent_coordination"]
    },
    "chat": {
        "name": "Chat Agent",
        "description": "Conversational responses and user interaction",
        "default_model": "llama3.2:1b-instruct-q4_K_M",
        "provider": "ollama",
        "enabled": True,
        "priority": 1,
        "tasks": ["conversation", "user_assistance", "general_queries"]
    },
    "kb_librarian": {
        "name": "Knowledge Base Librarian",
        "description": "Knowledge base search and document retrieval",
        "default_model": "llama3.2:1b-instruct-q4_K_M",
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["knowledge_search", "document_analysis", "information_retrieval"]
    },
    "research": {
        "name": "Research Agent",
        "description": "Web research and information gathering",
        "default_model": "llama3.2:1b-instruct-q4_K_M",
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["web_research", "fact_checking", "data_gathering"]
    },
    "system_commands": {
        "name": "System Commands Agent",
        "description": "Command execution and system operations",
        "default_model": "llama3.2:1b-instruct-q4_K_M",
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["command_execution", "system_operations", "tool_usage"]
    },
    "security_scanner": {
        "name": "Security Scanner Agent",
        "description": "Security analysis and vulnerability assessment",
        "default_model": "llama3.2:1b-instruct-q4_K_M",
        "provider": "ollama",
        "enabled": True,
        "priority": 3,
        "tasks": ["security_analysis", "vulnerability_scanning", "threat_assessment"]
    },
    "code_analysis": {
        "name": "Code Analysis Agent",
        "description": "Code review and analysis tasks",
        "default_model": "llama3.2:1b-instruct-q4_K_M",
        "provider": "ollama",
        "enabled": True,
        "priority": 2,
        "tasks": ["code_review", "static_analysis", "bug_detection"]
    }
}


@router.get("/agents")
async def list_agents():
    """Get list of all available agents with their configurations"""
    try:
        from src.config import config as global_config_manager

        llm_config = global_config_manager.get_llm_config()
        provider_type = llm_config.get("provider_type", "local")

        agents = []
        for agent_id, config in DEFAULT_AGENT_CONFIGS.items():
            # Get current model from config or use default
            current_model = global_config_manager.get_nested(
                f"agents.{agent_id}.model",
                config["default_model"]
            )
            current_provider = global_config_manager.get_nested(
                f"agents.{agent_id}.provider",
                config["provider"]
            )
            enabled = global_config_manager.get_nested(
                f"agents.{agent_id}.enabled",
                config["enabled"]
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
                    "total_requests": 0
                }
            }
            agents.append(agent_info)

        return JSONResponse(status_code=200, content={
            "agents": agents,
            "total_count": len(agents),
            "global_provider_type": provider_type,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Failed to list agents: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list agents: {str(e)}")


@router.get("/agents/{agent_id}")
async def get_agent_config(agent_id: str):
    """Get detailed configuration for a specific agent"""
    try:
        if agent_id not in DEFAULT_AGENT_CONFIGS:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

        from src.config import config as global_config_manager

        base_config = DEFAULT_AGENT_CONFIGS[agent_id]

        # Get current configuration
        current_model = global_config_manager.get_nested(
            f"agents.{agent_id}.model",
            base_config["default_model"]
        )
        current_provider = global_config_manager.get_nested(
            f"agents.{agent_id}.provider",
            base_config["provider"]
        )
        enabled = global_config_manager.get_nested(
            f"agents.{agent_id}.enabled",
            base_config["enabled"]
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
                "configurable_settings": ["model", "provider", "enabled", "priority"]
            },
            "health_check": {
                "last_check": datetime.now().isoformat(),
                "response_time": 0.0,
                "status": "healthy" if enabled else "disabled"
            }
        }

        return JSONResponse(status_code=200, content=agent_config)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent config for {agent_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get agent config: {str(e)}"
        )


@router.post("/agents/{agent_id}/model")
async def update_agent_model(agent_id: str, update: AgentModelUpdate):
    """Update the LLM model for a specific agent"""
    try:
        if agent_id not in DEFAULT_AGENT_CONFIGS:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

        from src.config import config as global_config_manager

        # Validate the update request
        if update.agent_id != agent_id:
            raise HTTPException(
                status_code=400,
                detail="Agent ID in URL must match agent ID in request body"
            )

        # Update the configuration
        global_config_manager.set_nested(f"agents.{agent_id}.model", update.model)
        if update.provider:
            global_config_manager.set_nested(
                f"agents.{agent_id}.provider",
                update.provider
            )

        # Save the configuration
        global_config_manager.save_settings()

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
            "timestamp": datetime.now().isoformat()
        }

        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": f"Agent {agent_id} model updated successfully",
            "updated_config": updated_config
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent {agent_id} model: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update agent model: {str(e)}"
        )


@router.post("/agents/{agent_id}/enable")
async def enable_agent(agent_id: str):
    """Enable a specific agent"""
    try:
        if agent_id not in DEFAULT_AGENT_CONFIGS:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

        from src.config import config as global_config_manager

        global_config_manager.set_nested(f"agents.{agent_id}.enabled", True)
        global_config_manager.save_settings()

        logger.info(f"Enabled agent {agent_id}")

        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": f"Agent {agent_id} enabled successfully",
            "agent_name": DEFAULT_AGENT_CONFIGS[agent_id]["name"]
        })

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

        from src.config import config as global_config_manager

        global_config_manager.set_nested(f"agents.{agent_id}.enabled", False)
        global_config_manager.save_settings()

        logger.info(f"Disabled agent {agent_id}")

        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": f"Agent {agent_id} disabled successfully",
            "agent_name": DEFAULT_AGENT_CONFIGS[agent_id]["name"]
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disable agent {agent_id}: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to disable agent: {str(e)}"
        )


@router.get("/agents/{agent_id}/health")
async def check_agent_health(agent_id: str):
    """Perform health check on a specific agent"""
    try:
        if agent_id not in DEFAULT_AGENT_CONFIGS:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

        from src.config import config as global_config_manager

        enabled = global_config_manager.get_nested(f"agents.{agent_id}.enabled", True)
        model = global_config_manager.get_nested(
            f"agents.{agent_id}.model",
            DEFAULT_AGENT_CONFIGS[agent_id]["default_model"]
        )

        # Simple health check - for now just check if enabled and has model
        is_healthy = enabled and bool(model)

        health_status = {
            "agent_id": agent_id,
            "agent_name": DEFAULT_AGENT_CONFIGS[agent_id]["name"],
            "status": "healthy" if is_healthy else "unhealthy",
            "enabled": enabled,
            "model": model,
            "checks": {
                "enabled": enabled,
                "model_configured": bool(model),
                "provider_available": True  # TODO: Actually check provider availability
            },
            "timestamp": datetime.now().isoformat(),
            "response_time": 0.001  # Mock response time
        }

        return JSONResponse(status_code=200, content=health_status)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check health for agent {agent_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check agent health: {str(e)}"
        )


@router.get("/status/overview")
async def get_agents_overview():
    """Get overview of all agents' status for dashboard"""
    try:
        from src.config import config as global_config_manager

        total_agents = len(DEFAULT_AGENT_CONFIGS)
        enabled_agents = 0
        healthy_agents = 0

        agent_summary = []

        for agent_id, config in DEFAULT_AGENT_CONFIGS.items():
            enabled = global_config_manager.get_nested(f"agents.{agent_id}.enabled", config["enabled"])
            model = global_config_manager.get_nested(f"agents.{agent_id}.model", config["default_model"])

            if enabled:
                enabled_agents += 1
                if model:
                    healthy_agents += 1

            agent_summary.append({
                "id": agent_id,
                "name": config["name"],
                "enabled": enabled,
                "status": "healthy" if enabled and model else "unhealthy",
                "priority": config["priority"]
            })

        overview = {
            "total_agents": total_agents,
            "enabled_agents": enabled_agents,
            "healthy_agents": healthy_agents,
            "unhealthy_agents": enabled_agents - healthy_agents,
            "disabled_agents": total_agents - enabled_agents,
            "overall_health": "good" if healthy_agents >= enabled_agents * 0.8 else "warning",
            "agents": agent_summary,
            "timestamp": datetime.now().isoformat()
        }

        return JSONResponse(status_code=200, content=overview)

    except Exception as e:
        logger.error(f"Failed to get agents overview: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get agents overview: {str(e)}"
        )
