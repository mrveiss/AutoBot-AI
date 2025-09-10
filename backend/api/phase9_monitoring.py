"""
Phase 9 Comprehensive Performance Monitoring API
Real-time monitoring dashboard for GPU/NPU utilization, multi-modal AI performance,
and distributed system optimization.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import aiofiles
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# Import Phase 9 monitoring system
from src.utils.phase9_performance_monitor import (
    phase9_monitor,
    start_phase9_monitoring,
    stop_phase9_monitoring,
    get_phase9_performance_dashboard,
    get_phase9_optimization_recommendations,
    collect_phase9_metrics,
    add_phase9_alert_callback,
    monitor_performance
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/monitoring/phase9", tags=["Phase 9 Monitoring"])


class MonitoringStatus(BaseModel):
    """Monitoring system status"""
    active: bool
    uptime_seconds: float
    collection_interval: float
    hardware_acceleration: Dict[str, bool]
    metrics_collected: int
    alerts_count: int


class PerformanceAlert(BaseModel):
    """Performance alert model"""
    category: str
    severity: str
    message: str
    recommendation: str
    timestamp: float


class OptimizationRecommendation(BaseModel):
    """Performance optimization recommendation"""
    category: str
    priority: str
    recommendation: str
    action: str
    expected_improvement: str


class MetricsQuery(BaseModel):
    """Query parameters for metrics retrieval"""
    categories: Optional[List[str]] = Field(None, description="Metric categories to include")
    time_range_minutes: int = Field(10, ge=1, le=1440, description="Time range in minutes")
    include_trends: bool = Field(True, description="Include trend analysis")
    include_alerts: bool = Field(True, description="Include recent alerts")


class ThresholdUpdate(BaseModel):
    """Performance threshold update"""
    category: str
    metric: str
    threshold: float
    comparison: str = Field(..., regex="^(gt|lt|eq)$")


# WebSocket connection manager for real-time updates
class MonitoringWebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.update_task: Optional[asyncio.Task] = None
        self.update_interval = 2.0  # Send updates every 2 seconds
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Active connections: {len(self.active_connections)}")
        
        # Start update task if this is the first connection
        if len(self.active_connections) == 1 and not self.update_task:
            self.update_task = asyncio.create_task(self._send_periodic_updates())
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Active connections: {len(self.active_connections)}")
        
        # Stop update task if no connections
        if len(self.active_connections) == 0 and self.update_task:
            self.update_task.cancel()
            self.update_task = None
    
    async def broadcast_update(self, data: Dict[str, Any]):
        """Broadcast update to all connected clients"""
        if not self.active_connections:
            return
        
        message = json.dumps(data, default=str)
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message: {e}")
                disconnected.append(connection)
        
        # Remove disconnected connections
        for connection in disconnected:
            self.disconnect(connection)
    
    async def _send_periodic_updates(self):
        """Send periodic performance updates to connected clients"""
        while self.active_connections:
            try:
                # Get current performance data
                dashboard = get_phase9_performance_dashboard()
                
                # Prepare update message
                update = {
                    "type": "performance_update",
                    "timestamp": time.time(),
                    "data": dashboard
                }
                
                await self.broadcast_update(update)
                await asyncio.sleep(self.update_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic updates: {e}")
                await asyncio.sleep(self.update_interval)


# Global WebSocket manager
ws_manager = MonitoringWebSocketManager()


@router.get("/status", response_model=MonitoringStatus)
async def get_monitoring_status():
    """Get current monitoring system status"""
    try:
        dashboard = get_phase9_performance_dashboard()
        
        # Calculate uptime
        uptime_seconds = 0
        if phase9_monitor.monitoring_active:
            uptime_seconds = time.time() - getattr(phase9_monitor, 'start_time', time.time())
        
        # Count metrics collected
        metrics_collected = (
            len(phase9_monitor.gpu_metrics_buffer) +
            len(phase9_monitor.npu_metrics_buffer) +
            len(phase9_monitor.multimodal_metrics_buffer) +
            len(phase9_monitor.system_metrics_buffer)
        )
        
        return MonitoringStatus(
            active=phase9_monitor.monitoring_active,
            uptime_seconds=uptime_seconds,
            collection_interval=phase9_monitor.collection_interval,
            hardware_acceleration=dashboard.get("hardware_acceleration", {}),
            metrics_collected=metrics_collected,
            alerts_count=len(phase9_monitor.performance_alerts)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get monitoring status: {str(e)}")


@router.post("/start")
async def start_monitoring(background_tasks: BackgroundTasks):
    """Start Phase 9 performance monitoring"""
    try:
        if phase9_monitor.monitoring_active:
            return {
                "status": "already_running",
                "message": "Phase 9 monitoring is already active"
            }
        
        # Start monitoring in background
        background_tasks.add_task(start_phase9_monitoring)
        
        # Add alert callback for WebSocket broadcasting
        async def alert_callback(alerts: List[Dict[str, Any]]):
            await ws_manager.broadcast_update({
                "type": "performance_alerts",
                "timestamp": time.time(),
                "alerts": alerts
            })
        
        add_phase9_alert_callback(alert_callback)
        
        return {
            "status": "started",
            "message": "Phase 9 comprehensive performance monitoring started",
            "collection_interval": phase9_monitor.collection_interval
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start monitoring: {str(e)}")


@router.post("/stop")
async def stop_monitoring():
    """Stop Phase 9 performance monitoring"""
    try:
        if not phase9_monitor.monitoring_active:
            return {
                "status": "not_running",
                "message": "Phase 9 monitoring is not currently active"
            }
        
        await stop_phase9_monitoring()
        
        return {
            "status": "stopped",
            "message": "Phase 9 performance monitoring stopped"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop monitoring: {str(e)}")


@router.get("/dashboard")
async def get_performance_dashboard():
    """Get comprehensive performance dashboard"""
    try:
        dashboard = get_phase9_performance_dashboard()
        
        # Add additional analysis
        dashboard["analysis"] = {
            "overall_health": _calculate_overall_health(dashboard),
            "performance_score": _calculate_performance_score(dashboard),
            "bottlenecks": _identify_bottlenecks(dashboard),
            "resource_utilization": _analyze_resource_utilization(dashboard)
        }
        
        return dashboard
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get performance dashboard: {str(e)}")


@router.get("/metrics/current")
async def get_current_metrics():
    """Get current performance metrics snapshot"""
    try:
        metrics = await collect_phase9_metrics()
        return {
            "timestamp": time.time(),
            "metrics": metrics,
            "collection_successful": metrics.get("collection_successful", False)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to collect current metrics: {str(e)}")


@router.post("/metrics/query")
async def query_metrics(query: MetricsQuery):
    """Query historical performance metrics with filters"""
    try:
        result = {
            "query": query.dict(),
            "timestamp": time.time(),
            "metrics": {},
            "trends": {},
            "alerts": []
        }
        
        # Calculate time range
        end_time = time.time()
        start_time = end_time - (query.time_range_minutes * 60)
        
        # Filter metrics by time range and categories
        categories = query.categories or ["gpu", "npu", "multimodal", "system", "services"]
        
        for category in categories:
            if category == "gpu" and phase9_monitor.gpu_metrics_buffer:
                filtered_metrics = [
                    m for m in phase9_monitor.gpu_metrics_buffer
                    if start_time <= m.timestamp <= end_time
                ]
                result["metrics"]["gpu"] = [
                    {
                        "timestamp": m.timestamp,
                        "utilization_percent": m.utilization_percent,
                        "memory_utilization_percent": m.memory_utilization_percent,
                        "temperature_celsius": m.temperature_celsius,
                        "power_draw_watts": m.power_draw_watts
                    }
                    for m in filtered_metrics
                ]
            
            elif category == "npu" and phase9_monitor.npu_metrics_buffer:
                filtered_metrics = [
                    m for m in phase9_monitor.npu_metrics_buffer
                    if start_time <= m.timestamp <= end_time
                ]
                result["metrics"]["npu"] = [
                    {
                        "timestamp": m.timestamp,
                        "utilization_percent": m.utilization_percent,
                        "acceleration_ratio": m.acceleration_ratio,
                        "inference_count": m.inference_count,
                        "average_inference_time_ms": m.average_inference_time_ms
                    }
                    for m in filtered_metrics
                ]
            
            elif category == "system" and phase9_monitor.system_metrics_buffer:
                filtered_metrics = [
                    m for m in phase9_monitor.system_metrics_buffer
                    if start_time <= m.timestamp <= end_time
                ]
                result["metrics"]["system"] = [
                    {
                        "timestamp": m.timestamp,
                        "cpu_usage_percent": m.cpu_usage_percent,
                        "memory_usage_percent": m.memory_usage_percent,
                        "cpu_load_1m": m.cpu_load_1m,
                        "network_latency_ms": m.network_latency_ms
                    }
                    for m in filtered_metrics
                ]
        
        # Include trends if requested
        if query.include_trends:
            result["trends"] = phase9_monitor._calculate_performance_trends()
        
        # Include recent alerts if requested
        if query.include_alerts:
            result["alerts"] = [
                alert for alert in phase9_monitor.performance_alerts
                if start_time <= alert.get("timestamp", 0) <= end_time
            ]
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query metrics: {str(e)}")


@router.get("/optimization/recommendations", response_model=List[OptimizationRecommendation])
async def get_optimization_recommendations():
    """Get performance optimization recommendations"""
    try:
        recommendations = get_phase9_optimization_recommendations()
        
        return [
            OptimizationRecommendation(
                category=rec["category"],
                priority=rec["priority"],
                recommendation=rec["recommendation"],
                action=rec["action"],
                expected_improvement=rec["expected_improvement"]
            )
            for rec in recommendations
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get optimization recommendations: {str(e)}")


@router.get("/alerts", response_model=List[PerformanceAlert])
async def get_performance_alerts(
    severity: Optional[str] = Query(None, description="Filter by severity"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of alerts")
):
    """Get performance alerts with optional filtering"""
    try:
        alerts = list(phase9_monitor.performance_alerts)
        
        # Apply filters
        if severity:
            alerts = [a for a in alerts if a.get("severity") == severity]
        
        if category:
            alerts = [a for a in alerts if a.get("category") == category]
        
        # Sort by timestamp (most recent first) and limit
        alerts.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        alerts = alerts[:limit]
        
        return [
            PerformanceAlert(
                category=alert["category"],
                severity=alert["severity"],
                message=alert["message"],
                recommendation=alert["recommendation"],
                timestamp=alert["timestamp"]
            )
            for alert in alerts
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get performance alerts: {str(e)}")


@router.post("/thresholds/update")
async def update_performance_threshold(threshold: ThresholdUpdate):
    """Update performance monitoring thresholds"""
    try:
        # Update threshold in monitoring system
        threshold_key = f"{threshold.category}_{threshold.metric}"
        
        if threshold_key in phase9_monitor.performance_baselines:
            old_value = phase9_monitor.performance_baselines[threshold_key]
            phase9_monitor.performance_baselines[threshold_key] = threshold.threshold
            
            return {
                "status": "updated",
                "threshold_key": threshold_key,
                "old_value": old_value,
                "new_value": threshold.threshold,
                "comparison": threshold.comparison
            }
        else:
            return {
                "status": "created",
                "threshold_key": threshold_key,
                "new_value": threshold.threshold,
                "comparison": threshold.comparison
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update threshold: {str(e)}")


@router.get("/hardware/gpu")
async def get_gpu_details():
    """Get detailed GPU information and metrics"""
    try:
        gpu_metrics = await phase9_monitor.collect_gpu_metrics()
        
        if not gpu_metrics:
            return {
                "available": False,
                "message": "GPU not available or accessible"
            }
        
        return {
            "available": True,
            "current_metrics": gpu_metrics.__dict__,
            "historical_data": [
                {
                    "timestamp": m.timestamp,
                    "utilization_percent": m.utilization_percent,
                    "memory_utilization_percent": m.memory_utilization_percent,
                    "temperature_celsius": m.temperature_celsius
                }
                for m in list(phase9_monitor.gpu_metrics_buffer)[-60:]  # Last 60 samples
            ],
            "optimization_status": {
                "target_utilization": phase9_monitor.performance_baselines["gpu_utilization_target"],
                "current_efficiency": _calculate_gpu_efficiency(gpu_metrics),
                "throttling_detected": gpu_metrics.thermal_throttling or gpu_metrics.power_throttling
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get GPU details: {str(e)}")


@router.get("/hardware/npu")
async def get_npu_details():
    """Get detailed NPU information and metrics"""
    try:
        npu_metrics = await phase9_monitor.collect_npu_metrics()
        
        if not npu_metrics:
            return {
                "available": False,
                "message": "NPU not available or not supported"
            }
        
        return {
            "available": True,
            "current_metrics": npu_metrics.__dict__,
            "historical_data": [
                {
                    "timestamp": m.timestamp,
                    "utilization_percent": m.utilization_percent,
                    "acceleration_ratio": m.acceleration_ratio,
                    "inference_count": m.inference_count
                }
                for m in list(phase9_monitor.npu_metrics_buffer)[-60:]  # Last 60 samples
            ],
            "optimization_status": {
                "target_acceleration": phase9_monitor.performance_baselines["npu_acceleration_target"],
                "current_efficiency": _calculate_npu_efficiency(npu_metrics),
                "wsl_limitation": npu_metrics.wsl_limitation
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get NPU details: {str(e)}")


@router.get("/services/health")
async def get_services_health():
    """Get health status of all monitored services"""
    try:
        service_metrics = await phase9_monitor.collect_service_performance_metrics()
        
        services_health = {
            "timestamp": time.time(),
            "total_services": len(service_metrics),
            "healthy_services": sum(1 for s in service_metrics if s.status == "healthy"),
            "degraded_services": sum(1 for s in service_metrics if s.status == "degraded"),
            "critical_services": sum(1 for s in service_metrics if s.status in ["critical", "offline"]),
            "services": []
        }
        
        for service in service_metrics:
            services_health["services"].append({
                "name": service.service_name,
                "host": service.host,
                "port": service.port,
                "status": service.status,
                "response_time_ms": service.response_time_ms,
                "health_score": service.health_score,
                "uptime_hours": service.uptime_hours
            })
        
        # Calculate overall system health
        if services_health["critical_services"] > 0:
            overall_status = "critical"
        elif services_health["degraded_services"] > 0:
            overall_status = "degraded"
        else:
            overall_status = "healthy"
        
        services_health["overall_status"] = overall_status
        services_health["health_percentage"] = round(
            (services_health["healthy_services"] / services_health["total_services"]) * 100, 1
        ) if services_health["total_services"] > 0 else 0
        
        return services_health
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get services health: {str(e)}")


@router.get("/export/metrics")
async def export_metrics(
    format: str = Query("json", regex="^(json|csv)$"),
    time_range_hours: int = Query(1, ge=1, le=168)  # Max 1 week
):
    """Export performance metrics in JSON or CSV format"""
    try:
        # Calculate time range
        end_time = time.time()
        start_time = end_time - (time_range_hours * 3600)
        
        # Collect all metrics within time range
        export_data = {
            "export_info": {
                "timestamp": end_time,
                "time_range_hours": time_range_hours,
                "start_time": start_time,
                "end_time": end_time,
                "format": format
            },
            "gpu_metrics": [],
            "npu_metrics": [],
            "system_metrics": [],
            "service_metrics": {}
        }
        
        # Filter GPU metrics
        for metric in phase9_monitor.gpu_metrics_buffer:
            if start_time <= metric.timestamp <= end_time:
                export_data["gpu_metrics"].append(metric.__dict__)
        
        # Filter NPU metrics
        for metric in phase9_monitor.npu_metrics_buffer:
            if start_time <= metric.timestamp <= end_time:
                export_data["npu_metrics"].append(metric.__dict__)
        
        # Filter system metrics
        for metric in phase9_monitor.system_metrics_buffer:
            if start_time <= metric.timestamp <= end_time:
                export_data["system_metrics"].append(metric.__dict__)
        
        # Filter service metrics
        for service_name, metrics_buffer in phase9_monitor.service_metrics_buffer.items():
            filtered_metrics = [
                m.__dict__ for m in metrics_buffer
                if start_time <= m.timestamp <= end_time
            ]
            if filtered_metrics:
                export_data["service_metrics"][service_name] = filtered_metrics
        
        if format == "json":
            # Return JSON response
            return JSONResponse(
                content=export_data,
                headers={
                    "Content-Disposition": f"attachment; filename=autobot_metrics_{int(end_time)}.json"
                }
            )
        
        elif format == "csv":
            # Convert to CSV and return as streaming response
            csv_content = _convert_metrics_to_csv(export_data)
            
            async def generate():
                yield csv_content.encode()
            
            return StreamingResponse(
                generate(),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=autobot_metrics_{int(end_time)}.csv"
                }
            )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export metrics: {str(e)}")


@router.websocket("/realtime")
async def realtime_monitoring_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time performance monitoring updates"""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle client messages
            message = await websocket.receive_text()
            
            # Handle client commands
            try:
                command = json.loads(message)
                if command.get("type") == "get_current_metrics":
                    metrics = await collect_phase9_metrics()
                    await websocket.send_text(json.dumps({
                        "type": "metrics_response",
                        "data": metrics
                    }, default=str))
                
                elif command.get("type") == "update_interval":
                    new_interval = command.get("interval", 2.0)
                    if 0.5 <= new_interval <= 30.0:
                        ws_manager.update_interval = new_interval
                        await websocket.send_text(json.dumps({
                            "type": "interval_updated",
                            "interval": new_interval
                        }))
                
            except json.JSONDecodeError:
                # Ignore invalid JSON messages
                pass
            
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# Helper functions
def _calculate_overall_health(dashboard: Dict[str, Any]) -> str:
    """Calculate overall system health based on dashboard data"""
    try:
        health_factors = []
        
        # GPU health
        if dashboard.get("gpu"):
            gpu = dashboard["gpu"]
            if gpu.get("thermal_throttling") or gpu.get("power_throttling"):
                health_factors.append("critical")
            elif gpu.get("utilization_percent", 0) < 20:
                health_factors.append("warning")
            else:
                health_factors.append("healthy")
        
        # System health
        if dashboard.get("system"):
            system = dashboard["system"]
            if system.get("memory_usage_percent", 0) > 90:
                health_factors.append("critical")
            elif system.get("cpu_load_1m", 0) > 20:
                health_factors.append("warning")
            else:
                health_factors.append("healthy")
        
        # Service health
        if dashboard.get("services"):
            critical_services = any(
                service.get("status") in ["critical", "offline"]
                for service in dashboard["services"].values()
            )
            if critical_services:
                health_factors.append("critical")
            else:
                health_factors.append("healthy")
        
        # Overall assessment
        if "critical" in health_factors:
            return "critical"
        elif "warning" in health_factors:
            return "warning"
        else:
            return "healthy"
            
    except Exception:
        return "unknown"


