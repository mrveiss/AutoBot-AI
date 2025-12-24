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
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

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


def _parse_agent_frontmatter(content: str) -> dict[str, Any]:
    """
    Parse YAML frontmatter from Claude agent markdown files.

    Args:
        content: Raw markdown file content

    Returns:
        dict: Parsed frontmatter fields (name, description, tools, color, model)
    """
    result = {
        "name": "",
        "description": "",
        "tools": [],
        "color": "gray",
        "model": None,
    }

    # Match YAML frontmatter between --- markers
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not frontmatter_match:
        return result

    frontmatter = frontmatter_match.group(1)

    # Parse simple YAML fields
    for line in frontmatter.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            if key == "name":
                result["name"] = value
            elif key == "description":
                result["description"] = value
            elif key == "tools":
                # Tools can be comma-separated list
                result["tools"] = [t.strip() for t in value.split(",") if t.strip()]
            elif key == "color":
                result["color"] = value
            elif key == "model":
                result["model"] = value

    return result


def _categorize_agent(name: str, description: str) -> str:
    """
    Categorize agent based on name and description.

    Args:
        name: Agent name
        description: Agent description

    Returns:
        str: Category (implementation, analysis, planning, specialized)
    """
    name_lower = name.lower()
    desc_lower = description.lower()

    # Implementation agents
    if any(
        kw in name_lower
        for kw in [
            "engineer",
            "developer",
            "backend",
            "frontend",
            "database",
            "devops",
            "testing",
        ]
    ):
        if "review" in name_lower or "analysis" in desc_lower:
            return "analysis"
        return "implementation"

    # Analysis agents
    if any(
        kw in name_lower
        for kw in ["skeptic", "architect", "performance", "security", "auditor", "review"]
    ):
        return "analysis"

    # Planning agents
    if any(kw in name_lower for kw in ["project", "manager", "planner", "prd", "task"]):
        return "planning"

    # Content/specialized agents
    if any(
        kw in name_lower
        for kw in ["content", "writer", "designer", "compacter", "memory", "refactor"]
    ):
        return "specialized"

    return "general"


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_claude_agents",
    error_code_prefix="AGENT_CONFIG",
)
@router.get("/agents/claude")
async def list_claude_agents():
    """
    Get list of all Claude specialized agents from .claude/agents/ directory.

    Returns agent definitions parsed from markdown files including:
    - name, description, tools, color, model
    - category (implementation, analysis, planning, specialized)
    """
    agents_dir = Path(__file__).parent.parent.parent / ".claude" / "agents"

    if not agents_dir.exists():
        logger.warning("Claude agents directory not found: %s", agents_dir)
        return JSONResponse(
            status_code=200,
            content={
                "agents": [],
                "total_count": 0,
                "categories": {},
                "timestamp": datetime.now().isoformat(),
                "error": "Claude agents directory not found",
            },
        )

    agents = []
    categories: dict[str, int] = {
        "implementation": 0,
        "analysis": 0,
        "planning": 0,
        "specialized": 0,
        "general": 0,
    }

    # Read all .md files in the agents directory
    for md_file in sorted(agents_dir.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
            parsed = _parse_agent_frontmatter(content)

            # Use filename as fallback name
            agent_name = parsed["name"] or md_file.stem

            # Categorize the agent
            category = _categorize_agent(agent_name, parsed["description"])
            categories[category] += 1

            agent_info = {
                "id": md_file.stem,
                "name": agent_name,
                "description": parsed["description"],
                "tools": parsed["tools"][:10],  # Limit tools for display
                "tool_count": len(parsed["tools"]),
                "color": parsed["color"],
                "model": parsed["model"],
                "category": category,
                "file": md_file.name,
                "status": "available",
            }
            agents.append(agent_info)

        except Exception as e:
            logger.warning("Failed to parse agent file %s: %s", md_file.name, e)
            continue

    return JSONResponse(
        status_code=200,
        content={
            "agents": agents,
            "total_count": len(agents),
            "categories": categories,
            "timestamp": datetime.now().isoformat(),
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_claude_agent",
    error_code_prefix="AGENT_CONFIG",
)
@router.get("/agents/claude/{agent_id}")
async def get_claude_agent(agent_id: str):
    """
    Get detailed information for a specific Claude agent.

    Args:
        agent_id: Agent identifier (filename without .md extension)

    Returns:
        Detailed agent information including full tool list and description
    """
    agents_dir = Path(__file__).parent.parent.parent / ".claude" / "agents"
    agent_file = agents_dir / f"{agent_id}.md"

    if not agent_file.exists():
        raise HTTPException(
            status_code=404, detail=f"Claude agent '{agent_id}' not found"
        )

    try:
        content = agent_file.read_text(encoding="utf-8")
        parsed = _parse_agent_frontmatter(content)

        # Extract the body content (after frontmatter)
        body_match = re.search(r"^---\s*\n.*?\n---\s*\n(.*)$", content, re.DOTALL)
        body = body_match.group(1).strip() if body_match else ""

        # Get first section as summary (up to first ## heading)
        summary_match = re.match(r"^(.*?)(?=\n##|\Z)", body, re.DOTALL)
        summary = summary_match.group(1).strip() if summary_match else body[:500]

        agent_name = parsed["name"] or agent_id
        category = _categorize_agent(agent_name, parsed["description"])

        agent_detail = {
            "id": agent_id,
            "name": agent_name,
            "description": parsed["description"],
            "summary": summary,
            "tools": parsed["tools"],
            "tool_count": len(parsed["tools"]),
            "color": parsed["color"],
            "model": parsed["model"],
            "category": category,
            "file": agent_file.name,
            "file_size": agent_file.stat().st_size,
            "last_modified": datetime.fromtimestamp(
                agent_file.stat().st_mtime
            ).isoformat(),
            "status": "available",
        }

        return JSONResponse(status_code=200, content=agent_detail)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to read agent file %s: %s", agent_file.name, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to read agent: {str(e)}"
        ) from e


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_all_agents_combined",
    error_code_prefix="AGENT_CONFIG",
)
@router.get("/agents/all")
async def get_all_agents_combined():
    """
    Get combined view of all agents (backend + Claude agents).

    Returns unified list for the Agent Registry dashboard.
    """
    from src.unified_config_manager import unified_config_manager

    # Get backend agents
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

    # Get Claude agents
    claude_agents = []
    agents_dir = Path(__file__).parent.parent.parent / ".claude" / "agents"

    if agents_dir.exists():
        for md_file in sorted(agents_dir.glob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
                parsed = _parse_agent_frontmatter(content)
                agent_name = parsed["name"] or md_file.stem

                claude_agents.append(
                    {
                        "id": md_file.stem,
                        "name": agent_name,
                        "description": parsed["description"],
                        "type": "claude",
                        "model": parsed["model"] or "claude",
                        "enabled": True,
                        "status": "available",
                        "priority": 1,
                        "tools": parsed["tools"][:5],
                        "tool_count": len(parsed["tools"]),
                        "color": parsed["color"],
                        "category": _categorize_agent(agent_name, parsed["description"]),
                    }
                )
            except Exception as e:
                logger.warning("Failed to parse agent %s: %s", md_file.name, e)

    return JSONResponse(
        status_code=200,
        content={
            "backend_agents": backend_agents,
            "claude_agents": claude_agents,
            "summary": {
                "total_backend": len(backend_agents),
                "total_claude": len(claude_agents),
                "total": len(backend_agents) + len(claude_agents),
                "healthy_backend": sum(
                    1 for a in backend_agents if a["status"] == "connected"
                ),
                "available_claude": len(claude_agents),
            },
            "timestamp": datetime.now().isoformat(),
        },
    )
