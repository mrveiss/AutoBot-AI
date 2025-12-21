# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Validation Dashboard API for AutoBot
Provides endpoints for real-time validation dashboard and reports
"""

import logging
import os

# Import the dashboard generator
import sys
from datetime import datetime
from typing import Optional

from backend.type_defs.common import Metadata

import aiofiles
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from src.utils.catalog_http_exceptions import (
    raise_not_found_error,
    raise_server_error,
    raise_service_unavailable,
    raise_validation_error,
)
from src.utils.error_boundaries import ErrorCategory, with_error_handling

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from scripts.validation_dashboard_generator import ValidationDashboardGenerator
except ImportError as e:
    ValidationDashboardGenerator = None
    import_error = str(e)

# Import LLM judges for validation enhancement
try:
    from src.judges.agent_response_judge import AgentResponseJudge
    from src.judges.workflow_step_judge import WorkflowStepJudge

    VALIDATION_JUDGES_AVAILABLE = True
except ImportError:
    VALIDATION_JUDGES_AVAILABLE = False

router = APIRouter()
logger = logging.getLogger(__name__)

# Thread-safe global singletons
import threading

# Global dashboard generator instance
_dashboard_generator = None
_dashboard_generator_lock = threading.Lock()

# Global validation judges
_validation_judges = None
_validation_judges_lock = threading.Lock()

# Issue #461: Removed mock fallback data constants (FALLBACK_PHASE_DETAILS,
# FALLBACK_RECOMMENDATIONS, FALLBACK_SYSTEM_OVERVIEW) and generate_fallback_report().
# Validation dashboard now returns proper error responses when generator unavailable.


def _try_create_dashboard_generator() -> Optional[ValidationDashboardGenerator]:
    """Try to create dashboard generator, return None on failure. (Issue #315 - extracted)"""
    try:
        generator = ValidationDashboardGenerator()
        logger.info("Dashboard generator initialized")
        return generator
    except ImportError as e:
        logger.error("Failed to initialize dashboard generator due to import error: %s", e)
    except (OSError, IOError) as e:
        logger.error("Failed to initialize dashboard generator due to file system error: %s", e)
    except Exception as e:
        logger.error("Failed to initialize dashboard generator due to unexpected error: %s", e)
    return None


def get_dashboard_generator() -> Optional[ValidationDashboardGenerator]:
    """Get or create dashboard generator instance (thread-safe)"""
    global _dashboard_generator

    if ValidationDashboardGenerator is None:
        logger.error("ValidationDashboardGenerator not available: %s", import_error)
        return None

    if _dashboard_generator is None:
        with _dashboard_generator_lock:
            # Double-check after acquiring lock
            if _dashboard_generator is None:
                _dashboard_generator = _try_create_dashboard_generator()

    return _dashboard_generator


def _try_create_validation_judges() -> Optional[Metadata]:
    """Try to create validation judges, return None on failure. (Issue #315 - extracted)"""
    try:
        judges = {
            "workflow_step_judge": WorkflowStepJudge(),
            "agent_response_judge": AgentResponseJudge(),
        }
        logger.info("Validation judges initialized")
        return judges
    except ImportError as e:
        logger.error("Failed to initialize validation judges due to import error: %s", e)
    except Exception as e:
        logger.error("Failed to initialize validation judges due to unexpected error: %s", e)
    return None


def get_validation_judges() -> Optional[Metadata]:
    """Get or create validation judges instance (thread-safe)"""
    global _validation_judges

    if not VALIDATION_JUDGES_AVAILABLE:
        logger.warning("Validation judges not available")
        return None

    if _validation_judges is None:
        with _validation_judges_lock:
            # Double-check after acquiring lock
            if _validation_judges is None:
                _validation_judges = _try_create_validation_judges()

    return _validation_judges


class DashboardGenerateRequest(BaseModel):
    include_trends: bool = True
    include_recommendations: bool = True
    refresh_interval: int = 30  # seconds


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dashboard_status",
    error_code_prefix="VALIDATION_DASHBOARD",
)
@router.get("/status")
async def get_dashboard_status():
    """Get validation dashboard service status"""
    generator = get_dashboard_generator()

    if generator is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "service": "validation_dashboard",
                "error": "Dashboard generator not available",
                "timestamp": datetime.now().isoformat(),
            },
        )

    try:
        return {
            "status": "healthy",
            "service": "validation_dashboard",
            "output_directory": str(generator.output_dir),
            "refresh_interval": generator.refresh_interval,
            "data_retention_days": generator.data_retention_days,
            "timestamp": datetime.now().isoformat(),
        }
    except (ImportError, AttributeError) as e:
        logger.error("Error getting dashboard status due to missing dependency: %s", e)
        raise_service_unavailable("API_0005", "Dashboard generator not available")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_validation_report",
    error_code_prefix="VALIDATION_DASHBOARD",
)
@router.get("/report")
async def get_validation_report():
    """Get current validation report data.

    Issue #461: Returns proper error response when generator unavailable
    instead of fallback mock data.
    """
    generator = get_dashboard_generator()

    if generator is None:
        # Issue #461: Return proper error instead of mock data
        logger.warning("Validation dashboard generator not available")
        raise_service_unavailable(
            "API_0005",
            "Validation dashboard generator not available. "
            "Check system configuration and ensure ValidationDashboardGenerator is properly installed.",
        )

    try:
        # Generate real-time report
        report = await generator.generate_real_time_report()

        return {
            "status": "success",
            "report": report,
            "timestamp": datetime.now().isoformat(),
        }

    except (ImportError, AttributeError) as e:
        logger.error(
            f"Error generating validation report due to missing dependency: {e}"
        )
        raise_service_unavailable(
            "API_0005",
            f"Dashboard generator dependency error: {e}",
        )
    except (OSError, IOError) as e:
        logger.error(
            f"Error generating validation report due to file system error: {e}"
        )
        raise_server_error(
            "API_0003",
            f"File system error generating validation report: {e}",
        )
    except Exception as e:
        logger.error("Error generating validation report: %s", e)
        raise_server_error(
            "API_0004",
            f"Unexpected error generating validation report: {e}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dashboard_html",
    error_code_prefix="VALIDATION_DASHBOARD",
)
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard_html():
    """Get HTML validation dashboard"""
    generator = get_dashboard_generator()

    if generator is None:
        return HTMLResponse(
            content="""
                <html><body>
                    <h1>Validation Dashboard Unavailable</h1>
                    <p>The validation dashboard generator is not available.</p>
                    <p>Please check the system configuration.</p>
                </body></html>
                """,
            status_code=503,
        )

    try:
        # Generate dashboard
        dashboard_path = await generator.generate_html_dashboard()

        # Read and return HTML content - PERFORMANCE FIX: Convert to async file I/O
        async with aiofiles.open(dashboard_path, "r") as f:
            html_content = await f.read()

        return HTMLResponse(content=html_content)

    except (ImportError, AttributeError) as e:
        logger.error("Error generating dashboard HTML due to missing dependency: %s", e)
        return HTMLResponse(
            content=f"""
            <html><body>
                <h1>Dashboard Error</h1>
                <p>Service unavailable: Dashboard generator not available</p>
                <p>Error: {e}</p>
            </body></html>
            """,
            status_code=503,
        )
    except (OSError, IOError) as e:
        logger.error("Error generating dashboard HTML due to file system error: %s", e)
        return HTMLResponse(
            content=f"""
            <html><body>
                <h1>Dashboard Error</h1>
                <p>File system error occurred during dashboard generation</p>
                <p>Error: {e}</p>
            </body></html>
            """,
            status_code=500,
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dashboard_file",
    error_code_prefix="VALIDATION_DASHBOARD",
)
@router.get("/dashboard/file")
async def get_dashboard_file():
    """Get dashboard HTML file for download"""
    generator = get_dashboard_generator()

    if generator is None:
        raise_service_unavailable(
            "API_0005", "Validation dashboard generator not available"
        )

    try:
        # Generate dashboard
        dashboard_path = await generator.generate_html_dashboard()

        return FileResponse(
            path=dashboard_path,
            filename="autobot_validation_dashboard.html",
            media_type="text/html",
        )

    except FileNotFoundError as e:
        logger.error("Dashboard file not found: %s", e)
        raise_not_found_error("API_0002", "Dashboard file not found")
    except (OSError, IOError) as e:
        logger.error("Error serving dashboard file due to file system error: %s", e)
        raise_server_error("API_0003", "File system error")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="generate_dashboard",
    error_code_prefix="VALIDATION_DASHBOARD",
)
@router.post("/generate")
async def generate_dashboard(
    request: DashboardGenerateRequest, background_tasks: BackgroundTasks
):
    """Generate validation dashboard with custom settings"""
    try:
        generator = get_dashboard_generator()

        if generator is None:
            raise_service_unavailable(
                "API_0005", "Validation dashboard generator not available"
            )

        # Update generator settings
        generator.refresh_interval = request.refresh_interval

        # Generate dashboard in background if requested
        async def generate_background():
            """Generate validation dashboard HTML file asynchronously."""
            try:
                dashboard_path = await generator.generate_html_dashboard()
                logger.info(
                    f"Background dashboard generation completed: {dashboard_path}"
                )
            except (ImportError, AttributeError) as e:
                logger.error(
                    "Background dashboard generation failed due to "
                    f"missing dependency: {e}"
                )
            except (OSError, IOError) as e:
                logger.error(
                    "Background dashboard generation failed due to "
                    f"file system error: {e}"
                )
            except Exception as e:
                logger.error("Background dashboard generation failed: %s", e)

        background_tasks.add_task(generate_background)

        return {
            "status": "initiated",
            "message": "Dashboard generation started in background",
            "settings": {
                "refresh_interval": request.refresh_interval,
                "include_trends": request.include_trends,
                "include_recommendations": request.include_recommendations,
            },
            "timestamp": datetime.now().isoformat(),
        }

    except (ImportError, AttributeError) as e:
        logger.error(
            f"Error initiating dashboard generation due to missing dependency: {e}"
        )
        raise_service_unavailable("API_0005", "Dashboard generator not available")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dashboard_metrics",
    error_code_prefix="VALIDATION_DASHBOARD",
)
@router.get("/metrics")
async def get_dashboard_metrics():
    """Get dashboard-specific metrics"""
    generator = get_dashboard_generator()

    if generator is None:
        raise_service_unavailable(
            "API_0005", "Validation dashboard generator not available"
        )

    try:
        # Get basic metrics
        report = await generator.generate_real_time_report()

        metrics = {
            "system_overview": report["system_overview"],
            "current_metrics": report["metrics"],
            "alert_count": len(report["alerts"]),
            "recommendation_count": len(report["recommendations"]),
            "phase_summary": {
                "total_phases": len(report["phase_details"]),
                "completed_phases": len(
                    [
                        p
                        for p in report["phase_details"]
                        if p["completion_percentage"] >= 95.0
                    ]
                ),
                "phases_in_progress": len(
                    [
                        p
                        for p in report["phase_details"]
                        if 50.0 <= p["completion_percentage"] < 95.0
                    ]
                ),
                "phases_not_started": len(
                    [
                        p
                        for p in report["phase_details"]
                        if p["completion_percentage"] < 50.0
                    ]
                ),
            },
        }

        return {
            "status": "success",
            "metrics": metrics,
            "timestamp": datetime.now().isoformat(),
        }

    except (ImportError, AttributeError) as e:
        logger.error("Error getting dashboard metrics due to missing dependency: %s", e)
        raise_service_unavailable("API_0005", "Dashboard generator not available")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_trend_data",
    error_code_prefix="VALIDATION_DASHBOARD",
)
@router.get("/trends")
async def get_trend_data():
    """Get trend data for charts"""
    generator = get_dashboard_generator()

    if generator is None:
        raise_service_unavailable(
            "API_0005", "Validation dashboard generator not available"
        )

    try:
        # Get trend data
        trend_data = await generator._generate_trend_data()

        return {
            "status": "success",
            "trends": trend_data,
            "timestamp": datetime.now().isoformat(),
        }

    except (ImportError, AttributeError) as e:
        logger.error("Error getting trend data due to missing dependency: %s", e)
        raise_service_unavailable("API_0005", "Dashboard generator not available")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_alerts",
    error_code_prefix="VALIDATION_DASHBOARD",
)
@router.get("/alerts")
async def get_system_alerts():
    """Get current system alerts"""
    generator = get_dashboard_generator()

    if generator is None:
        raise_service_unavailable(
            "API_0005", "Validation dashboard generator not available"
        )

    try:
        # Get current report
        report = await generator.generate_real_time_report()

        return {
            "status": "success",
            "alerts": report["alerts"],
            "alert_counts": {
                "critical": len(
                    [a for a in report["alerts"] if a["level"] == "critical"]
                ),
                "warning": len(
                    [a for a in report["alerts"] if a["level"] == "warning"]
                ),
                "info": len([a for a in report["alerts"] if a["level"] == "info"]),
            },
            "timestamp": datetime.now().isoformat(),
        }

    except (ImportError, AttributeError) as e:
        logger.error("Error getting system alerts due to missing dependency: %s", e)
        raise_service_unavailable("API_0005", "Dashboard generator not available")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_recommendations",
    error_code_prefix="VALIDATION_DASHBOARD",
)
@router.get("/recommendations")
async def get_system_recommendations():
    """Get current system recommendations"""
    generator = get_dashboard_generator()

    if generator is None:
        raise_service_unavailable(
            "API_0005", "Validation dashboard generator not available"
        )

    try:
        # Get current report
        report = await generator.generate_real_time_report()

        return {
            "status": "success",
            "recommendations": report["recommendations"],
            "recommendation_counts": {
                "high": len(
                    [r for r in report["recommendations"] if r["urgency"] == "high"]
                ),
                "medium": len(
                    [r for r in report["recommendations"] if r["urgency"] == "medium"]
                ),
                "low": len(
                    [r for r in report["recommendations"] if r["urgency"] == "low"]
                ),
            },
            "timestamp": datetime.now().isoformat(),
        }

    except (ImportError, AttributeError) as e:
        logger.error(
            f"Error getting system recommendations due to missing dependency: {e}"
        )
        raise_service_unavailable("API_0005", "Dashboard generator not available")


