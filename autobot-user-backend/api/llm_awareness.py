# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Self-Awareness API for AutoBot
Provides endpoints for LLM agents to access system context and capabilities
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from llm_self_awareness import get_llm_self_awareness
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for context level validation (Issue #326)
VALID_CONTEXT_LEVELS = {"basic", "detailed", "full"}
DETAILED_CONTEXT_LEVELS = {"detailed", "full"}


class ContextRequest(BaseModel):
    level: str = "basic"  # basic, detailed, full
    include_history: bool = False
    include_progression_rules: bool = False


class PromptInjectionRequest(BaseModel):
    prompt: str
    context_level: str = "basic"
    preserve_format: bool = True


class QueryAnalysisRequest(BaseModel):
    query: str
    analyze_capabilities: bool = True
    provide_recommendations: bool = True


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_awareness_status",
    error_code_prefix="LLM_AWARENESS",
)
@router.get("/status")
async def get_awareness_status():
    """Get LLM self-awareness system status"""
    try:
        awareness = get_llm_self_awareness()
        context = await awareness.get_system_context(include_detailed=False)

        return {
            "status": "healthy",
            "service": "llm_awareness",
            "timestamp": datetime.now().isoformat(),
            "system_identity": context["system_identity"],
            "capabilities_count": context["current_capabilities"]["count"],
            "system_maturity": context["system_identity"]["system_maturity"],
        }
    except Exception as e:
        logger.error("Error getting awareness status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_context",
    error_code_prefix="LLM_AWARENESS",
)
@router.get("/context")
async def get_system_context(
    level: str = Query(
        "basic", description="Context detail level: basic, detailed, full"
    ),
    format: str = Query("json", description="Response format: json, summary"),
):
    """Get comprehensive system context for LLM awareness"""
    try:
        awareness = get_llm_self_awareness()

        # Validate level parameter
        if level not in VALID_CONTEXT_LEVELS:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": f"Invalid context level: {level}",
                    "valid_levels": list(VALID_CONTEXT_LEVELS),
                },
            )

        include_detailed = level in DETAILED_CONTEXT_LEVELS
        context = await awareness.get_system_context(include_detailed=include_detailed)

        if format == "summary":
            # Return a simplified summary format
            summary = {
                "system_name": context["system_identity"]["name"],
                "current_phase": context["system_identity"]["current_phase"],
                "system_maturity": context["system_identity"]["system_maturity"],
                "capabilities": {
                    "total": context["current_capabilities"]["count"],
                    "categories": list(
                        context["current_capabilities"]["categories"].keys()
                    ),
                    "recent_activities": len(context.get("recent_activities", [])),
                },
                "status": {
                    "auto_progression": context["operational_status"][
                        "auto_progression_enabled"
                    ],
                    "milestones_achieved": context["operational_status"][
                        "milestones_achieved"
                    ],
                },
            }
            return {
                "status": "success",
                "format": "summary",
                "context": summary,
                "timestamp": datetime.now().isoformat(),
            }

        return {
            "status": "success",
            "format": "json",
            "context": context,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error getting system context: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_capabilities_summary",
    error_code_prefix="LLM_AWARENESS",
)
@router.get("/capabilities")
async def get_capabilities_summary():
    """Get detailed capabilities summary"""
    try:
        awareness = get_llm_self_awareness()
        context = await awareness.get_system_context(include_detailed=True)

        capabilities_info = {
            "overview": {
                "total_capabilities": context["current_capabilities"]["count"],
                "categories": context["current_capabilities"]["categories"],
                "system_maturity": context["system_identity"]["system_maturity"],
            },
            "by_category": {},
            "detailed_info": context.get("detailed_capabilities", {}),
            "endpoints": context["contextual_information"]["api_endpoints_available"],
        }

        # Organize capabilities by category with counts
        for category, caps in context["current_capabilities"]["categories"].items():
            capabilities_info["by_category"][category] = {
                "count": len(caps),
                "capabilities": caps,
            }

        return {
            "status": "success",
            "capabilities": capabilities_info,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error getting capabilities summary: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="inject_awareness_context",
    error_code_prefix="LLM_AWARENESS",
)
@router.post("/inject-context")
async def inject_awareness_context(request: PromptInjectionRequest):
    """Inject system awareness context into a prompt"""
    try:
        awareness = get_llm_self_awareness()

        # Validate context level
        if request.context_level not in VALID_CONTEXT_LEVELS:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": f"Invalid context level: {request.context_level}",
                    "valid_levels": list(VALID_CONTEXT_LEVELS),
                },
            )

        # Inject context
        enhanced_prompt = await awareness.inject_awareness_context(
            request.prompt, context_level=request.context_level
        )

        return {
            "status": "success",
            "original_prompt": request.prompt,
            "enhanced_prompt": enhanced_prompt,
            "context_level": request.context_level,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error injecting context: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_query_with_awareness",
    error_code_prefix="LLM_AWARENESS",
)
@router.post("/analyze-query")
async def analyze_query_with_awareness(request: QueryAnalysisRequest):
    """Analyze a query with phase and capability awareness"""
    try:
        awareness = get_llm_self_awareness()

        # Get phase-aware response
        analysis = await awareness.get_phase_aware_response(request.query)

        return {
            "status": "success",
            "analysis": analysis,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error analyzing query: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_capability_summary_text",
    error_code_prefix="LLM_AWARENESS",
)
@router.get("/summary/text")
async def get_capability_summary_text():
    """Get human-readable capability summary"""
    try:
        awareness = get_llm_self_awareness()
        summary = awareness.create_capability_summary()

        return {
            "status": "success",
            "summary": summary,
            "format": "markdown",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error creating summary: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_phase_information",
    error_code_prefix="LLM_AWARENESS",
)
@router.get("/phase-info")
async def get_phase_information():
    """Get current phase information and progression status"""
    try:
        awareness = get_llm_self_awareness()
        context = await awareness.get_system_context(include_detailed=True)

        phase_info = {
            "current_phase": context["phase_information"]["current_phase"],
            "completion_status": context["phase_information"]["completion_status"],
            "completed_phases": context["phase_information"]["completed_phases"],
            "total_phases": context["phase_information"]["total_phases"],
            "progression_rules": context.get("phase_progression_rules", {}),
            "recent_activities": context.get("recent_activities", []),
        }

        return {
            "status": "success",
            "phase_info": phase_info,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error getting phase information: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_awareness_metrics",
    error_code_prefix="LLM_AWARENESS",
)
@router.get("/metrics")
async def get_awareness_metrics():
    """Get self-awareness system metrics"""
    try:
        awareness = get_llm_self_awareness()
        context = await awareness.get_system_context(include_detailed=False)

        metrics = {
            "system_metrics": context["system_metrics"],
            "operational_status": context["operational_status"],
            "cache_info": {
                "cache_active": awareness._context_cache is not None,
                "cache_age_seconds": (
                    (datetime.now() - awareness._cache_timestamp).seconds
                    if awareness._cache_timestamp
                    else None
                ),
                "cache_ttl": awareness._cache_ttl,
            },
            "context_categories": len(context["current_capabilities"]["categories"]),
            "api_endpoints": len(
                context["contextual_information"]["api_endpoints_available"]
            ),
        }

        return {
            "status": "success",
            "metrics": metrics,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error getting awareness metrics: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_awareness_data",
    error_code_prefix="LLM_AWARENESS",
)
@router.post("/export")
async def export_awareness_data(
    include_history: bool = Query(False),
    format: str = Query("json", description="Export format: json"),
):
    """Export comprehensive awareness data"""
    try:
        awareness = get_llm_self_awareness()

        # Export data
        output_path = await awareness.export_awareness_data()

        return {
            "status": "success",
            "message": "Awareness data exported successfully",
            "output_path": output_path,
            "format": format,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error exporting awareness data: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="llm_awareness_health",
    error_code_prefix="LLM_AWARENESS",
)
@router.get("/health")
async def llm_awareness_health():
    """Health check for LLM awareness system"""
    try:
        awareness = get_llm_self_awareness()

        # Quick health checks
        context = await awareness.get_system_context(include_detailed=False)

        health_status = {
            "awareness_module_loaded": awareness is not None,
            "context_available": context is not None,
            "capabilities_loaded": len(context["current_capabilities"]["active"]) > 0,
            "phase_info_available": (
                "current_phase" in context.get("phase_information", {})
            ),
            "cache_functional": awareness._context_cache is not None,
        }

        overall_healthy = all(health_status.values())

        return {
            "status": "healthy" if overall_healthy else "degraded",
            "service": "llm_awareness",
            "components": health_status,
            "system_maturity": context["system_identity"]["system_maturity"],
            "capabilities_count": context["current_capabilities"]["count"],
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("LLM awareness health check failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")