def _calculate_performance_score(dashboard: Dict[str, Any]) -> float:
    """Calculate overall performance score (0-100)"""
    try:
        scores = []
        
        # GPU performance score
        if dashboard.get("gpu"):
            gpu = dashboard["gpu"]
            gpu_score = min(100, gpu.get("utilization_percent", 0) * 1.25)  # Favor high utilization
            if gpu.get("thermal_throttling"):
                gpu_score *= 0.5
            scores.append(gpu_score)
        
        # NPU performance score
        if dashboard.get("npu"):
            npu = dashboard["npu"]
            npu_score = min(100, npu.get("acceleration_ratio", 0) * 20)  # Target 5x = 100%
            scores.append(npu_score)
        
        # System performance score
        if dashboard.get("system"):
            system = dashboard["system"]
            cpu_score = max(0, 100 - system.get("cpu_load_1m", 0) * 5)  # Penalize high load
            memory_score = max(0, 100 - system.get("memory_usage_percent", 0))
            system_score = (cpu_score + memory_score) / 2
            scores.append(system_score)
        
        return round(sum(scores) / len(scores), 1) if scores else 0.0
        
    except Exception:
        return 0.0


def _identify_bottlenecks(dashboard: Dict[str, Any]) -> List[str]:
    """Identify system bottlenecks"""
    bottlenecks = []
    
    try:
        # GPU bottlenecks
        if dashboard.get("gpu"):
            gpu = dashboard["gpu"]
            if gpu.get("memory_utilization_percent", 0) > 95:
                bottlenecks.append("GPU memory saturation")
            if gpu.get("thermal_throttling"):
                bottlenecks.append("GPU thermal throttling")
        
        # System bottlenecks
        if dashboard.get("system"):
            system = dashboard["system"]
            if system.get("memory_usage_percent", 0) > 90:
                bottlenecks.append("System memory pressure")
            if system.get("cpu_load_1m", 0) > 20:
                bottlenecks.append("High CPU load")
            if system.get("network_latency_ms", 0) > 100:
                bottlenecks.append("Network latency")
        
        # Service bottlenecks
        if dashboard.get("services"):
            slow_services = [
                name for name, service in dashboard["services"].items()
                if service.get("response_time_ms", 0) > 500
            ]
            if slow_services:
                bottlenecks.append(f"Slow services: {', '.join(slow_services)}")
        
    except Exception:
        pass
    
    return bottlenecks


