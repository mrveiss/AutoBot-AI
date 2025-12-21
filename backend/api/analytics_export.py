# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analytics Export API Module - BI tool export functionality.

Provides API endpoints for exporting analytics data to various formats:
- CSV (spreadsheet analysis)
- JSON (programmatic access)
- Prometheus metrics format (Grafana)
- Grafana dashboard JSON

Related Issues: #59 (Advanced Analytics & Business Intelligence)
Issue #379: Optimized sequential awaits with asyncio.gather for concurrent data collection.
"""

import asyncio
import csv
import io
import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse, Response

from backend.services.agent_analytics import get_agent_analytics
from backend.services.llm_cost_tracker import get_cost_tracker
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/export", tags=["analytics", "export"])


# ============================================================================
# CSV EXPORT ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_cost_csv",
    error_code_prefix="EXPORT",
)
@router.get("/csv/costs")
async def export_cost_csv(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to export"),
):
    """
    Export cost data as CSV.

    Returns daily cost data suitable for spreadsheet analysis.
    """
    tracker = get_cost_tracker()
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    summary = await tracker.get_cost_summary(start_date, end_date)
    daily_costs = summary.get("daily_costs", {})

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(["date", "cost_usd"])

    # Data rows
    for date in sorted(daily_costs):
        writer.writerow([date, daily_costs[date]])

    csv_content = output.getvalue()

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=autobot_costs_{days}d.csv"
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_agent_csv",
    error_code_prefix="EXPORT",
)
@router.get("/csv/agents")
async def export_agent_csv():
    """
    Export agent performance data as CSV.

    Returns agent metrics suitable for spreadsheet analysis.
    """
    analytics = get_agent_analytics()
    metrics_list = await analytics.get_all_agents_metrics()

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "agent_id",
        "agent_type",
        "total_tasks",
        "completed_tasks",
        "failed_tasks",
        "timeout_tasks",
        "success_rate_percent",
        "error_rate_percent",
        "avg_duration_ms",
        "total_tokens_used",
        "last_activity",
    ])

    # Data rows using model method (Issue #372 - reduces feature envy)
    for m in metrics_list:
        writer.writerow(m.to_csv_row())

    csv_content = output.getvalue()

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=autobot_agents.csv"
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_usage_csv",
    error_code_prefix="EXPORT",
)
@router.get("/csv/usage")
async def export_usage_csv(
    limit: int = Query(default=1000, ge=1, le=10000, description="Max records"),
):
    """
    Export LLM usage records as CSV.

    Returns individual API call records.
    """
    tracker = get_cost_tracker()
    records = await tracker.get_recent_usage(limit)

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "timestamp",
        "provider",
        "model",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "session_id",
        "success",
        "latency_ms",
    ])

    # Data rows
    for r in records:
        writer.writerow([
            r.get("timestamp", ""),
            r.get("provider", ""),
            r.get("model", ""),
            r.get("input_tokens", 0),
            r.get("output_tokens", 0),
            r.get("cost_usd", 0),
            r.get("session_id", ""),
            r.get("success", True),
            r.get("latency_ms", ""),
        ])

    csv_content = output.getvalue()

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=autobot_usage_{limit}.csv"
        },
    )


# ============================================================================
# JSON EXPORT ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_full_json",
    error_code_prefix="EXPORT",
)
@router.get("/json/full")
async def export_full_json(
    days: int = Query(default=30, ge=1, le=365, description="Number of days"),
):
    """
    Export complete analytics data as JSON.

    Returns comprehensive analytics export for programmatic processing.
    """
    tracker = get_cost_tracker()
    analytics = get_agent_analytics()

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Issue #379: Concurrent data collection with asyncio.gather
    cost_summary, cost_trends, agent_metrics, agent_comparison = await asyncio.gather(
        tracker.get_cost_summary(start_date, end_date),
        tracker.get_cost_trends(days),
        analytics.get_all_agents_metrics(),
        analytics.compare_agents(),
    )

    export_data = {
        "export_info": {
            "generated_at": datetime.utcnow().isoformat(),
            "period_days": days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "version": "1.0",
        },
        "cost_analytics": {
            "summary": cost_summary,
            "trends": cost_trends,
        },
        "agent_analytics": {
            "metrics": [m.to_dict() for m in agent_metrics],
            "comparison": agent_comparison,
        },
    }

    return Response(
        content=json.dumps(export_data, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=autobot_analytics_{days}d.json"
        },
    )


# ============================================================================
# PROMETHEUS FORMAT ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_prometheus",
    error_code_prefix="EXPORT",
)
@router.get("/prometheus")
async def export_prometheus():
    """
    Export metrics in Prometheus format.

    Returns metrics compatible with Prometheus/Grafana scraping.
    """
    tracker = get_cost_tracker()
    analytics = get_agent_analytics()

    # Issue #379: Concurrent data collection with asyncio.gather
    cost_summary, agent_metrics = await asyncio.gather(
        tracker.get_cost_summary(),
        analytics.get_all_agents_metrics(),
    )

    lines = []

    # Add header
    lines.append("# HELP autobot_llm_cost_total_usd Total LLM costs in USD")
    lines.append("# TYPE autobot_llm_cost_total_usd gauge")
    lines.append(f'autobot_llm_cost_total_usd {cost_summary.get("total_cost_usd", 0)}')

    lines.append("")
    lines.append("# HELP autobot_llm_daily_cost_usd Daily LLM cost in USD")
    lines.append("# TYPE autobot_llm_daily_cost_usd gauge")
    lines.append(f'autobot_llm_daily_cost_usd {cost_summary.get("avg_daily_cost", 0)}')

    # Model-specific costs
    lines.append("")
    lines.append("# HELP autobot_llm_model_cost_usd Cost by model in USD")
    lines.append("# TYPE autobot_llm_model_cost_usd gauge")
    for model, data in cost_summary.get("by_model", {}).items():
        cost = data.get("cost_usd", 0)
        lines.append(f'autobot_llm_model_cost_usd{{model="{model}"}} {cost}')

    lines.append("")
    lines.append("# HELP autobot_llm_model_tokens Token usage by model")
    lines.append("# TYPE autobot_llm_model_tokens counter")
    for model, data in cost_summary.get("by_model", {}).items():
        input_tokens = data.get("input_tokens", 0)
        output_tokens = data.get("output_tokens", 0)
        lines.append(f'autobot_llm_model_tokens{{model="{model}",type="input"}} {input_tokens}')
        lines.append(f'autobot_llm_model_tokens{{model="{model}",type="output"}} {output_tokens}')

    # Agent metrics using model methods (Issue #372 - reduces feature envy)
    lines.append("")
    lines.append("# HELP autobot_agent_tasks_total Total tasks by agent")
    lines.append("# TYPE autobot_agent_tasks_total counter")
    for m in agent_metrics:
        lines.append(m.to_prometheus_tasks_line())

    lines.append("")
    lines.append("# HELP autobot_agent_success_rate Agent success rate percentage")
    lines.append("# TYPE autobot_agent_success_rate gauge")
    for m in agent_metrics:
        lines.append(m.to_prometheus_success_rate_line())

    lines.append("")
    lines.append("# HELP autobot_agent_error_rate Agent error rate percentage")
    lines.append("# TYPE autobot_agent_error_rate gauge")
    for m in agent_metrics:
        lines.append(m.to_prometheus_error_rate_line())

    lines.append("")
    lines.append("# HELP autobot_agent_avg_duration_ms Average task duration in ms")
    lines.append("# TYPE autobot_agent_avg_duration_ms gauge")
    for m in agent_metrics:
        lines.append(m.to_prometheus_duration_line())

    prometheus_output = "\n".join(lines) + "\n"

    return PlainTextResponse(
        content=prometheus_output,
        media_type="text/plain; version=0.0.4",
    )


# ============================================================================
# GRAFANA DASHBOARD EXPORT
# ============================================================================


def _get_cost_panels() -> list:
    """Return Grafana panels for cost metrics. Issue #484: Extracted from _get_grafana_panels."""
    return [
        {
            "id": 1,
            "title": "LLM Cost Overview",
            "type": "stat",
            "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
            "targets": [{"expr": "autobot_llm_cost_total_usd", "legendFormat": "Total Cost (USD)"}],
            "options": {"colorMode": "value", "graphMode": "area", "justifyMode": "auto"},
        },
        {
            "id": 2,
            "title": "Daily Cost Average",
            "type": "stat",
            "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
            "targets": [{"expr": "autobot_llm_daily_cost_usd", "legendFormat": "Avg Daily Cost (USD)"}],
        },
        {
            "id": 3,
            "title": "Cost by Model",
            "type": "piechart",
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
            "targets": [{"expr": "autobot_llm_model_cost_usd", "legendFormat": "{{model}}"}],
        },
    ]


