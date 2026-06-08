# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Model Optimization API Endpoints
Provides intelligent model selection, performance tracking, and optimization suggestions.
"""

import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from api.schemas_agent import (
    InferenceOptimizationSettings,
    LLMAvailableModelsResponse,
    LLMBenchmarkResponse,
    LLMInferenceMetricsResponse,
    LLMInferenceSettingsResponse,
    LLMModelPerformanceHistoryResponse,
    LLMModelsComparisonResponse,
    LLMOptimizationConfigResponse,
    LLMOptimizationRequest,
    LLMOptimizationSuggestionsResponse,
    LLMProviderOptimizationSummaryResponse,
    LLMSelectModelResponse,
    LLMSystemResourcesResponse,
    LLMTrackPerformanceResponse,
    ModelPerformanceData,
)
from api.system_health import register_singleton_probe
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from config.manager import get_config_manager
from services.llm_service import get_llm_service
from utils.model_optimizer import TaskRequest, get_model_optimizer

router = APIRouter()
logger = get_logger(__name__)

config = get_config_manager()


register_singleton_probe("llm_optimization", get_model_optimizer)


@router.get("/models/available", response_model=LLMAvailableModelsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_available_models",
    error_code_prefix="LLM_OPTIMIZATION",
)
async def get_available_models(admin_check: bool = Depends(check_admin_permission)):
    """Get all available models with performance data

    Issue #744: Requires admin authentication."""
    try:
        optimizer = get_model_optimizer()
        models = await optimizer.refresh_available_models()

        # Issue #372: Use model method to reduce feature envy
        models_data = [model.to_info_dict() for model in models]

        # Sort by performance level and success rate
        models_data.sort(key=lambda x: (x["performance_level"], -x["success_rate"]))

        return {
            "models_count": len(models_data),
            "models": models_data,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error("Error getting available models: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get available models")


@router.post("/models/select", response_model=LLMSelectModelResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="select_optimal_model",
    error_code_prefix="LLM_OPTIMIZATION",
)
async def select_optimal_model(request: LLMOptimizationRequest, admin_check: bool = Depends(check_admin_permission)):
    """Select the optimal model for a given task

    Issue #744: Requires admin authentication."""
    try:
        optimizer = get_model_optimizer()

        # Create task request
        task_request = TaskRequest(
            query=request.query,
            task_type=request.task_type,
            max_response_time=request.max_response_time,
            min_quality=request.min_quality,
            context_length=request.context_length,
            user_preference=request.user_preference,
        )

        # Analyze task complexity
        complexity = optimizer.analyze_task_complexity(task_request)

        # Select optimal model
        selected_model = await optimizer.select_optimal_model(task_request)

        # Get model details - Issue #372: Use model method to reduce feature envy
        model_details = None
        if selected_model and selected_model in optimizer._models_cache:
            model = optimizer._models_cache[selected_model]
            model_details = model.to_select_dict()

        # Get system resources
        resources = optimizer.get_system_resources()

        return {
            "selected_model": selected_model,
            "model_details": model_details,
            "task_complexity": complexity.value,
            "selection_reasoning": {
                "complexity_analysis": f"Task classified as {complexity.value}",
                "resource_status": {
                    "cpu_percent": resources["cpu_percent"],
                    "memory_percent": resources["memory_percent"],
                    "available_memory_gb": resources["available_memory_gb"],
                },
                "selection_criteria": ("Balanced for performance, quality, and resource efficiency"),
            },
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error("Error selecting optimal model: %s", e)
        raise HTTPException(status_code=500, detail="Failed to select optimal model")


@router.post("/models/performance/track", response_model=LLMTrackPerformanceResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="track_model_performance",
    error_code_prefix="LLM_OPTIMIZATION",
)
async def track_model_performance(
    performance_data: ModelPerformanceData,
    admin_check: bool = Depends(check_admin_permission),
):
    """Track model performance for future optimization

    Issue #744: Requires admin authentication."""
    try:
        optimizer = get_model_optimizer()

        await optimizer.track_model_performance(
            model_name=performance_data.model_name,
            response_time=performance_data.response_time,
            response_tokens=performance_data.response_tokens,
            success=performance_data.success,
        )

        return {
            "status": "success",
            "message": f"Performance data recorded for {performance_data.model_name}",
            "recorded_data": {
                "model": performance_data.model_name,
                "response_time": performance_data.response_time,
                "tokens": performance_data.response_tokens,
                "success": performance_data.success,
            },
        }

    except Exception as e:
        logger.error("Error tracking model performance: %s", e)
        raise HTTPException(status_code=500, detail="Failed to track performance")


@router.get("/models/performance/history/{model_name}", response_model=LLMModelPerformanceHistoryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_model_performance_history",
    error_code_prefix="LLM_OPTIMIZATION",
)
async def get_model_performance_history(model_name: str, admin_check: bool = Depends(check_admin_permission)):
    """Get performance history for a specific model

    Issue #744: Requires admin authentication."""
    try:
        optimizer = get_model_optimizer()

        # Refresh models to get latest performance data
        await optimizer.refresh_available_models()

        if model_name not in optimizer._models_cache:
            raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")

        model = optimizer._models_cache[model_name]

        # Issue #372: Use model method to reduce feature envy
        return model.to_performance_history_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting model performance history: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get performance history")


@router.get("/optimization/suggestions", response_model=LLMOptimizationSuggestionsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_optimization_suggestions",
    error_code_prefix="LLM_OPTIMIZATION",
)
async def get_optimization_suggestions(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get optimization suggestions based on usage patterns

    Issue #744: Requires admin authentication."""
    try:
        optimizer = get_model_optimizer()
        suggestions = await optimizer.get_optimization_suggestions()

        return {
            "suggestions_count": len(suggestions),
            "suggestions": suggestions,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error("Error getting optimization suggestions: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get optimization suggestions")


@router.get("/models/comparison", response_model=LLMModelsComparisonResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="compare_models",
    error_code_prefix="LLM_OPTIMIZATION",
)
async def compare_models(admin_check: bool = Depends(check_admin_permission)):
    """Compare all available models by performance metrics

    Issue #744: Requires admin authentication."""
    try:
        optimizer = get_model_optimizer()
        models = await optimizer.refresh_available_models()

        if not models:
            return {"message": "No models available for comparison", "models": []}

        # Separate models by performance level
        comparison_data = {
            "lightweight": [],
            "standard": [],
            "advanced": [],
            "specialized": [],
        }

        # Issue #372: Use model method to reduce feature envy
        for model in models:
            model_data = model.to_comparison_dict()

            level_key = model.performance_level.value
            if level_key in comparison_data:
                comparison_data[level_key].append(model_data)

        # Sort each category by performance score
        for level in comparison_data:
            comparison_data[level].sort(key=lambda x: x["performance_score"], reverse=True)

        # Find best models in each category
        best_models = {}
        for level, models_list in comparison_data.items():
            if models_list:
                best_models[f"best_{level}"] = models_list[0]

        return {
            "comparison": comparison_data,
            "best_models": best_models,
            "total_models": len(models),
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error("Error comparing models: %s", e)
        raise HTTPException(status_code=500, detail="Failed to compare models")


@router.post("/models/benchmark/{model_name}", response_model=LLMBenchmarkResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="benchmark_model",
    error_code_prefix="LLM_OPTIMIZATION",
)
async def benchmark_model(
    model_name: str,
    admin_check: bool = Depends(check_admin_permission),
    test_queries: List[str] = None,
    iterations: int = 3,
):
    """Benchmark a specific model with test queries

    Issue #744: Requires admin authentication."""
    try:
        if not test_queries:
            test_queries = [
                "What is the capital of France?",
                "Explain the concept of machine learning in simple terms.",
                "Write a simple Python function to calculate fibonacci numbers.",
                "Analyze the pros and cons of renewable energy sources.",
            ]

        if iterations > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 iterations allowed")

        optimizer = get_model_optimizer()

        # Check if model exists
        models = await optimizer.refresh_available_models()
        if not any(model.name == model_name for model in models):
            raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")

        # Note: In a real implementation, you would actually call the model here
        # For now, we'll return a benchmark structure
        benchmark_results = {
            "model_name": model_name,
            "test_queries": test_queries,
            "iterations_per_query": iterations,
            "status": "benchmark_scheduled",
            "message": ("Benchmark scheduled. In a real implementation, this would run the actual model tests."),
            "expected_metrics": [
                "average_response_time",
                "tokens_per_second",
                "success_rate",
                "quality_scores",
                "resource_usage",
            ],
            "timestamp": time.time(),
        }

        return benchmark_results

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error benchmarking model: %s", e)
        raise HTTPException(status_code=500, detail="Failed to benchmark model")


@router.get("/system/resources", response_model=LLMSystemResourcesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_resources",
    error_code_prefix="LLM_OPTIMIZATION",
)
async def get_system_resources(admin_check: bool = Depends(check_admin_permission)):
    """Get current system resources for model optimization

    Issue #744: Requires admin authentication."""
    try:
        optimizer = get_model_optimizer()
        resources = optimizer.get_system_resources()

        # Add resource recommendations
        recommendations = []

        if resources["cpu_percent"] > 80:
            recommendations.append(
                {
                    "type": "warning",
                    "message": "High CPU usage detected",
                    "suggestion": ("Consider using lighter models or reducing concurrent requests"),
                }
            )

        if resources["memory_percent"] > 85:
            recommendations.append(
                {
                    "type": "warning",
                    "message": "High memory usage detected",
                    "suggestion": "Consider using smaller models or freeing up memory",
                }
            )

        if resources["available_memory_gb"] > 16:
            recommendations.append(
                {
                    "type": "optimization",
                    "message": "Abundant memory available",
                    "suggestion": "System can handle larger, more capable models",
                }
            )

        return {
            "resources": resources,
            "recommendations": recommendations,
            "optimal_model_size_gb": min(
                resources["available_memory_gb"] * 0.6, 12
            ),  # 60% of available memory, capped at 12GB
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error("Error getting system resources: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get system resources")


@router.get("/config", response_model=LLMOptimizationConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_optimization_config",
    error_code_prefix="LLM_OPTIMIZATION",
)
async def get_optimization_config(admin_check: bool = Depends(check_admin_permission)):
    """Get current optimization configuration

    Issue #744: Requires admin authentication."""
    try:
        optimization_config = {
            "performance_threshold": config.get("llm.optimization.performance_threshold", 0.8),
            "cache_ttl": config.get("llm.optimization.cache_ttl", 3600),
            "min_samples": config.get("llm.optimization.min_samples", 5),
            "model_classification": {
                "lightweight_threshold": "< 2B parameters",
                "standard_range": "2-8B parameters",
                "advanced_threshold": "> 8B parameters",
            },
            "task_complexity_levels": ["simple", "moderate", "complex", "specialized"],
            "optimization_factors": [
                "task_complexity",
                "system_resources",
                "historical_performance",
                "user_preferences",
                "response_time_requirements",
            ],
        }

        return optimization_config

    except Exception as e:
        logger.error("Error getting optimization config: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get optimization config")


# ============================================================================
# Issue #717: Inference Optimization Settings Endpoints
# ============================================================================


def _get_prompt_compression_settings(opt_config: dict) -> dict:
    """
    Extract prompt compression settings from config.

    Issue #620: Extracted from get_inference_optimization_settings.
    """
    pc = opt_config.get("prompt_compression", {})
    return {
        "prompt_compression_enabled": pc.get("enabled", True),
        "prompt_compression_ratio": pc.get("target_ratio", 0.7),
        "prompt_compression_min_length": pc.get("min_length", 100),
        "prompt_compression_preserve_code": pc.get("preserve_code_blocks", True),
        "prompt_compression_aggressive": pc.get("aggressive_mode", False),
    }


def _get_cache_settings(opt_config: dict) -> dict:
    """
    Extract cache settings from config.

    Issue #620: Extracted from get_inference_optimization_settings.
    """
    cache = opt_config.get("cache", {})
    return {
        "cache_enabled": cache.get("enabled", True),
        "cache_l1_size": cache.get("l1_size", 100),
        "cache_l2_ttl": cache.get("l2_ttl", 300),
    }


def _get_cloud_settings(opt_config: dict) -> dict:
    """
    Extract cloud optimization settings from config.

    Issue #620: Extracted from get_inference_optimization_settings.
    """
    cloud = opt_config.get("cloud", {})
    return {
        "cloud_connection_pool_size": cloud.get("connection_pool_size", 100),
        "cloud_batch_window_ms": cloud.get("batch_window_ms", 50),
        "cloud_max_batch_size": cloud.get("max_batch_size", 10),
        "cloud_retry_max_attempts": cloud.get("retry_max_attempts", 3),
        "cloud_retry_base_delay": cloud.get("retry_base_delay", 1.0),
        "cloud_retry_max_delay": cloud.get("retry_max_delay", 60.0),
    }


def _get_local_settings(opt_config: dict) -> dict:
    """
    Extract local optimization settings from config.

    Issue #620: Extracted from get_inference_optimization_settings.
    """
    local = opt_config.get("local", {})
    return {
        "local_speculation_enabled": local.get("speculation_enabled", False),
        "local_speculation_draft_model": local.get("speculation_draft_model", ""),
        "local_speculation_num_tokens": local.get("speculation_num_tokens", 5),
        "local_speculation_use_ngram": local.get("speculation_use_ngram", False),
        "local_quantization_type": local.get("quantization_type", "none"),
        "local_vllm_multi_step": local.get("vllm_multi_step", 8),
        "local_vllm_prefix_caching": local.get("vllm_prefix_caching", True),
        "local_vllm_async_output": local.get("vllm_async_output", True),
    }


@router.get("/inference/settings", response_model=LLMInferenceSettingsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_inference_optimization_settings",
    error_code_prefix="LLM_OPTIMIZATION",
)
async def get_inference_optimization_settings(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get current inference optimization settings (Issue #717).

    Returns settings for:
    - Prompt compression
    - Response caching
    - Cloud optimizations (connection pooling, batching, rate limiting)
    - Local optimizations (speculative decoding, quantization, vLLM)

    Issue #620: Refactored to use helper functions.
    Issue #744: Requires admin authentication.
    """
    try:
        opt_config = config.get("optimization", {})

        # Build settings using helper functions (Issue #620)
        settings = InferenceOptimizationSettings(
            **_get_prompt_compression_settings(opt_config),
            **_get_cache_settings(opt_config),
            **_get_cloud_settings(opt_config),
            **_get_local_settings(opt_config),
        )

        return {
            "settings": settings.model_dump(),
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error("Error getting inference optimization settings: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to get inference optimization settings",
        )


@router.post("/inference/settings", response_model=LLMInferenceSettingsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_inference_optimization_settings",
    error_code_prefix="LLM_OPTIMIZATION",
)
async def update_inference_optimization_settings(
    settings: InferenceOptimizationSettings,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Update inference optimization settings (Issue #717).

    Saves settings to config and updates runtime configuration.
    Issue #744: Requires admin authentication.
    """
    try:
        # Build optimization config structure
        optimization_config = {
            "prompt_compression": {
                "enabled": settings.prompt_compression_enabled,
                "target_ratio": settings.prompt_compression_ratio,
                "min_length": settings.prompt_compression_min_length,
                "preserve_code_blocks": settings.prompt_compression_preserve_code,
                "aggressive_mode": settings.prompt_compression_aggressive,
            },
            "cache": {
                "enabled": settings.cache_enabled,
                "l1_size": settings.cache_l1_size,
                "l2_ttl": settings.cache_l2_ttl,
            },
            "cloud": {
                "connection_pool_size": settings.cloud_connection_pool_size,
                "batch_window_ms": settings.cloud_batch_window_ms,
                "max_batch_size": settings.cloud_max_batch_size,
                "retry_max_attempts": settings.cloud_retry_max_attempts,
                "retry_base_delay": settings.cloud_retry_base_delay,
                "retry_max_delay": settings.cloud_retry_max_delay,
            },
            "local": {
                "speculation_enabled": settings.local_speculation_enabled,
                "speculation_draft_model": settings.local_speculation_draft_model,
                "speculation_num_tokens": settings.local_speculation_num_tokens,
                "speculation_use_ngram": settings.local_speculation_use_ngram,
                "quantization_type": settings.local_quantization_type,
                "vllm_multi_step": settings.local_vllm_multi_step,
                "vllm_prefix_caching": settings.local_vllm_prefix_caching,
                "vllm_async_output": settings.local_vllm_async_output,
            },
        }

        # Save to config
        config.set("optimization", optimization_config)
        config.save()

        logger.info("Inference optimization settings updated")

        return {
            "status": "success",
            "message": "Inference optimization settings updated",
            "settings": settings.model_dump(),
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error("Error updating inference optimization settings: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to update inference optimization settings",
        )


@router.get("/inference/metrics", response_model=LLMInferenceMetricsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_inference_metrics",
    error_code_prefix="LLM_OPTIMIZATION",
)
async def get_inference_metrics(admin_check: bool = Depends(check_admin_permission)):
    """
    Get inference optimization metrics (Issue #717).

    Returns real-time metrics from the LLMInterface optimization layer.
    Issue #744: Requires admin authentication.
    """
    try:
        llm_interface = get_llm_service()
        metrics = llm_interface.get_metrics()

        return {
            "optimization": metrics.get("optimization", {}),
            "cache": metrics.get("cache", {}),
            "provider_usage": metrics.get("provider_usage", {}),
            "total_requests": metrics.get("total_requests", 0),
            "avg_response_time": metrics.get("avg_response_time", 0.0),
            "fallback_count": metrics.get("fallback_count", 0),
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error("Error getting inference metrics: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to get inference metrics",
        )


@router.get("/inference/provider/{provider_type}/optimizations", response_model=LLMProviderOptimizationSummaryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_provider_optimization_summary",
    error_code_prefix="LLM_OPTIMIZATION",
)
async def get_provider_optimization_summary(provider_type: str, admin_check: bool = Depends(check_admin_permission)):
    """
    Get optimization summary for a specific provider type (Issue #717).

    Args:
        provider_type: Provider type (ollama, openai, anthropic, vllm, etc.)

    Returns applicable optimizations for the provider.
    Issue #744: Requires admin authentication.
    """
    try:
        from llm_shared.optimization import get_optimization_router
        from llm_shared.types import ProviderType

        # Map provider string to enum
        provider_map = {
            "ollama": ProviderType.OLLAMA,
            "openai": ProviderType.OPENAI,
            "anthropic": ProviderType.ANTHROPIC,
            "vllm": ProviderType.VLLM,
            "transformers": ProviderType.TRANSFORMERS,
            "local": ProviderType.LOCAL,
        }

        provider_enum = provider_map.get(provider_type.lower())
        if not provider_enum:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown provider type: {provider_type}. " f"Valid types: {list(provider_map.keys())}",
            )

        router = get_optimization_router()
        summary = router.get_optimization_summary(provider_enum)

        return {
            "provider": provider_type,
            "is_local": router.is_local_provider(provider_enum),
            "is_cloud": router.is_cloud_provider(provider_enum),
            "optimizations": summary,
            "timestamp": time.time(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting provider optimization summary: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to get provider optimization summary",
        )