def _analyze_resource_utilization(dashboard: Dict[str, Any]) -> Dict[str, float]:
    """Analyze resource utilization efficiency"""
    utilization = {}
    
    try:
        if dashboard.get("gpu"):
            utilization["gpu"] = dashboard["gpu"].get("utilization_percent", 0)
        
        if dashboard.get("npu"):
            utilization["npu"] = dashboard["npu"].get("utilization_percent", 0)
        
        if dashboard.get("system"):
            utilization["cpu"] = dashboard["system"].get("cpu_usage_percent", 0)
            utilization["memory"] = dashboard["system"].get("memory_usage_percent", 0)
        
    except Exception:
        pass
    
    return utilization


def _calculate_gpu_efficiency(gpu_metrics) -> float:
    """Calculate GPU efficiency score"""
    try:
        utilization = gpu_metrics.utilization_percent
        memory_util = gpu_metrics.memory_utilization_percent
        
        # Efficiency based on balanced utilization
        efficiency = (utilization + memory_util) / 2
        
        # Penalize for throttling
        if gpu_metrics.thermal_throttling:
            efficiency *= 0.7
        if gpu_metrics.power_throttling:
            efficiency *= 0.8
        
        return round(efficiency, 1)
        
    except Exception:
        return 0.0


def _calculate_npu_efficiency(npu_metrics) -> float:
    """Calculate NPU efficiency score"""
    try:
        # Base efficiency on acceleration ratio
        efficiency = min(100, npu_metrics.acceleration_ratio * 20)  # 5x = 100%
        
        # Adjust for thermal state
        if npu_metrics.thermal_state == "throttling":
            efficiency *= 0.7
        elif npu_metrics.thermal_state == "critical":
            efficiency *= 0.5
        
        return round(efficiency, 1)
        
    except Exception:
        return 0.0


