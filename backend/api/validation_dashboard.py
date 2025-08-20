"""
Validation Dashboard API for AutoBot
Provides endpoints for real-time validation dashboard and reports
"""

import logging
import os
import aiofiles

# Import the dashboard generator
import sys
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from scripts.validation_dashboard_generator import ValidationDashboardGenerator
except ImportError as e:
    ValidationDashboardGenerator = None
    import_error = str(e)

router = APIRouter()
logger = logging.getLogger(__name__)

# Global dashboard generator instance
_dashboard_generator = None


def get_dashboard_generator() -> Optional[ValidationDashboardGenerator]:
    """Get or create dashboard generator instance"""
    global _dashboard_generator

    if ValidationDashboardGenerator is None:
        logger.error(f"ValidationDashboardGenerator not available: {import_error}")
        return None

    if _dashboard_generator is None:
        try:
            _dashboard_generator = ValidationDashboardGenerator()
            logger.info("Dashboard generator initialized")
        except Exception as e:
            logger.error(f"Failed to initialize dashboard generator: {e}")
            return None

    return _dashboard_generator


class DashboardGenerateRequest(BaseModel):
    include_trends: bool = True
    include_recommendations: bool = True
    refresh_interval: int = 30  # seconds


@router.get("/status")
async def get_dashboard_status():
    """Get validation dashboard service status"""
    try:
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

        return {
            "status": "healthy",
            "service": "validation_dashboard",
            "output_directory": str(generator.output_dir),
            "refresh_interval": generator.refresh_interval,
            "data_retention_days": generator.data_retention_days,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting dashboard status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report")
async def get_validation_report():
    """Get current validation report data"""
    try:
        generator = get_dashboard_generator()

        if generator is None:
            raise HTTPException(
                status_code=503, detail="Validation dashboard generator not available"
            )

        # Generate real-time report
        report = await generator.generate_real_time_report()

        return {
            "status": "success",
            "report": report,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error generating validation report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard_html():
    """Get HTML validation dashboard"""
    try:
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

        # Generate dashboard
        dashboard_path = await generator.generate_html_dashboard()

        # Read and return HTML content - PERFORMANCE FIX: Convert to async file I/O
        async with aiofiles.open(dashboard_path, "r") as f:
            html_content = await f.read()

        return HTMLResponse(content=html_content)

    except Exception as e:
        logger.error(f"Error generating dashboard HTML: {e}")
        return HTMLResponse(
            content=f"""
            <html><body>
                <h1>Dashboard Error</h1>
                <p>Error generating validation dashboard: {str(e)}</p>
            </body></html>
            """,
            status_code=500,
        )


@router.get("/dashboard/file")
async def get_dashboard_file():
    """Get dashboard HTML file for download"""
    try:
        generator = get_dashboard_generator()

        if generator is None:
            raise HTTPException(
                status_code=503, detail="Validation dashboard generator not available"
            )

        # Generate dashboard
        dashboard_path = await generator.generate_html_dashboard()

        return FileResponse(
            path=dashboard_path,
            filename="autobot_validation_dashboard.html",
            media_type="text/html",
        )

    except Exception as e:
        logger.error(f"Error serving dashboard file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def generate_dashboard(
    request: DashboardGenerateRequest, background_tasks: BackgroundTasks
):
    """Generate validation dashboard with custom settings"""
    try:
        generator = get_dashboard_generator()

        if generator is None:
            raise HTTPException(
                status_code=503, detail="Validation dashboard generator not available"
            )

        # Update generator settings
        generator.refresh_interval = request.refresh_interval

        # Generate dashboard in background if requested
        async def generate_background():
            try:
                dashboard_path = await generator.generate_html_dashboard()
                logger.info(
                    f"Background dashboard generation completed: {dashboard_path}"
                )
            except Exception as e:
                logger.error(f"Background dashboard generation failed: {e}")

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

    except Exception as e:
        logger.error(f"Error initiating dashboard generation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
async def get_dashboard_metrics():
    """Get dashboard-specific metrics"""
    try:
        generator = get_dashboard_generator()

        if generator is None:
            raise HTTPException(
                status_code=503, detail="Validation dashboard generator not available"
            )

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

    except Exception as e:
        logger.error(f"Error getting dashboard metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trends")
async def get_trend_data():
    """Get trend data for charts"""
    try:
        generator = get_dashboard_generator()

        if generator is None:
            raise HTTPException(
                status_code=503, detail="Validation dashboard generator not available"
            )

        # Get trend data
        trend_data = await generator._generate_trend_data()

        return {
            "status": "success",
            "trends": trend_data,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting trend data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_system_alerts():
    """Get current system alerts"""
    try:
        generator = get_dashboard_generator()

        if generator is None:
            raise HTTPException(
                status_code=503, detail="Validation dashboard generator not available"
            )

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

    except Exception as e:
        logger.error(f"Error getting system alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommendations")
async def get_system_recommendations():
    """Get current system recommendations"""
    try:
        generator = get_dashboard_generator()

        if generator is None:
            raise HTTPException(
                status_code=503, detail="Validation dashboard generator not available"
            )

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

    except Exception as e:
        logger.error(f"Error getting system recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def validation_dashboard_health():
    """Health check for validation dashboard"""
    try:
        generator = get_dashboard_generator()

        if generator is None:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "service": "validation_dashboard",
                    "error": "Generator not available",
                    "timestamp": datetime.now().isoformat(),
                },
            )

        # Test basic functionality
        try:
            await generator.generate_real_time_report()
            report_generation_ok = True
        except Exception as e:
            logger.error(f"Report generation test failed: {e}")
            report_generation_ok = False

        health_checks = {
            "generator_initialized": generator is not None,
            "output_directory_exists": generator.output_dir.exists(),
            "output_directory_writable": os.access(generator.output_dir, os.W_OK),
            "report_generation": report_generation_ok,
        }

        overall_healthy = all(health_checks.values())

        return {
            "status": "healthy" if overall_healthy else "degraded",
            "service": "validation_dashboard",
            "components": health_checks,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Validation dashboard health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")