# Health check moved to consolidated health service
# See backend/services/consolidated_health_service.py
# Use /api/system/health?detailed=true for comprehensive status


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="judge_workflow_step",
    error_code_prefix="VALIDATION_DASHBOARD",
)
@router.post("/judge_workflow_step")
async def judge_workflow_step(request: dict):
    """Use LLM judges to evaluate a workflow step"""
    try:
        judges = get_validation_judges()

        if judges is None:
            raise_service_unavailable("API_0005", "Validation judges not available")

        step_data = request.get("step_data", {})
        workflow_context = request.get("workflow_context", {})
        user_context = request.get("user_context", {})

        if not step_data:
            raise_validation_error("API_0001", "step_data is required")

        # Evaluate with workflow step judge
        workflow_judge = judges["workflow_step_judge"]
        judgment = await workflow_judge.evaluate_workflow_step(
            step_data, workflow_context, user_context
        )

        return {
            "status": "success",
            "judgment": {
                "overall_score": judgment.overall_score,
                "recommendation": judgment.recommendation,
                "confidence": judgment.confidence.value,
                "reasoning": judgment.reasoning,
                "criterion_scores": [
                    {
                        "dimension": score.dimension.value,
                        "score": score.score,
                        "confidence": score.confidence.value,
                        "reasoning": score.reasoning,
                        "evidence": score.evidence,
                    }
                    for score in judgment.criterion_scores
                ],
                "improvement_suggestions": judgment.improvement_suggestions,
            },
            "timestamp": datetime.now().isoformat(),
        }

    except (ImportError, AttributeError) as e:
        logger.error("Error in workflow step judgment due to missing dependency: %s", e)
        raise_service_unavailable("API_0005", "Validation judges not available")
    except ValueError as e:
        logger.error("Error in workflow step judgment due to invalid input: %s", e)
        raise_validation_error("API_0001", "Invalid workflow step data")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="judge_agent_response",
    error_code_prefix="VALIDATION_DASHBOARD",
)
@router.post("/judge_agent_response")
async def judge_agent_response(request: dict):
    """Use LLM judges to evaluate an agent response"""
    judges = get_validation_judges()

    if judges is None:
        raise_service_unavailable("API_0005", "Validation judges not available")

    user_request = request.get("request", {})
    response = request.get("response", {})
    agent_type = request.get("agent_type", "unknown")
    context = request.get("context", {})

    if not response:
        raise_validation_error("API_0001", "response is required")

    try:
        # Evaluate with agent response judge
        response_judge = judges["agent_response_judge"]
        judgment = await response_judge.evaluate_agent_response(
            user_request, response, agent_type, context
        )

        return {
            "status": "success",
            "judgment": {
                "overall_score": judgment.overall_score,
                "recommendation": judgment.recommendation,
                "confidence": judgment.confidence.value,
                "reasoning": judgment.reasoning,
                "criterion_scores": [
                    {
                        "dimension": score.dimension.value,
                        "score": score.score,
                        "confidence": score.confidence.value,
                        "reasoning": score.reasoning,
                        "evidence": score.evidence,
                    }
                    for score in judgment.criterion_scores
                ],
                "improvement_suggestions": judgment.improvement_suggestions,
            },
            "timestamp": datetime.now().isoformat(),
        }

    except (ImportError, AttributeError) as e:
        logger.error("Error in agent response judgment due to missing dependency: %s", e)
        raise_service_unavailable("API_0005", "Validation judges not available")
    except ValueError as e:
        logger.error("Error in agent response judgment due to invalid input: %s", e)
        raise_validation_error("API_0001", "Invalid agent response data")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_judge_status",
    error_code_prefix="VALIDATION_DASHBOARD",
)
@router.get("/judge_status")
async def get_judge_status():
    """Get status of validation judges"""
    judges = get_validation_judges()

    if judges is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "service": "validation_judges",
                "error": "Judges not available",
                "timestamp": datetime.now().isoformat(),
            },
        )

    # Get performance metrics for judges
    judge_metrics = {}
    for judge_name, judge in judges.items():
        try:
            metrics = judge.get_performance_metrics()
            judge_metrics[judge_name] = metrics
        except (ImportError, AttributeError) as e:
            logger.error(
                f"Error getting metrics for {judge_name} due to "
                f"missing dependency: {e}"
            )
            judge_metrics[judge_name] = {
                "error": "Judge not available",
                "details": str(e),
            }
        except Exception as e:
            logger.error("Error getting metrics for %s: %s", judge_name, e)
            judge_metrics[judge_name] = {"error": str(e)}

    return {
        "status": "healthy",
        "service": "validation_judges",
        "available_judges": list(judges.keys()),
        "judge_metrics": judge_metrics,
        "timestamp": datetime.now().isoformat(),
    }