def _get_agent_panels() -> list:
    """Return Grafana panels for agent metrics. Issue #484: Extracted from _get_grafana_panels."""
    return [
        {
            "id": 4,
            "title": "Agent Success Rates",
            "type": "bargauge",
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 4},
            "targets": [{"expr": "autobot_agent_success_rate", "legendFormat": "{{agent_id}}"}],
            "options": {"orientation": "horizontal", "displayMode": "gradient"},
            "fieldConfig": {"defaults": {"max": 100, "min": 0, "unit": "percent"}},
        },
        {
            "id": 6,
            "title": "Agent Task Duration",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 20},
            "targets": [{"expr": "autobot_agent_avg_duration_ms", "legendFormat": "{{agent_id}}"}],
            "fieldConfig": {"defaults": {"unit": "ms"}},
        },
        {
            "id": 7,
            "title": "Agent Error Rates",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 20},
            "targets": [{"expr": "autobot_agent_error_rate", "legendFormat": "{{agent_id}}"}],
            "fieldConfig": {
                "defaults": {
                    "unit": "percent",
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "yellow", "value": 5},
                            {"color": "red", "value": 15},
                        ],
                    },
                }
            },
        },
    ]


def _get_token_usage_panel() -> dict:
    """Return Grafana panel for token usage timeline. Issue #484: Extracted from _get_grafana_panels."""
    return {
        "id": 5,
        "title": "Token Usage Over Time",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": 12},
        "targets": [
            {"expr": 'rate(autobot_llm_model_tokens{type="input"}[5m])', "legendFormat": "{{model}} - Input"},
            {"expr": 'rate(autobot_llm_model_tokens{type="output"}[5m])', "legendFormat": "{{model}} - Output"},
        ],
    }


