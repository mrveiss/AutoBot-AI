# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
BI Saved Reports API — CRUD + run for saved analytics report configs.

Issue #1295: Persistence layer backed by Redis (ANALYTICS db).
Issue #1282: 3 redundant export stubs (grafana/tableau/csv) removed —
             already served by analytics_export.py.

Remaining endpoints:
  POST   /bi/reports/save                  — create a saved report
  GET    /bi/reports/saved                 — list all saved reports
  GET    /bi/reports/saved/{report_id}     — get one saved report
  PUT    /bi/reports/saved/{report_id}     — update a saved report
  DELETE /bi/reports/saved/{report_id}     — delete a saved report
  POST   /bi/reports/saved/{report_id}/run — execute a saved report
"""

from typing import List

from auth_middleware import check_admin_permission
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from services.saved_reports_service import get_saved_reports_service

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter(tags=["bi-reports"])


class SavedReportRequest(BaseModel):
    name: str
    report_type: str = "executive"
    sections: List[str] = ["cost", "agents"]


# =========================================================================
# CREATE
# =========================================================================


@router.post("/reports/save")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_report",
    error_code_prefix="REPORT",
)
async def save_report(
    request: SavedReportRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """Save a new configured report. Issue #1295."""
    svc = get_saved_reports_service()
    report = await svc.create_report(
        name=request.name,
        report_type=request.report_type,
        sections=request.sections,
    )
    return report


# =========================================================================
# LIST
# =========================================================================


@router.get("/reports/saved")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_saved_reports",
    error_code_prefix="REPORT",
)
async def list_saved_reports(
    admin_check: bool = Depends(check_admin_permission),
):
    """List all saved reports. Issue #1295."""
    svc = get_saved_reports_service()
    reports = await svc.list_reports()
    return {"reports": reports}


# =========================================================================
# GET
# =========================================================================


@router.get("/reports/saved/{report_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_saved_report",
    error_code_prefix="REPORT",
)
async def get_saved_report(
    report_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """Get a saved report by ID. Issue #1295."""
    svc = get_saved_reports_service()
    report = await svc.get_report(report_id)
    if report is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Report {report_id} not found"},
        )
    return report


# =========================================================================
# UPDATE
# =========================================================================


@router.put("/reports/saved/{report_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_saved_report",
    error_code_prefix="REPORT",
)
async def update_saved_report(
    report_id: str,
    request: SavedReportRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """Update a saved report. Issue #1295."""
    svc = get_saved_reports_service()
    report = await svc.update_report(
        report_id=report_id,
        name=request.name,
        report_type=request.report_type,
        sections=request.sections,
    )
    if report is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Report {report_id} not found"},
        )
    return report


# =========================================================================
# DELETE
# =========================================================================


@router.delete("/reports/saved/{report_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_saved_report",
    error_code_prefix="REPORT",
)
async def delete_saved_report(
    report_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """Delete a saved report. Issue #1295."""
    svc = get_saved_reports_service()
    existed = await svc.delete_report(report_id)
    if not existed:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Report {report_id} not found"},
        )
    return {"report_id": report_id, "deleted": True}


# =========================================================================
# RUN
# =========================================================================


@router.post("/reports/saved/{report_id}/run")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_saved_report",
    error_code_prefix="REPORT",
)
async def run_saved_report(
    report_id: str,
    days: int = Query(default=30, ge=1, le=365),
    admin_check: bool = Depends(check_admin_permission),
):
    """Run a saved report with live analytics data. Issue #1295."""
    svc = get_saved_reports_service()
    result = await svc.run_report(report_id, days)
    if result is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Report {report_id} not found"},
        )
    return result
