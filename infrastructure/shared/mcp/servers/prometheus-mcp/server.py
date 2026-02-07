#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Prometheus MCP Server
Provides agents with access to Prometheus metrics data
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

# Prometheus configuration
PROMETHEUS_URL = "http://172.16.168.23:9090"

app = Server("prometheus-mcp")


@app.list_tools()
async def list_tools() -> List[Tool]:
    """List available Prometheus query tools."""
    return [
        Tool(
            name="query_metric",
            description="Query current value of a Prometheus metric",
            inputSchema={
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
        Tool(
            name="query_range",
            description="Query metric values over a time range",
            inputSchema={
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
        Tool(
            name="get_system_metrics",
            description="Get current system metrics for all machines (CPU, memory, load)",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_service_health",
            description="Get health status of all AutoBot services",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_vm_metrics",
            description="Get detailed metrics for a specific VM",
            inputSchema={
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
        Tool(
            name="list_available_metrics",
            description="List all available Prometheus metrics with descriptions",
            inputSchema={
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


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> List[TextContent]:
    """Handle tool calls."""

    if name == "query_metric":
        return await query_metric(arguments["query"])

    elif name == "query_range":
        duration = arguments.get("duration", "1h")
        step = arguments.get("step", "15s")
        return await query_range(arguments["query"], duration, step)

    elif name == "get_system_metrics":
        return await get_system_metrics()

    elif name == "get_service_health":
        return await get_service_health()

    elif name == "get_vm_metrics":
        return await get_vm_metrics(arguments["vm_ip"])

    elif name == "list_available_metrics":
        filter_pattern = arguments.get("filter", "")
        return await list_available_metrics(filter_pattern)

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def prometheus_query(query: str) -> Optional[Dict]:
    """Execute instant Prometheus query."""
    try:
        async with aiohttp.ClientSession() as session:
            params = {"query": query}
            async with session.get(
                f"{PROMETHEUS_URL}/api/v1/query", params=params, timeout=10
            ) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                if data.get("status") != "success":
                    return None

                return data.get("data", {})

    except Exception:
        return None


async def prometheus_query_range(
    query: str, start: datetime, end: datetime, step: str
) -> Optional[Dict]:
    """Execute range Prometheus query."""
    try:
        async with aiohttp.ClientSession() as session:
            params = {
                "query": query,
                "start": start.isoformat() + "Z",
                "end": end.isoformat() + "Z",
                "step": step,
            }
            async with session.get(
                f"{PROMETHEUS_URL}/api/v1/query_range", params=params, timeout=30
            ) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                if data.get("status") != "success":
                    return None

                return data.get("data", {})

    except Exception:
        return None


async def query_metric(query: str) -> List[TextContent]:
    """Query current metric value."""
    data = await prometheus_query(query)

    if not data or not data.get("result"):
        return [TextContent(type="text", text=f"No data found for query: {query}")]

    results = []
    for result in data["result"]:
        metric = result["metric"]
        value = result["value"][1]
        result["value"][0]

        # Format metric labels
        labels = ", ".join([f"{k}={v}" for k, v in metric.items() if k != "__name__"])
        metric_name = metric.get("__name__", query)

        results.append(f"{metric_name}{{{labels}}}: {value}")

    return [
        TextContent(
            type="text", text=f"Query: {query}\n\nResults:\n" + "\n".join(results)
        )
    ]


async def query_range(query: str, duration: str, step: str) -> List[TextContent]:
    """Query metric over time range."""
    # Parse duration
    duration_map = {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "1d": timedelta(days=1),
        "7d": timedelta(days=7),
    }

    delta = duration_map.get(duration, timedelta(hours=1))
    end = datetime.utcnow()
    start = end - delta

    data = await prometheus_query_range(query, start, end, step)

    if not data or not data.get("result"):
        return [TextContent(type="text", text=f"No data found for query: {query}")]

    results = []
    for result in data["result"]:
        metric = result["metric"]
        values = result.get("values", [])

        labels = ", ".join([f"{k}={v}" for k, v in metric.items() if k != "__name__"])
        metric_name = metric.get("__name__", query)

        # Format time series
        series = f"\n{metric_name}{{{labels}}}:\n"
        for timestamp, value in values[-10:]:  # Last 10 points
            dt = datetime.fromtimestamp(timestamp)
            series += f"  {dt.strftime('%H:%M:%S')}: {value}\n"

        results.append(series)

    return [
        TextContent(
            type="text",
            text=f"Query: {query}\nDuration: {duration}\nStep: {step}\n"
            + "\n".join(results),
        )
    ]


async def get_system_metrics() -> List[TextContent]:
    """Get system metrics for all machines."""

    # Query all VMs
    load_data = await prometheus_query("node_load1")
    cpu_data = await prometheus_query(
        "100 - (avg by (instance) (rate(node_cpu_seconds_total{mode='idle'}[5m])) * 100)"
    )
    memory_data = await prometheus_query(
        "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100"
    )

    if not load_data or not load_data.get("result"):
        return [
            TextContent(
                type="text",
                text="No system metrics available. Node exporters may not be running.",
            )
        ]

    output = "System Metrics (All Machines)\n" + "=" * 50 + "\n\n"

    # Build VM map
    vms = {}

    # Load averages
    for result in load_data.get("result", []):
        instance = result["metric"]["instance"]
        load = float(result["value"][1])
        vms[instance] = {"load": load}

    # CPU usage
    for result in cpu_data.get("result", []) if cpu_data else []:
        instance = result["metric"]["instance"]
        cpu = float(result["value"][1])
        if instance in vms:
            vms[instance]["cpu"] = cpu

    # Memory usage
    for result in memory_data.get("result", []) if memory_data else []:
        instance = result["metric"]["instance"]
        memory = float(result["value"][1])
        if instance in vms:
            vms[instance]["memory"] = memory

    # Format output
    for instance, metrics in sorted(vms.items()):
        output += f"VM: {instance}\n"
        output += f"  Load (1m): {metrics.get('load', 'N/A')}\n"
        output += f"  CPU: {metrics.get('cpu', 'N/A'):.1f}%\n"
        output += f"  Memory: {metrics.get('memory', 'N/A'):.1f}%\n\n"

    return [TextContent(type="text", text=output)]


async def get_service_health() -> List[TextContent]:
    """Get AutoBot service health status."""

    # Query service status
    backend_up = await prometheus_query('up{job="autobot-backend"}')

    output = "Service Health Status\n" + "=" * 50 + "\n\n"

    if backend_up and backend_up.get("result"):
        for result in backend_up["result"]:
            service = result["metric"].get("service", "unknown")
            status = "UP" if result["value"][1] == "1" else "DOWN"
            output += f"AutoBot Backend ({service}): {status}\n"
    else:
        output += "AutoBot Backend: No data\n"

    # Query node exporters
    node_up = await prometheus_query('up{job="node"}')
    if node_up and node_up.get("result"):
        output += "\nNode Exporters:\n"
        for result in node_up["result"]:
            instance = result["metric"]["instance"]
            status = "UP" if result["value"][1] == "1" else "DOWN"
            output += f"  {instance}: {status}\n"

    return [TextContent(type="text", text=output)]


async def get_vm_metrics(vm_ip: str) -> List[TextContent]:
    """Get detailed metrics for a specific VM."""

    # Query metrics for this VM
    instance_filter = f'instance=~"{vm_ip}:.*"'
    load = await prometheus_query(f"node_load1{{{instance_filter}}}")
    cpu = await prometheus_query(
        f"100 - (avg by (instance) "
        f'(rate(node_cpu_seconds_total{{mode="idle",{instance_filter}}}[5m])) * 100)'
    )
    memory = await prometheus_query(
        f"(1 - (node_memory_MemAvailable_bytes{{{instance_filter}}} / "
        f"node_memory_MemTotal_bytes{{{instance_filter}}})) * 100"
    )
    disk = await prometheus_query(
        f'(1 - (node_filesystem_avail_bytes{{{instance_filter},fstype!="tmpfs"}} / '
        f'node_filesystem_size_bytes{{{instance_filter},fstype!="tmpfs"}})) * 100'
    )

    output = f"VM Metrics: {vm_ip}\n" + "=" * 50 + "\n\n"

    if load and load.get("result"):
        output += f"Load Average: {load['result'][0]['value'][1]}\n"

    if cpu and cpu.get("result"):
        output += f"CPU Usage: {float(cpu['result'][0]['value'][1]):.1f}%\n"

    if memory and memory.get("result"):
        output += f"Memory Usage: {float(memory['result'][0]['value'][1]):.1f}%\n"

    if disk and disk.get("result"):
        for result in disk["result"]:
            mountpoint = result["metric"].get("mountpoint", "unknown")
            usage = float(result["value"][1])
            output += f"Disk ({mountpoint}): {usage:.1f}%\n"

    if output.count("\n") <= 3:
        output += "\nNo metrics available for this VM."

    return [TextContent(type="text", text=output)]


async def list_available_metrics(filter_pattern: str) -> List[TextContent]:
    """List all available metrics."""

    # Query label values for __name__ (all metric names)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{PROMETHEUS_URL}/api/v1/label/__name__/values", timeout=10
            ) as response:
                if response.status != 200:
                    return [
                        TextContent(type="text", text="Failed to fetch metrics list")
                    ]

                data = await response.json()
                if data.get("status") != "success":
                    return [
                        TextContent(type="text", text="Failed to fetch metrics list")
                    ]

                metrics = data.get("data", [])

                # Filter if pattern provided
                if filter_pattern:
                    metrics = [m for m in metrics if filter_pattern in m]

                # Categorize metrics
                autobot_metrics = [m for m in metrics if m.startswith("autobot_")]
                node_metrics = [m for m in metrics if m.startswith("node_")]
                other_metrics = [
                    m
                    for m in metrics
                    if not m.startswith("autobot_") and not m.startswith("node_")
                ]

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
                    output += "\n"

                if other_metrics and not filter_pattern:
                    output += f"Other Metrics ({len(other_metrics)}):\n"
                    for metric in sorted(other_metrics)[:10]:
                        output += f"  - {metric}\n"
                    if len(other_metrics) > 10:
                        output += f"  ... and {len(other_metrics) - 10} more\n"

                return [TextContent(type="text", text=output)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error fetching metrics: {str(e)}")]


@app.list_resources()
async def list_resources() -> List[Resource]:
    """List available resources."""
    return [
        Resource(
            uri="prometheus://current_metrics",
            name="Current System Metrics",
            description="Real-time view of all system metrics",
            mimeType="text/plain",
        )
    ]


@app.read_resource()
async def read_resource(uri: str) -> str:
    """Read resource content."""
    if uri == "prometheus://current_metrics":
        result = await get_system_metrics()
        return result[0].text

    return f"Unknown resource: {uri}"


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
