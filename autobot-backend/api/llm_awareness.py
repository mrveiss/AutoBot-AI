# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
LLM Self-Awareness API for AutoBot
Provides endpoints for LLM agents to access system context and capabilities
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.schemas_agent import (
    LLMAnalyzeQueryResponse,
    LLMAwarenessMetricsResponse,
    LLMAwarenessStatusResponse,
    LLMCapabilitiesSummaryResponse,
    LLMCapabilitySummaryTextResponse,
    LLMExportAwarenessResponse,
    LLMInjectContextResponse,
    LLMPhaseInfoResponse,
    LLMSystemContextResponse,
    PromptInjectionRequest,
    QueryAnalysisRequest,
)
from api.system_health import register_singleton_probe
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from llm_self_awareness import get_llm_self_awareness

router = APIRouter()
logger = get_logger(__name__)

# Performance optimization: O(1) lookup for context level validation (Issue #326)
VALID_CONTEXT_LEVELS = {"basic", "detailed", "full"}
DETAILED_CONTEXT_LEVELS = {"detailed", "full"}


@router.get("/status", response_model=LLMAwarenessStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_awareness_status",
    error_code_prefix="LLM_AWARENESS",
)
async def get_awareness_status():
    """Get LLM self-awareness system status"""
    try:
        awareness = get_llm_self_awareness()
        context = await awareness.get_system_context(include_detailed=False)

        return {
            "status": "healthy",
            "service": "llm_awareness",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "system_identity": context["system_identity"],
            "capabilities_count": context["current_capabilities"]["count"],
            "system_maturity": context["system_identity"]["system_maturity"],
        }
    except Exception as e:
        logger.error("Error getting awareness status: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/context", response_model=LLMSystemContextResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_context",
    error_code_prefix="LLM_AWARENESS",
)
async def get_system_context(
    level: str = Query("basic", description="Context detail level: basic, detailed, full"),
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
                    "categories": list(context["current_capabilities"]["categories"].keys()),
                    "recent_activities": len(context.get("recent_activities", [])),
                },
                "status": {
                    "auto_progression": context["operational_status"]["auto_progression_enabled"],
                    "milestones_achieved": context["operational_status"]["milestones_achieved"],
                },
            }
            return {
                "status": "success",
                "format": "summary",
                "context": summary,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            }

        return {
            "status": "success",
            "format": "json",
            "context": context,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting system context: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/capabilities", response_model=LLMCapabilitiesSummaryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_capabilities_summary",
    error_code_prefix="LLM_AWARENESS",
)
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
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting capabilities summary: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/inject-context", response_model=LLMInjectContextResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="inject_awareness_context",
    error_code_prefix="LLM_AWARENESS",
)
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
        enhanced_prompt = await awareness.inject_awareness_context(request.prompt, context_level=request.context_level)

        return {
            "status": "success",
            "original_prompt": request.prompt,
            "enhanced_prompt": enhanced_prompt,
            "context_level": request.context_level,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("Error injecting context: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/analyze-query", response_model=LLMAnalyzeQueryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_query_with_awareness",
    error_code_prefix="LLM_AWARENESS",
)
async def analyze_query_with_awareness(request: QueryAnalysisRequest):
    """Analyze a query with phase and capability awareness"""
    try:
        awareness = get_llm_self_awareness()

        # Get phase-aware response
        analysis = await awareness.get_phase_aware_response(request.query)

        return {
            "status": "success",
            "analysis": analysis,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("Error analyzing query: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/summary/text", response_model=LLMCapabilitySummaryTextResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_capability_summary_text",
    error_code_prefix="LLM_AWARENESS",
)
async def get_capability_summary_text():
    """Get human-readable capability summary"""
    try:
        awareness = get_llm_self_awareness()
        summary = awareness.create_capability_summary()

        return {
            "status": "success",
            "summary": summary,
            "format": "markdown",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("Error creating summary: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/phase-info", response_model=LLMPhaseInfoResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_phase_information",
    error_code_prefix="LLM_AWARENESS",
)
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
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting phase information: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/metrics", response_model=LLMAwarenessMetricsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_awareness_metrics",
    error_code_prefix="LLM_AWARENESS",
)
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
                    (datetime.now(tz=timezone.utc) - awareness._cache_timestamp).seconds
                    if awareness._cache_timestamp
                    else None
                ),
                "cache_ttl": awareness._cache_ttl,
            },
            "context_categories": len(context["current_capabilities"]["categories"]),
            "api_endpoints": len(context["contextual_information"]["api_endpoints_available"]),
        }

        return {
            "status": "success",
            "metrics": metrics,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting awareness metrics: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/export", response_model=LLMExportAwarenessResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_awareness_data",
    error_code_prefix="LLM_AWARENESS",
)
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
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("Error exporting awareness data: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


register_singleton_probe("llm_awareness", get_llm_self_awareness)
