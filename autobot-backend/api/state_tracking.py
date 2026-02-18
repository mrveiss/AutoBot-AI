# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
State Tracking API for AutoBot
Provides endpoints for comprehensive project state tracking and reporting
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from backend.type_defs.common import Metadata
from enhanced_project_state_tracker import (
    StateChangeType,
    TrackingMetric,
    get_state_tracker,
)
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)


class StateChangeRequest(BaseModel):
    change_type: str
    description: str
    after_state: Metadata
    before_state: Optional[Metadata] = None
    user_id: Optional[str] = "system"
    metadata: Optional[Metadata] = None


class ExportRequest(BaseModel):
    format: str = "json"  # json or markdown
    include_history: bool = True
    time_range_days: Optional[int] = None


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_state_tracking_status",
    error_code_prefix="STATE",
)
@router.get("/status")
async def get_state_tracking_status():
    """Get overall state tracking system status"""
    try:
        tracker = get_state_tracker()

        # Get latest summary
        summary = await tracker.get_state_summary()

        return {
            "status": "healthy",
            "service": "state_tracking",
            "timestamp": datetime.now().isoformat(),
            "tracking_active": True,
            "snapshot_count": summary["snapshot_count"],
            "change_count": summary["change_count"],
            "latest_snapshot": (
                summary["current_state"]["validation_results"]
                if summary["current_state"]
                else None
            ),
        }
    except (ImportError, AttributeError) as e:
        logger.error(
            f"Error getting state tracking status due to missing dependency: {e}"
        )
        raise HTTPException(status_code=503, detail="State tracker not available")
    except Exception as e:
        logger.error("Error getting state tracking status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_state_summary",
    error_code_prefix="STATE",
)
@router.get("/summary")
async def get_state_summary():
    """Get comprehensive state summary"""
    try:
        tracker = get_state_tracker()
        summary = await tracker.get_state_summary()

        return {
            "status": "success",
            "summary": summary,
            "timestamp": datetime.now().isoformat(),
        }
    except (ImportError, AttributeError) as e:
        logger.error("Error getting state summary due to missing dependency: %s", e)
        raise HTTPException(status_code=503, detail="State tracker not available")
    except Exception as e:
        logger.error("Error getting state summary: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="capture_state_snapshot",
    error_code_prefix="STATE",
)
@router.post("/snapshot")
async def capture_state_snapshot(background_tasks: BackgroundTasks):
    """Manually trigger a state snapshot"""
    try:
        tracker = get_state_tracker()

        # Run snapshot in background
        async def capture_snapshot():
            """Capture and log state snapshot asynchronously."""
            snapshot = await tracker.capture_state_snapshot()
            logger.info("State snapshot captured at %s", snapshot.timestamp)

        background_tasks.add_task(capture_snapshot)

        return {
            "status": "success",
            "message": "State snapshot capture initiated",
            "timestamp": datetime.now().isoformat(),
        }
    except (ImportError, AttributeError) as e:
        logger.error("Error capturing snapshot due to missing dependency: %s", e)
        raise HTTPException(status_code=503, detail="State tracker not available")
    except Exception as e:
        logger.error("Error capturing snapshot: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="record_state_change",
    error_code_prefix="STATE",
)
@router.post("/change")
async def record_state_change(request: StateChangeRequest):
    """Record a state change event"""
    try:
        tracker = get_state_tracker()

        # Convert string to enum
        try:
            change_type = StateChangeType(request.change_type)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": f"Invalid change type: {request.change_type}",
                    "valid_types": [t.value for t in StateChangeType],
                },
            )

        # Record the change
        await tracker.record_state_change(
            change_type=change_type,
            description=request.description,
            after_state=request.after_state,
            before_state=request.before_state,
            user_id=request.user_id,
            metadata=request.metadata,
        )

        return {
            "status": "success",
            "message": "State change recorded",
            "change_type": change_type.value,
            "timestamp": datetime.now().isoformat(),
        }
    except (ImportError, AttributeError) as e:
        logger.error("Error recording state change due to missing dependency: %s", e)
        raise HTTPException(status_code=503, detail="State tracker not available")
    except ValueError as e:
        logger.error("Error recording state change due to invalid input: %s", e)
        raise HTTPException(status_code=400, detail="Invalid state change data")
    except Exception as e:
        logger.error("Error recording state change: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_milestones",
    error_code_prefix="STATE",
)
@router.get("/milestones")
async def get_milestones():
    """Get project milestone status"""
    try:
        tracker = get_state_tracker()
        summary = await tracker.get_state_summary()

        return {
            "status": "success",
            "milestones": summary["milestones"],
            "achieved_count": sum(
                1 for m in summary["milestones"].values() if m["achieved"]
            ),
            "total_count": len(summary["milestones"]),
            "timestamp": datetime.now().isoformat(),
        }
    except (ImportError, AttributeError) as e:
        logger.error("Error getting milestones due to missing dependency: %s", e)
        raise HTTPException(status_code=503, detail="State tracker not available")
    except Exception as e:
        logger.error("Error getting milestones: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_metric_trends",
    error_code_prefix="STATE",
)
@router.get("/trends/{metric}")
async def get_metric_trends(metric: str, days: int = Query(7, ge=1, le=90)):
    """Get trend data for a specific metric"""
    try:
        tracker = get_state_tracker()

        # Validate metric
        try:
            metric_enum = TrackingMetric(metric)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": f"Invalid metric: {metric}",
                    "valid_metrics": [m.value for m in TrackingMetric],
                },
            )

        # Get historical data
        cutoff_date = datetime.now() - timedelta(days=days)

        # Filter snapshots within time range
        relevant_snapshots = [
            s for s in tracker.state_history if s.timestamp >= cutoff_date
        ]

        # Extract metric values
        trend_data = []
        for snapshot in relevant_snapshots:
            if metric_enum in snapshot.system_metrics:
                trend_data.append(
                    {
                        "timestamp": snapshot.timestamp.isoformat(),
                        "value": snapshot.system_metrics[metric_enum],
                    }
                )

        return {
            "status": "success",
            "metric": metric,
            "days": days,
            "data_points": len(trend_data),
            "trend_data": trend_data,
            "timestamp": datetime.now().isoformat(),
        }
    except (ImportError, AttributeError) as e:
        logger.error("Error getting metric trends due to missing dependency: %s", e)
        raise HTTPException(status_code=503, detail="State tracker not available")
    except Exception as e:
        logger.error("Error getting metric trends: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_recent_changes",
    error_code_prefix="STATE",
)
@router.get("/changes")
async def get_recent_changes(
    limit: int = Query(10, ge=1, le=100), change_type: Optional[str] = None
):
    """Get recent state changes"""
    try:
        tracker = get_state_tracker()

        # Filter changes
        changes = tracker.change_log
        if change_type:
            try:
                change_type_enum = StateChangeType(change_type)
                changes = [c for c in changes if c.change_type == change_type_enum]
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": f"Invalid change type: {change_type}",
                        "valid_types": [t.value for t in StateChangeType],
                    },
                )

        # Get recent changes
        recent_changes = changes[-limit:]

        return {
            "status": "success",
            "changes": [
                {
                    "timestamp": change.timestamp.isoformat(),
                    "type": change.change_type.value,
                    "description": change.description,
                    "user_id": change.user_id,
                    "has_before_state": change.before_state is not None,
                    "metadata": change.metadata,
                }
                for change in recent_changes
            ],
            "total_changes": len(changes),
            "showing": len(recent_changes),
            "timestamp": datetime.now().isoformat(),
        }
    except (ImportError, AttributeError) as e:
        logger.error("Error getting recent changes due to missing dependency: %s", e)
        raise HTTPException(status_code=503, detail="State tracker not available")
    except Exception as e:
        logger.error("Error getting recent changes: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="generate_state_report",
    error_code_prefix="STATE",
)
@router.get("/report")
async def generate_state_report():
    """Generate comprehensive state tracking report"""
    try:
        tracker = get_state_tracker()
        report = await tracker.generate_state_report()

        return {
            "status": "success",
            "report": report,
            "format": "markdown",
            "timestamp": datetime.now().isoformat(),
        }
    except (ImportError, AttributeError) as e:
        logger.error("Error generating report due to missing dependency: %s", e)
        raise HTTPException(status_code=503, detail="State tracker not available")
    except (OSError, IOError) as e:
        logger.error("Error generating report due to file system error: %s", e)
        raise HTTPException(
            status_code=500, detail="File system error during report generation"
        )
    except Exception as e:
        logger.error("Error generating report: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_state_data",
    error_code_prefix="STATE",
)
@router.post("/export")
async def export_state_data(request: ExportRequest):
    """Export state tracking data"""
    try:
        tracker = get_state_tracker()

        # Generate filename using centralized path management
        from backend.utils.paths_manager import ensure_data_directory, get_data_path

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"state_tracking_export_{timestamp}.{request.format}"

        # Ensure data directory and reports subdirectory exist
        ensure_data_directory()
        reports_dir = get_data_path("reports/state_tracking")
        # Issue #358 - avoid blocking
        await asyncio.to_thread(reports_dir.mkdir, parents=True, exist_ok=True)

        output_path = str(reports_dir / filename)

        # Export data
        await tracker.export_state_data(output_path, format=request.format)

        return {
            "status": "success",
            "message": "State data exported",
            "filename": filename,
            "path": output_path,
            "format": request.format,
            "timestamp": datetime.now().isoformat(),
        }
    except (ImportError, AttributeError) as e:
        logger.error("Error exporting state data due to missing dependency: %s", e)
        raise HTTPException(status_code=503, detail="State tracker not available")
    except ValueError as e:
        logger.error("Error exporting state data due to invalid format: %s", e)
        raise HTTPException(status_code=400, detail="Invalid export format")
    except (OSError, IOError) as e:
        logger.error("Error exporting state data due to file system error: %s", e)
        raise HTTPException(status_code=500, detail="File system error during export")
    except Exception as e:
        logger.error("Error exporting state data: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# Health check moved to consolidated health service
# See backend/services/consolidated_health_service.py
# Use /api/system/health?detailed=true for comprehensive status


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_all_metrics",
    error_code_prefix="STATE",
)
@router.get("/metrics/all")
async def get_all_metrics():
    """Get current values for all tracking metrics"""
    try:
        tracker = get_state_tracker()
        summary = await tracker.get_state_summary()

        metrics = summary["current_state"]["system_metrics"]

        return {
            "status": "success",
            "metrics": metrics,
            "available_metrics": [m.value for m in TrackingMetric],
            "timestamp": datetime.now().isoformat(),
        }
    except (ImportError, AttributeError) as e:
        logger.error("Error getting all metrics due to missing dependency: %s", e)
        raise HTTPException(status_code=503, detail="State tracker not available")
    except Exception as e:
        logger.error("Error getting all metrics: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_phase_history",
    error_code_prefix="STATE",
)
@router.get("/phase-history/{phase_name}")
async def get_phase_history(phase_name: str, days: int = Query(30, ge=1, le=365)):
    """Get historical data for a specific phase"""
    try:
        tracker = get_state_tracker()

        # Get historical data
        cutoff_date = datetime.now() - timedelta(days=days)

        phase_history = []
        for snapshot in tracker.state_history:
            if (
                snapshot.timestamp >= cutoff_date
                and phase_name in snapshot.phase_states
            ):
                phase_data = snapshot.phase_states[phase_name]
                phase_history.append(
                    {
                        "timestamp": snapshot.timestamp.isoformat(),
                        "completion_percentage": phase_data["completion_percentage"],
                        "status": phase_data["status"],
                    }
                )

        return {
            "status": "success",
            "phase_name": phase_name,
            "days": days,
            "data_points": len(phase_history),
            "history": phase_history,
            "timestamp": datetime.now().isoformat(),
        }
    except (ImportError, AttributeError) as e:
        logger.error("Error getting phase history due to missing dependency: %s", e)
        raise HTTPException(status_code=503, detail="State tracker not available")
    except Exception as e:
        logger.error("Error getting phase history: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
