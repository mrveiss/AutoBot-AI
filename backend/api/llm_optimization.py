"""
LLM Model Optimization API Endpoints
Provides intelligent model selection, performance tracking, and optimization suggestions.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config_helper import cfg
from src.constants.network_constants import NetworkConstants
from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.utils.model_optimizer import TaskComplexity, TaskRequest, get_model_optimizer

router = APIRouter()
logger = logging.getLogger(__name__)


class OptimizationRequest(BaseModel):
    """Model for optimization requests"""

    query: str
    task_type: str = "chat"
    max_response_time: Optional[float] = None
    min_quality: Optional[float] = None
    context_length: int = 0
    user_preference: Optional[str] = None


class ModelPerformanceData(BaseModel):
    """Model for tracking performance data"""

    model_name: str
    response_time: float
    response_tokens: int
    success: bool
    user_rating: Optional[float] = None


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_optimization_health",
    error_code_prefix="LLM_OPTIMIZATION",
)
@router.get("/health")
async def get_optimization_health():
    """Get model optimization system health status"""
    try:
        optimizer = get_model_optimizer()

        # Test basic functionality
        models = await optimizer.refresh_available_models()

        health_status = {
            "status": "healthy" if models else "degraded",
            "available_models": len(models),
            "cache_size": len(optimizer._models_cache),
            "ollama_connection": len(models) > 0,
            "redis_connected": optimizer._redis_client is not None,
        }

        return health_status

    except Exception as e:
        logger.error(f"Error checking optimization health: {e}")
        return JSONResponse(
            content={"status": "unhealthy", "error": str(e)}, status_code=500
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_available_models",
    error_code_prefix="LLM_OPTIMIZATION",
)
@router.get("/models/available")
async def get_available_models():
    """Get all available models with performance data"""
    try:
        optimizer = get_model_optimizer()
        models = await optimizer.refresh_available_models()

        models_data = []
        for model in models:
            model_data = {
                "name": model.name,
                "size_gb": model.size_gb,
                "parameter_size": model.parameter_size,
                "quantization": model.quantization,
                "family": model.family,
                "performance_level": model.performance_level.value,
                "avg_tokens_per_second": model.avg_tokens_per_second,
                "avg_response_time": model.avg_response_time,
                "success_rate": model.success_rate,
                "use_count": model.use_count,
                "last_used": model.last_used,
            }
            models_data.append(model_data)

        # Sort by performance level and success rate
        models_data.sort(key=lambda x: (x["performance_level"], -x["success_rate"]))

        return {
            "models_count": len(models_data),
            "models": models_data,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Error getting available models: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get available models: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="select_optimal_model",
    error_code_prefix="LLM_OPTIMIZATION",
)
@router.post("/models/select")
async def select_optimal_model(request: OptimizationRequest):
    """Select the optimal model for a given task"""
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

        # Get model details
        model_details = None
        if selected_model and selected_model in optimizer._models_cache:
            model = optimizer._models_cache[selected_model]
            model_details = {
                "name": model.name,
                "size_gb": model.size_gb,
                "parameter_size": model.parameter_size,
                "performance_level": model.performance_level.value,
                "avg_response_time": model.avg_response_time,
                "avg_tokens_per_second": model.avg_tokens_per_second,
                "success_rate": model.success_rate,
            }

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
                "selection_criteria": "Balanced for performance, quality, and resource efficiency",
            },
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Error selecting optimal model: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to select optimal model: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="track_model_performance",
    error_code_prefix="LLM_OPTIMIZATION",
)
@router.post("/models/performance/track")
async def track_model_performance(performance_data: ModelPerformanceData):
    """Track model performance for future optimization"""
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
        logger.error(f"Error tracking model performance: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to track performance: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_model_performance_history",
    error_code_prefix="LLM_OPTIMIZATION",
)
@router.get("/models/performance/history/{model_name}")
async def get_model_performance_history(model_name: str):
    """Get performance history for a specific model"""
    try:
        optimizer = get_model_optimizer()

        # Refresh models to get latest performance data
        await optimizer.refresh_available_models()

        if model_name not in optimizer._models_cache:
            raise HTTPException(
                status_code=404, detail=f"Model '{model_name}' not found"
            )

        model = optimizer._models_cache[model_name]

        performance_history = {
            "model_name": model.name,
            "current_metrics": {
                "avg_response_time": model.avg_response_time,
                "avg_tokens_per_second": model.avg_tokens_per_second,
                "success_rate": model.success_rate,
                "use_count": model.use_count,
                "last_used": model.last_used,
            },
            "model_info": {
                "size_gb": model.size_gb,
                "parameter_size": model.parameter_size,
                "quantization": model.quantization,
                "family": model.family,
                "performance_level": model.performance_level.value,
            },
            "efficiency_metrics": {
                "tokens_per_gb": model.avg_tokens_per_second / max(model.size_gb, 0.1),
                "response_efficiency": (
                    1.0 / max(model.avg_response_time, 0.1)
                    if model.avg_response_time > 0
                    else 0
                ),
                "overall_score": (
                    (
                        model.success_rate * 40
                        + min(model.avg_tokens_per_second / 10, 30)
                        + min(10 / max(model.avg_response_time, 0.1), 30)
                    )
                    if model.avg_response_time > 0
                    else model.success_rate * 40
                ),
            },
        }

        return performance_history

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model performance history: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get performance history: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_optimization_suggestions",
    error_code_prefix="LLM_OPTIMIZATION",
)
@router.get("/optimization/suggestions")
async def get_optimization_suggestions():
    """Get optimization suggestions based on usage patterns"""
    try:
        optimizer = get_model_optimizer()
        suggestions = await optimizer.get_optimization_suggestions()

        return {
            "suggestions_count": len(suggestions),
            "suggestions": suggestions,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Error getting optimization suggestions: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get optimization suggestions: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="compare_models",
    error_code_prefix="LLM_OPTIMIZATION",
)
@router.get("/models/comparison")
async def compare_models():
    """Compare all available models by performance metrics"""
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

        for model in models:
            model_data = {
                "name": model.name,
                "size_gb": model.size_gb,
                "parameter_size": model.parameter_size,
                "avg_response_time": model.avg_response_time,
                "avg_tokens_per_second": model.avg_tokens_per_second,
                "success_rate": model.success_rate,
                "use_count": model.use_count,
                "efficiency_score": (
                    (model.avg_tokens_per_second / max(model.size_gb, 0.1))
                    if model.size_gb > 0
                    else 0
                ),
                "performance_score": (
                    (
                        model.success_rate * 50
                        + min(model.avg_tokens_per_second / 5, 25)
                        + min(25 / max(model.avg_response_time, 0.1), 25)
                    )
                    if model.avg_response_time > 0
                    else model.success_rate * 50
                ),
            }

            level_key = model.performance_level.value
            if level_key in comparison_data:
                comparison_data[level_key].append(model_data)

        # Sort each category by performance score
        for level in comparison_data:
            comparison_data[level].sort(
                key=lambda x: x["performance_score"], reverse=True
            )

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
        logger.error(f"Error comparing models: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to compare models: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="benchmark_model",
    error_code_prefix="LLM_OPTIMIZATION",
)
@router.post("/models/benchmark/{model_name}")
async def benchmark_model(
    model_name: str, test_queries: List[str] = None, iterations: int = 3
):
    """Benchmark a specific model with test queries"""
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
            raise HTTPException(
                status_code=404, detail=f"Model '{model_name}' not found"
            )

        # Note: In a real implementation, you would actually call the model here
        # For now, we'll return a benchmark structure
        benchmark_results = {
            "model_name": model_name,
            "test_queries": test_queries,
            "iterations_per_query": iterations,
            "status": "benchmark_scheduled",
            "message": "Benchmark scheduled. In a real implementation, this would run the actual model tests.",
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
        logger.error(f"Error benchmarking model: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to benchmark model: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_resources",
    error_code_prefix="LLM_OPTIMIZATION",
)
@router.get("/system/resources")
async def get_system_resources():
    """Get current system resources for model optimization"""
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
                    "suggestion": "Consider using lighter models or reducing concurrent requests",
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
        logger.error(f"Error getting system resources: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get system resources: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_optimization_config",
    error_code_prefix="LLM_OPTIMIZATION",
)
@router.get("/config")
async def get_optimization_config():
    """Get current optimization configuration"""
    try:
        config = {
            "performance_threshold": cfg.get(
                "llm.optimization.performance_threshold", 0.8
            ),
            "cache_ttl": cfg.get("llm.optimization.cache_ttl", 3600),
            "min_samples": cfg.get("llm.optimization.min_samples", 5),
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

        return config

    except Exception as e:
        logger.error(f"Error getting optimization config: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get optimization config: {str(e)}"
        )
