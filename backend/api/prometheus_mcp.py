# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Prometheus MCP Bridge
Exposes Prometheus metrics as MCP tools for AutoBot's LLM agents
Provides agents access to system monitoring data and metrics queries
"""

import logging
from typing import List

import aiohttp
from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.type_defs.common import Metadata
from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.utils.http_client import get_http_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["prometheus_mcp", "mcp", "monitoring"])

# Prometheus configuration
PROMETHEUS_URL = "http://172.16.168.23:9090"


class MCPTool(BaseModel):
    """Standard MCP tool definition"""

    name: str
    description: str
    input_schema: Metadata


class QueryMetricRequest(BaseModel):
    """Request model for Prometheus metric query"""

    query: str = Field(..., description="PromQL query expression")


class QueryRangeRequest(BaseModel):
    """Request model for Prometheus range query"""

    query: str = Field(..., description="PromQL query expression")
    duration: str = Field("1h", description="Time duration (e.g., '1h', '6h', '1d')")
    step: str = Field("15s", description="Query resolution step (e.g., '15s', '1m')")


class GetVMMetricsRequest(BaseModel):
    """Request model for VM metrics"""

    vm_ip: str = Field(..., description="VM IP address (e.g., '172.16.168.21')")


class ListMetricsRequest(BaseModel):
    """Request model for listing metrics"""

    filter: str = Field("", description="Optional filter pattern (e.g., 'autobot_', 'node_')")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_prometheus_mcp_tools",
    error_code_prefix="PROMETHEUS_MCP",
)
@router.get("/mcp/tools")
async def get_prometheus_mcp_tools() -> List[MCPTool]:
    """
    Get available MCP tools for Prometheus metrics

    These tools allow AutoBot's LLM agents to:
    - Query current metrics values
    - Query metrics over time ranges
    - Get system-wide metrics for all VMs
    - Check service health status
    - Get detailed metrics for specific VMs
    - List available metrics
    """
    tools = [
        MCPTool(
            name="query_metric",
            description=(
                "Query current value of a Prometheus metric using PromQL. "
                "Use this to get instant metric values like CPU usage, memory usage, load average."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "PromQL query expression (e.g., 'autobot_cpu_usage_percent', 'node_load1')",
                    }
                },
                "required": ["query"],
            },
        ),
        MCPTool(
            name="query_range",
            description=(
                "Query metric values over a time range. Returns time-series data showing "
                "how metrics changed over the specified duration."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "PromQL query expression",
                    },
                    "duration": {
                        "type": "string",
                        "description": "Time duration (e.g., '1h', '6h', '1d')",
                        "default": "1h",
                    },
                    "step": {
                        "type": "string",
                        "description": "Query resolution step (e.g., '15s', '1m')",
                        "default": "15s",
                    },
                },
                "required": ["query"],
            },
        ),
        MCPTool(
            name="get_system_metrics",
            description=(
                "Get current system metrics for all machines (CPU, memory, load). "
                "Provides a summary of resource usage across all VMs."
            ),
            input_schema={
                "type": "object",
                "properties": {},
            },
        ),
        MCPTool(
            name="get_service_health",
            description=(
                "Get health status of all AutoBot services and node exporters. "
                "Shows which services are UP or DOWN."
            ),
            input_schema={
                "type": "object",
                "properties": {},
            },
        ),
        MCPTool(
            name="get_vm_metrics",
            description=(
                "Get detailed metrics for a specific VM including CPU, memory, disk, and load. "
                "Use this when you need comprehensive information about one machine."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "vm_ip": {
                        "type": "string",
                        "description": "VM IP address (e.g., '172.16.168.21')",
                    }
                },
                "required": ["vm_ip"],
            },
        ),
        MCPTool(
            name="list_available_metrics",
            description=(
                "List all available Prometheus metrics with optional filtering. "
                "Use this to discover what metrics are available to query."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Optional filter pattern (e.g., 'autobot_', 'node_')",
                        "default": "",
                    }
                },
            },
        ),
    ]

    return tools


async def prometheus_query(query: str) -> Metadata:
    """Execute instant Prometheus query."""
    try:
        http_client = get_http_client()
        params = {"query": query}
        async with await http_client.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params=params,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status != 200:
                return None
            data = await response.json()
            if data.get("status") != "success":
                return None
            return data.get("data", {})
    except Exception as e:
        logger.error(f"Prometheus query failed: {e}")
        return None


# Tool handler functions (Issue #315 - extracted to reduce nesting)
async def _handle_query_metric(request: Metadata) -> Metadata:
    """Handle query_metric tool."""
    query = request.get("query", "")
    data = await prometheus_query(query)

    if not data or not data.get("result"):
        return {"status": "error", "error": f"No data found for query: {query}"}

    results = []
    for result in data["result"]:
        metric = result["metric"]
        value = result["value"][1]
        labels = ", ".join([f"{k}={v}" for k, v in metric.items() if k != "__name__"])
        metric_name = metric.get("__name__", query)
        results.append(f"{metric_name}{{{labels}}}: {value}")

    return {"status": "success", "result": f"Query: {query}\n\nResults:\n" + "\n".join(results)}


def _build_vm_metrics(load_data: Metadata, cpu_data: Metadata, memory_data: Metadata) -> dict:
    """Build VM metrics dictionary from query results (Issue #315 - extracted)."""
    vms = {}
    for result in load_data.get("result", []):
        instance = result["metric"]["instance"]
        vms[instance] = {"load": float(result["value"][1])}

    for result in cpu_data.get("result", []) if cpu_data else []:
        instance = result["metric"]["instance"]
        if instance in vms:
            vms[instance]["cpu"] = float(result["value"][1])

    for result in memory_data.get("result", []) if memory_data else []:
        instance = result["metric"]["instance"]
        if instance in vms:
            vms[instance]["memory"] = float(result["value"][1])

    return vms


async def _handle_get_system_metrics(_request: Metadata) -> Metadata:
    """Handle get_system_metrics tool."""
    load_data = await prometheus_query("node_load1")
    cpu_data = await prometheus_query(
        "100 - (avg by (instance) (rate(node_cpu_seconds_total{mode='idle'}[5m])) * 100)"
    )
    memory_data = await prometheus_query(
        "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100"
    )

    if not load_data or not load_data.get("result"):
        return {"status": "error", "error": "No system metrics available. Node exporters may not be running."}

    vms = _build_vm_metrics(load_data, cpu_data, memory_data)
    output = "System Metrics (All Machines)\n" + "=" * 50 + "\n\n"

    for instance, metrics in sorted(vms.items()):
        output += f"VM: {instance}\n"
        output += f"  Load (1m): {metrics.get('load', 'N/A')}\n"
        cpu_val = metrics.get('cpu', 'N/A')
        mem_val = metrics.get('memory', 'N/A')
        output += f"  CPU: {cpu_val:.1f}%\n" if isinstance(cpu_val, float) else f"  CPU: {cpu_val}\n"
        output += f"  Memory: {mem_val:.1f}%\n\n" if isinstance(mem_val, float) else f"  Memory: {mem_val}\n\n"

    return {"status": "success", "result": output}


async def _handle_get_service_health(_request: Metadata) -> Metadata:
    """Handle get_service_health tool."""
    backend_up = await prometheus_query('up{job="autobot-backend"}')
    node_up = await prometheus_query('up{job="node"}')

    output = "Service Health Status\n" + "=" * 50 + "\n\n"

    if backend_up and backend_up.get("result"):
        for result in backend_up["result"]:
            service = result["metric"].get("service", "unknown")
            status = "UP" if result["value"][1] == "1" else "DOWN"
            output += f"AutoBot Backend ({service}): {status}\n"
    else:
        output += "AutoBot Backend: No data\n"

    if node_up and node_up.get("result"):
        output += "\nNode Exporters:\n"
        for result in node_up["result"]:
            instance = result["metric"]["instance"]
            status = "UP" if result["value"][1] == "1" else "DOWN"
            output += f"  {instance}: {status}\n"

    return {"status": "success", "result": output}


async def _handle_get_vm_metrics(request: Metadata) -> Metadata:
    """Handle get_vm_metrics tool."""
    vm_ip = request.get("vm_ip", "")
    if not vm_ip:
        return {"status": "error", "error": "vm_ip parameter is required"}

    load = await prometheus_query(f'node_load1{{instance=~"{vm_ip}:.*"}}')
    cpu = await prometheus_query(
        f'100 - (avg by (instance) (rate(node_cpu_seconds_total{{mode="idle",instance=~"{vm_ip}:.*"}}[5m])) * 100)'
    )
    memory = await prometheus_query(
        f'(1 - (node_memory_MemAvailable_bytes{{instance=~"{vm_ip}:.*"}} / node_memory_MemTotal_bytes{{instance=~"{vm_ip}:.*"}})) * 100'
    )

    output = f"VM Metrics: {vm_ip}\n" + "=" * 50 + "\n\n"

    if load and load.get("result"):
        output += f"Load Average: {load['result'][0]['value'][1]}\n"
    if cpu and cpu.get("result"):
        output += f"CPU Usage: {float(cpu['result'][0]['value'][1]):.1f}%\n"
    if memory and memory.get("result"):
        output += f"Memory Usage: {float(memory['result'][0]['value'][1]):.1f}%\n"

    if output.count("\n") <= 3:
        output += "\nNo metrics available for this VM."

    return {"status": "success", "result": output}


async def _fetch_metrics_list() -> tuple:
    """Fetch metrics list from Prometheus (Issue #315 - extracted)."""
    http_client = get_http_client()
    async with await http_client.get(
        f"{PROMETHEUS_URL}/api/v1/label/__name__/values",
        timeout=aiohttp.ClientTimeout(total=10),
    ) as response:
        if response.status != 200:
            return None, "Failed to fetch metrics list"
        data = await response.json()
        if data.get("status") != "success":
            return None, "Failed to fetch metrics list"
        return data.get("data", []), None


def _format_metrics_output(metrics: list, filter_pattern: str) -> str:
    """Format metrics list output (Issue #315 - extracted)."""
    if filter_pattern:
        metrics = [m for m in metrics if filter_pattern in m]

    autobot_metrics = [m for m in metrics if m.startswith("autobot_")]
    node_metrics = [m for m in metrics if m.startswith("node_")]

    output = "Available Prometheus Metrics\n" + "=" * 50 + "\n\n"

    if autobot_metrics:
        output += f"AutoBot Metrics ({len(autobot_metrics)}):\n"
        for metric in sorted(autobot_metrics)[:20]:
            output += f"  - {metric}\n"
        if len(autobot_metrics) > 20:
            output += f"  ... and {len(autobot_metrics) - 20} more\n"
        output += "\n"

    if node_metrics:
        output += f"Node/System Metrics ({len(node_metrics)}):\n"
        for metric in sorted(node_metrics)[:20]:
            output += f"  - {metric}\n"
        if len(node_metrics) > 20:
            output += f"  ... and {len(node_metrics) - 20} more\n"

    return output


async def _handle_list_available_metrics(request: Metadata) -> Metadata:
    """Handle list_available_metrics tool."""
    metrics, error = await _fetch_metrics_list()
    if error:
        return {"status": "error", "error": error}

    filter_pattern = request.get("filter", "")
    output = _format_metrics_output(metrics, filter_pattern)
    return {"status": "success", "result": output}


# Tool dispatch table (Issue #315 - reduces nesting from if-elif chain)
TOOL_HANDLERS = {
    "query_metric": _handle_query_metric,
    "get_system_metrics": _handle_get_system_metrics,
    "get_service_health": _handle_get_service_health,
    "get_vm_metrics": _handle_get_vm_metrics,
    "list_available_metrics": _handle_list_available_metrics,
}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_prometheus_tool",
    error_code_prefix="PROMETHEUS_MCP",
)
@router.post("/mcp/{tool_name}")
async def execute_prometheus_tool(tool_name: str, request: Metadata) -> Metadata:
    """
    Execute a Prometheus MCP tool

    Args:
        tool_name: Name of the tool to execute
        request: Tool-specific request parameters

    Returns:
        Tool execution results with metrics data
    """
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return {"status": "error", "error": f"Unknown tool: {tool_name}"}

    try:
        return await handler(request)
    except Exception as e:
        logger.error(f"Error executing Prometheus tool {tool_name}: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