def _get_grafana_panels() -> list:
    """
    Return Grafana dashboard panel configurations.

    Issue #281: Extracted from export_grafana_dashboard to reduce function length.
    Issue #484: Further refactored into category-specific helpers for maintainability.

    Returns:
        List of panel configuration dictionaries for Grafana dashboard.
    """
    panels = []
    panels.extend(_get_cost_panels())
    panels.extend(_get_agent_panels())
    panels.append(_get_token_usage_panel())
    return panels


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_grafana_dashboard",
    error_code_prefix="EXPORT",
)
@router.get("/grafana-dashboard")
async def export_grafana_dashboard():
    """
    Export a Grafana dashboard JSON.

    Returns a pre-configured dashboard for AutoBot analytics.

    Issue #281: Panel configurations extracted to _get_grafana_panels()
    to reduce function length from 166 to ~30 lines.
    """
    # Issue #281: Use extracted helper for panel configurations
    dashboard = {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 0,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": _get_grafana_panels(),
        "refresh": "30s",
        "schemaVersion": 38,
        "style": "dark",
        "tags": ["autobot", "analytics", "llm"],
        "templating": {"list": []},
        "time": {"from": "now-24h", "to": "now"},
        "timepicker": {},
        "timezone": "browser",
        "title": "AutoBot Analytics Dashboard",
        "uid": "autobot-analytics",
        "version": 1,
        "weekStart": "",
    }

    return Response(
        content=json.dumps(dashboard, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": "attachment; filename=autobot_grafana_dashboard.json"
        },
    )


# ============================================================================
# EXPORT SUMMARY ENDPOINT
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_export_formats",
    error_code_prefix="EXPORT",
)
@router.get("/formats")
async def get_export_formats():
    """
    Get available export formats and endpoints.

    Returns documentation for all export options.
    """
    return {
        "formats": [
            {
                "format": "CSV",
                "description": "Comma-separated values for spreadsheet analysis",
                "endpoints": [
                    {"path": "/export/csv/costs", "description": "Daily cost data"},
                    {"path": "/export/csv/agents", "description": "Agent performance metrics"},
                    {"path": "/export/csv/usage", "description": "Individual LLM usage records"},
                ],
            },
            {
                "format": "JSON",
                "description": "Full analytics export for programmatic access",
                "endpoints": [
                    {"path": "/export/json/full", "description": "Complete analytics export"},
                ],
            },
            {
                "format": "Prometheus",
                "description": "Metrics in Prometheus exposition format",
                "endpoints": [
                    {"path": "/export/prometheus", "description": "Prometheus-compatible metrics"},
                ],
            },
            {
                "format": "Grafana",
                "description": "Pre-configured Grafana dashboard",
                "endpoints": [
                    {"path": "/export/grafana-dashboard", "description": "Grafana dashboard JSON"},
                ],
            },
        ],
        "notes": [
            "CSV exports include headers and are ready for import into Excel/Sheets",
            "JSON exports include metadata about the export period",
            "Prometheus endpoint can be scraped directly by Prometheus server",
            "Grafana dashboard can be imported via Grafana's import feature",
        ],
    }
