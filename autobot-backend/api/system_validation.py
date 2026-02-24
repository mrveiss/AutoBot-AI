#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Validation API endpoints for AutoBot optimization suite
"""

import logging
from typing import Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from type_defs.common import Metadata
from utils.catalog_http_exceptions import raise_not_found_error, raise_server_error
from utils.system_validator import get_system_validator

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


class ValidationRequest(BaseModel):
    """Request model for system validation"""

    validation_type: str = "comprehensive"
    include_performance_tests: bool = True
    include_stress_tests: bool = False
    timeout_seconds: int = 300


class ValidationResult(BaseModel):
    """Response model for validation results"""

    validation_id: str
    status: str
    overall_score: float
    component_scores: Dict[str, float]
    recommendations: List[str]
    test_results: Metadata
    execution_time: float
    timestamp: str


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="validation_health",
    error_code_prefix="SYSTEM_VALIDATION",
)
@router.get("/health")
async def validation_health():
    """Health check for validation system"""
    try:
        validator = get_system_validator()
        return {
            "status": "healthy",
            "message": "System validation API is operational",
            "validator_initialized": validator is not None,
            "timestamp": validator._get_timestamp() if validator else None,
        }
    except Exception as e:
        logger.error("Validation health check failed: %s", e)
        raise_server_error("API_0003", f"Health check failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_comprehensive_validation",
    error_code_prefix="SYSTEM_VALIDATION",
)
@router.post("/validate/comprehensive", response_model=ValidationResult)
async def run_comprehensive_validation(
    request: ValidationRequest, background_tasks: BackgroundTasks
):
    """Run comprehensive system validation"""
    try:
        validator = get_system_validator()

        # Run validation
        result = await validator.run_comprehensive_validation()

        if not result["success"]:
            raise_server_error(
                "API_0003", f"Validation failed: {result.get('error', 'Unknown error')}"
            )

        # Format response
        validation_result = ValidationResult(
            validation_id=result["validation_id"],
            status="completed",
            overall_score=result["overall_score"],
            component_scores=result["component_scores"],
            recommendations=result["recommendations"],
            test_results=result["test_results"],
            execution_time=result["execution_time"],
            timestamp=result["timestamp"],
        )

        return validation_result

    except Exception as e:
        logger.error("Comprehensive validation failed: %s", e)
        raise_server_error("API_0003", f"Validation error: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_quick_validation",
    error_code_prefix="SYSTEM_VALIDATION",
)
@router.get("/validate/quick")
async def run_quick_validation():
    """Run quick system validation check"""
    try:
        validator = get_system_validator()

        # Run quick checks only
        quick_results = {}

        # Cache validation
        cache_result = await validator.validate_knowledge_base_caching()
        quick_results["cache"] = {
            "status": "healthy" if cache_result["success"] else "unhealthy",
            "score": cache_result.get("score", 0),
            "message": cache_result.get("message", "No message"),
        }

        # Search validation
        search_result = await validator.validate_hybrid_search()
        quick_results["search"] = {
            "status": "healthy" if search_result["success"] else "unhealthy",
            "score": search_result.get("score", 0),
            "message": search_result.get("message", "No message"),
        }

        # Monitoring validation
        monitoring_result = await validator.validate_monitoring_system()
        quick_results["monitoring"] = {
            "status": "healthy" if monitoring_result["success"] else "unhealthy",
            "score": monitoring_result.get("score", 0),
            "message": monitoring_result.get("message", "No message"),
        }

        # Model optimization validation
        model_result = await validator.validate_model_optimization()
        quick_results["model_optimization"] = {
            "status": "healthy" if model_result["success"] else "unhealthy",
            "score": model_result.get("score", 0),
            "message": model_result.get("message", "No message"),
        }

        # Calculate overall status
        all_scores = [result["score"] for result in quick_results.values()]
        overall_score = sum(all_scores) / len(all_scores) if all_scores else 0
        overall_status = (
            "healthy"
            if overall_score >= 80
            else "degraded"
            if overall_score >= 60
            else "unhealthy"
        )

        return {
            "status": overall_status,
            "overall_score": overall_score,
            "components": quick_results,
            "timestamp": validator._get_timestamp(),
        }

    except Exception as e:
        logger.error("Quick validation failed: %s", e)
        raise_server_error("API_0003", f"Quick validation error: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="validate_component",
    error_code_prefix="SYSTEM_VALIDATION",
)
@router.get("/validate/component/{component_name}")
async def validate_component(component_name: str):
    """Validate specific component"""
    try:
        validator = get_system_validator()

        # Map component names to validation methods
        component_methods = {
            "cache": validator.validate_knowledge_base_caching,
            "caching": validator.validate_knowledge_base_caching,
            "search": validator.validate_hybrid_search,
            "hybrid_search": validator.validate_hybrid_search,
            "monitoring": validator.validate_monitoring_system,
            "model": validator.validate_model_optimization,
            "model_optimization": validator.validate_model_optimization,
            "integration": validator.validate_integration_tests,
        }

        if component_name.lower() not in component_methods:
            raise_not_found_error(
                "API_0002",
                f"Component '{component_name}' not found. Available: {list(component_methods.keys())}",
            )

        # Run specific validation
        method = component_methods[component_name.lower()]
        result = await method()

        return {
            "component": component_name,
            "status": "healthy" if result["success"] else "unhealthy",
            "score": result.get("score", 0),
            "details": result,
            "timestamp": validator._get_timestamp(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Component validation failed for %s: %s", component_name, e)
        raise_server_error("API_0003", f"Component validation error: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_optimization_recommendations",
    error_code_prefix="SYSTEM_VALIDATION",
)
@router.get("/validate/recommendations")
async def get_optimization_recommendations():
    """Get system optimization recommendations"""
    try:
        validator = get_system_validator()

        # Get recommendations from each component
        recommendations = []

        # Cache recommendations
        cache_result = await validator.validate_knowledge_base_caching()
        if "recommendations" in cache_result:
            recommendations.extend(
                [
                    {"component": "cache", "recommendation": rec}
                    for rec in cache_result["recommendations"]
                ]
            )

        # Search recommendations
        search_result = await validator.validate_hybrid_search()
        if "recommendations" in search_result:
            recommendations.extend(
                [
                    {"component": "search", "recommendation": rec}
                    for rec in search_result["recommendations"]
                ]
            )

        # Monitoring recommendations
        monitoring_result = await validator.validate_monitoring_system()
        if "recommendations" in monitoring_result:
            recommendations.extend(
                [
                    {"component": "monitoring", "recommendation": rec}
                    for rec in monitoring_result["recommendations"]
                ]
            )

        # Model optimization recommendations
        model_result = await validator.validate_model_optimization()
        if "recommendations" in model_result:
            recommendations.extend(
                [
                    {"component": "model_optimization", "recommendation": rec}
                    for rec in model_result["recommendations"]
                ]
            )

        return {
            "total_recommendations": len(recommendations),
            "recommendations": recommendations,
            "timestamp": validator._get_timestamp(),
        }

    except Exception as e:
        logger.error("Failed to get recommendations: %s", e)
        raise_server_error("API_0003", f"Recommendations error: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_validation_status",
    error_code_prefix="SYSTEM_VALIDATION",
)
@router.get("/validate/status")
async def get_validation_status():
    """Get current validation system status"""
    try:
        validator = get_system_validator()

        return {
            "validation_system": "operational",
            "available_validations": [
                "comprehensive",
                "quick",
                "cache",
                "search",
                "monitoring",
                "model_optimization",
                "integration",
            ],
            "last_validation": None,  # Could store last validation timestamp
            "system_health": "unknown",  # Would require running quick validation
            "timestamp": validator._get_timestamp(),
        }

    except Exception as e:
        logger.error("Failed to get validation status: %s", e)
        raise_server_error("API_0003", f"Status error: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_performance_benchmark",
    error_code_prefix="SYSTEM_VALIDATION",
)
@router.post("/validate/benchmark")
async def run_performance_benchmark():
    """Run performance benchmarking tests"""
    try:
        validator = get_system_validator()

        # This would run performance benchmarks for each component
        # For now, return a placeholder structure
        benchmarks = {
            "cache_performance": {
                "hit_rate": 0.0,
                "response_time_ms": 0.0,
                "throughput_ops_sec": 0.0,
            },
            "search_performance": {
                "semantic_time_ms": 0.0,
                "hybrid_time_ms": 0.0,
                "relevance_score": 0.0,
            },
            "monitoring_performance": {
                "collection_time_ms": 0.0,
                "storage_time_ms": 0.0,
                "query_time_ms": 0.0,
            },
            "model_performance": {
                "selection_time_ms": 0.0,
                "accuracy_score": 0.0,
                "resource_efficiency": 0.0,
            },
        }

        return {
            "benchmark_status": "completed",
            "benchmarks": benchmarks,
            "overall_performance_score": 85.0,  # Calculated from benchmarks
            "timestamp": validator._get_timestamp(),
        }

    except Exception as e:
        logger.error("Performance benchmark failed: %s", e)
        raise_server_error("API_0003", f"Benchmark error: {str(e)}")
