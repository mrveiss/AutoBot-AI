# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Usage Metering API — token counts, resource usage, and billing-ready metrics.

Provides endpoints for:
- Per-user usage summary (tokens, cost, request counts)
- System-wide aggregated usage
- Daily/model/session breakdowns
- Usage data export (CSV)

Issue #1807: Usage metering and cost tracking.
"""

import csv
import io
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api.schemas_analytics import (
    UsageByUserAllResponse,
    UsageByUserSingleResponse,
    UsageMyUsageResponse,
    UsageRecordEndpointRequest,
    UsageSummaryResponse,
)
from api.schemas_common import UsageRecordResponse
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc, utc_timestamp
from services.llm_cost_tracker import get_cost_tracker

logger = get_logger(__name__)
router = APIRouter(prefix="/usage", tags=["usage", "analytics"])


# ============================================================================
# SUMMARY ENDPOINTS
# ============================================================================


@router.get("/summary", response_model=UsageSummaryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_usage_summary",
    error_code_prefix="USAGE",
)
async def get_usage_summary(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to include"),
    admin_check: bool = Depends(check_admin_permission),
) -> dict[str, Any]:
    """
    Get system-wide usage summary: tokens, costs, model breakdown.

    Returns aggregate token counts and costs across all users and models
    for the specified time period.

    Issue #1807: Billing-ready usage metrics.
    """
    tracker = get_cost_tracker()
    end_date = now_utc()
    start_date = end_date - timedelta(days=days)

    cost_summary = await tracker.get_cost_summary(start_date, end_date)
    all_users = await tracker.get_all_user_costs()

    total_input = sum(u["input_tokens"] for u in all_users)
    total_output = sum(u["output_tokens"] for u in all_users)
    total_requests = sum(u["call_count"] for u in all_users)

    return {
        "period": {
            "days": days,
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        },
        "tokens": {
            "input": total_input,
            "output": total_output,
            "total": total_input + total_output,
        },
        "cost_usd": cost_summary.get("total_cost_usd", 0.0),
        "requests": total_requests,
        "daily_costs": cost_summary.get("daily_costs", {}),
        "by_model": cost_summary.get("by_model", {}),
        "active_users": len(all_users),
    }


@router.get("/by-user", response_model=UsageByUserAllResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_usage_by_user_all",
    error_code_prefix="USAGE",
)
async def get_usage_by_user_all(
    admin_check: bool = Depends(check_admin_permission),
) -> dict[str, Any]:
    """
    Get usage breakdown for all users, sorted by cost descending.

    Issue #1807: Per-user billing metrics.
    """
    tracker = get_cost_tracker()
    users = await tracker.get_all_user_costs()

    return {
        "timestamp": utc_timestamp(),
        "users": users,
        "total_users": len(users),
    }


@router.get("/by-user/{user_id}", response_model=UsageByUserSingleResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_usage_by_user_single",
    error_code_prefix="USAGE",
)
async def get_usage_by_user_single(
    user_id: str,
    admin_check: bool = Depends(check_admin_permission),
) -> dict[str, Any]:
    """
    Get usage breakdown for a specific user.

    Issue #1807: Per-user billing metrics.
    """
    tracker = get_cost_tracker()
    return await tracker.get_cost_by_user(user_id)


@router.get("/me", response_model=UsageMyUsageResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_my_usage",
    error_code_prefix="USAGE",
)
async def get_my_usage(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Get the authenticated user's personal usage summary.

    Returns token counts, cost, and request history for the caller.

    Issue #1807: Personal usage dashboard data.
    """
    tracker = get_cost_tracker()
    user_id: str = current_user.get("username", "")
    if not user_id:
        return {"found": False, "message": "User identity not available"}

    data = await tracker.get_cost_by_user(user_id)

    # Enrich with recent usage records filtered to this user
    recent = await tracker.get_recent_usage(limit=200)
    user_recent = [r for r in recent if r.get("user_id") == user_id][:50]

    return {
        **data,
        "recent_requests": user_recent,
    }


# ============================================================================
# RECORD ENDPOINT
# ============================================================================


@router.post("/record", response_model=UsageRecordResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="record_usage_event",
    error_code_prefix="USAGE",
)
async def record_usage_event(
    body: UsageRecordEndpointRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Record a single LLM usage event.

    Called from LLM handlers after each API call to track tokens and cost.
    The user_id in the body is used if provided; otherwise falls back to the
    authenticated user's username.

    Issue #1807: Billing-ready usage event ingestion.
    """
    tracker = get_cost_tracker()
    user_id = body.user_id or current_user.get("username", "")
    record = await tracker.track_usage(
        provider=body.provider,
        model=body.model,
        input_tokens=body.input_tokens,
        output_tokens=body.output_tokens,
        session_id=body.session_id,
        user_id=user_id,
        agent_id=body.agent_id,
        latency_ms=body.latency_ms,
        success=body.success,
    )
    return {
        "recorded": True,
        "cost_usd": record.cost_usd,
        "record_id": record.id if hasattr(record, "id") else None,
    }


# ============================================================================
# EXPORT ENDPOINT
# ============================================================================


@router.get("/export/csv", response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_usage_csv",
    error_code_prefix="USAGE",
)
async def export_usage_csv(
    days: int = Query(default=30, ge=1, le=365, description="Days of data to export"),
    admin_check: bool = Depends(check_admin_permission),
) -> StreamingResponse:
    """
    Export usage data as CSV.

    Downloads a CSV file containing all usage records for the given period.
    Columns: timestamp, provider, model, user_id, session_id, input_tokens,
             output_tokens, cost_usd, latency_ms, success.

    Issue #1807: CSV export for billing/reporting.
    """
    tracker = get_cost_tracker()
    cutoff = now_utc() - timedelta(days=days)

    records = await tracker.get_recent_usage(limit=10000)
    filtered = [r for r in records if r.get("timestamp", "") >= cutoff.strftime("%Y-%m-%dT")]

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "timestamp",
            "provider",
            "model",
            "user_id",
            "session_id",
            "agent_id",
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "latency_ms",
            "success",
        ],
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in filtered:
        writer.writerow(row)

    output.seek(0)
    filename = f"usage_{now_utc().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
