# AutoBot BI Export Module
# Issue #59

from datetime import datetime
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from backend.services.analytics_service import get_analytics_service
from src.utils.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter(prefix="/bi", tags=["bi-export"])

class SavedReportRequest(BaseModel):
    name: str
    report_type: str = "executive"
    sections: List[str] = ["cost", "agents"]

@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="export_grafana", error_code_prefix="EXPORT")
@router.get("/export/grafana")
async def export_to_grafana():
    service = get_analytics_service()
    if hasattr(service, "export_to_grafana"):
        return await service.export_to_grafana()
    return {"format": "grafana", "status": "stub"}

@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="export_tableau", error_code_prefix="EXPORT")
@router.get("/export/tableau")
async def export_to_tableau():
    service = get_analytics_service()
    if hasattr(service, "export_to_tableau"):
        return await service.export_to_tableau()
    return {"format": "tableau", "status": "stub"}

@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="list_saved_reports", error_code_prefix="REPORT")
@router.get("/reports/saved")
async def list_saved_reports():
    service = get_analytics_service()
    if hasattr(service, "list_saved_reports"):
        return await service.list_saved_reports()
    return {"reports": []}


@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="export_csv", error_code_prefix="EXPORT")
@router.get("/export/csv")
async def export_to_csv(table: str = Query(default="all", description="Table to export")):
    service = get_analytics_service()
    if hasattr(service, "export_to_csv"):
        return await service.export_to_csv(table)
    return {"format": "csv", "table": table, "status": "stub"}

@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="get_saved_report", error_code_prefix="REPORT")
@router.get("/reports/saved/{report_id}")
async def get_saved_report(report_id: str):
    service = get_analytics_service()
    if hasattr(service, "get_saved_report"):
        return await service.get_saved_report(report_id)
    return {"report_id": report_id, "status": "not_found"}

@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="update_saved_report", error_code_prefix="REPORT")
@router.put("/reports/saved/{report_id}")
async def update_saved_report(report_id: str, request: SavedReportRequest):
    service = get_analytics_service()
    if hasattr(service, "update_saved_report"):
        return await service.update_saved_report(report_id=report_id, name=request.name, report_type=request.report_type, sections=request.sections)
    return {"report_id": report_id, "name": request.name, "status": "stub"}

@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="delete_saved_report", error_code_prefix="REPORT")
@router.delete("/reports/saved/{report_id}")
async def delete_saved_report(report_id: str):
    service = get_analytics_service()
    if hasattr(service, "delete_saved_report"):
        return await service.delete_saved_report(report_id)
    return {"report_id": report_id, "deleted": True}

@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="run_saved_report", error_code_prefix="REPORT")
@router.post("/reports/saved/{report_id}/run")
async def run_saved_report(report_id: str, days: int = Query(default=30, ge=1, le=365)):
    service = get_analytics_service()
    if hasattr(service, "run_saved_report"):
        return await service.run_saved_report(report_id, days)
    return {"report_id": report_id, "days": days, "status": "stub", "data": {}}
