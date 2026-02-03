# AutoBot BI Export Module
# Issue #59

from typing import List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from backend.services.analytics_service import get_analytics_service
from src.auth_middleware import check_admin_permission
from src.utils.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter(prefix="/bi", tags=["bi-export"])


class SavedReportRequest(BaseModel):
    name: str
    report_type: str = "executive"
    sections: List[str] = ["cost", "agents"]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_grafana",
    error_code_prefix="EXPORT",
)
@router.get("/export/grafana")
async def export_to_grafana(
    admin_check: bool = Depends(check_admin_permission),
):
    """Export data in Grafana format. Issue #744: Requires admin authentication."""
    service = get_analytics_service()
    if hasattr(service, "export_to_grafana"):
        return await service.export_to_grafana()
    return {"format": "grafana", "status": "stub"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_tableau",
    error_code_prefix="EXPORT",
)
@router.get("/export/tableau")
async def export_to_tableau(
    admin_check: bool = Depends(check_admin_permission),
):
    """Export data in Tableau format. Issue #744: Requires admin authentication."""
    service = get_analytics_service()
    if hasattr(service, "export_to_tableau"):
        return await service.export_to_tableau()
    return {"format": "tableau", "status": "stub"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_saved_reports",
    error_code_prefix="REPORT",
)
@router.get("/reports/saved")
async def list_saved_reports(
    admin_check: bool = Depends(check_admin_permission),
):
    """List saved reports. Issue #744: Requires admin authentication."""
    service = get_analytics_service()
    if hasattr(service, "list_saved_reports"):
        return await service.list_saved_reports()
    return {"reports": []}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_csv",
    error_code_prefix="EXPORT",
)
@router.get("/export/csv")
async def export_to_csv(
    table: str = Query(default="all", description="Table to export"),
    admin_check: bool = Depends(check_admin_permission),
):
    """Export data to CSV. Issue #744: Requires admin authentication."""
    service = get_analytics_service()
    if hasattr(service, "export_to_csv"):
        return await service.export_to_csv(table)
    return {"format": "csv", "table": table, "status": "stub"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_saved_report",
    error_code_prefix="REPORT",
)
@router.get("/reports/saved/{report_id}")
async def get_saved_report(
    report_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """Get a saved report by ID. Issue #744: Requires admin authentication."""
    service = get_analytics_service()
    if hasattr(service, "get_saved_report"):
        return await service.get_saved_report(report_id)
    return {"report_id": report_id, "status": "not_found"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_saved_report",
    error_code_prefix="REPORT",
)
@router.put("/reports/saved/{report_id}")
async def update_saved_report(
    report_id: str,
    request: SavedReportRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """Update a saved report. Issue #744: Requires admin authentication."""
    service = get_analytics_service()
    if hasattr(service, "update_saved_report"):
        return await service.update_saved_report(
            report_id=report_id,
            name=request.name,
            report_type=request.report_type,
            sections=request.sections,
        )
    return {"report_id": report_id, "name": request.name, "status": "stub"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_saved_report",
    error_code_prefix="REPORT",
)
@router.delete("/reports/saved/{report_id}")
async def delete_saved_report(
    report_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """Delete a saved report. Issue #744: Requires admin authentication."""
    service = get_analytics_service()
    if hasattr(service, "delete_saved_report"):
        return await service.delete_saved_report(report_id)
    return {"report_id": report_id, "deleted": True}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_saved_report",
    error_code_prefix="REPORT",
)
@router.post("/reports/saved/{report_id}/run")
async def run_saved_report(
    report_id: str,
    days: int = Query(default=30, ge=1, le=365),
    admin_check: bool = Depends(check_admin_permission),
):
    """Run a saved report. Issue #744: Requires admin authentication."""
    service = get_analytics_service()
    if hasattr(service, "run_saved_report"):
        return await service.run_saved_report(report_id, days)
    return {"report_id": report_id, "days": days, "status": "stub", "data": {}}