def _convert_metrics_to_csv(data: Dict[str, Any]) -> str:
    """Convert metrics data to CSV format"""
    try:
        import io
        import csv
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "timestamp", "category", "metric", "value", "unit"
        ])
        
        # Write GPU metrics
        for metric in data.get("gpu_metrics", []):
            timestamp = metric["timestamp"]
            for key, value in metric.items():
                if key != "timestamp":
                    writer.writerow([timestamp, "gpu", key, value, ""])
        
        # Write NPU metrics
        for metric in data.get("npu_metrics", []):
            timestamp = metric["timestamp"]
            for key, value in metric.items():
                if key != "timestamp":
                    writer.writerow([timestamp, "npu", key, value, ""])
        
        # Write system metrics
        for metric in data.get("system_metrics", []):
            timestamp = metric["timestamp"]
            for key, value in metric.items():
                if key != "timestamp":
                    writer.writerow([timestamp, "system", key, value, ""])
        
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"Error converting to CSV: {e}")
        return "Error generating CSV"


# Performance monitoring decorator endpoint
@router.post("/test/performance")
@monitor_performance("api_test")
async def test_performance_monitoring():
    """Test endpoint to demonstrate performance monitoring"""
    # Simulate some work
    await asyncio.sleep(0.1)
    
    # Collect current metrics
    metrics = await collect_phase9_metrics()
    
    return {
        "message": "Performance monitoring test completed",
        "metrics_collected": metrics.get("collection_successful", False),
        "timestamp": time.time()
    }