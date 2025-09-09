"""
Real-time system monitoring API endpoints for AutoBot.
Integrates hardware monitoring into the web interface.
"""

import asyncio
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import psutil
import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Import advanced metrics system
from src.utils.system_metrics import get_metrics_collector
from src.config_helper import cfg

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


class MonitoringData(BaseModel):
    """System monitoring data model."""

    timestamp: str
    system_health: Dict[str, Any]
    gpu_status: Dict[str, Any]
    npu_status: Dict[str, Any]
    system_resources: Dict[str, Any]
    frontend_status: Dict[str, Any]
    ollama_models: Dict[str, Any]


class HardwareMonitor:
    """Hardware monitoring service."""

    def __init__(self):
        from src.config import (
            API_BASE_URL,
            FRONTEND_HOST_IP,
            FRONTEND_PORT,
            HTTP_PROTOCOL,
        )

        self.api_base = API_BASE_URL
        self.frontend_url = f"{HTTP_PROTOCOL}://{FRONTEND_HOST_IP}:{FRONTEND_PORT}"
        self._monitoring_active = False
        self._latest_data = None

    async def get_system_health(self) -> Dict[str, Any]:
        """Get AutoBot system health status."""
        try:
            response = requests.get(f"{self.api_base}/api/system/health", timeout=5)
            if response.status_code == 200:
                return response.json()
            return {"status": "error", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_gpu_status(self) -> Dict[str, Any]:
        """Get GPU utilization status with real-time data."""
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.used,memory.total,utilization.gpu,"
                    "temperature.gpu,power.draw,clocks.current.graphics,"
                    "clocks.current.memory",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                if len(parts) >= 5:
                    gpu_data = {
                        "available": True,
                        "name": parts[0].strip(),
                        "memory_used_mb": int(parts[1].strip()),
                        "memory_total_mb": int(parts[2].strip()),
                        "utilization_percent": int(parts[3].strip()),
                        "temperature_c": int(parts[4].strip()),
                        "power_draw_w": (
                            float(parts[5].strip())
                            if len(parts) > 5 and parts[5].strip()
                            else 0
                        ),
                        "memory_utilization_percent": round(
                            (int(parts[1].strip()) / int(parts[2].strip())) * 100, 1
                        ),
                        "efficiency_rating": (
                            "optimal" if int(parts[3].strip()) > 20 else "idle"
                        ),
                    }

                    # Add clock speeds if available
                    if len(parts) >= 8:
                        try:
                            gpu_data["gpu_clock_mhz"] = (
                                int(parts[6].strip()) if parts[6].strip() else 0
                            )
                            gpu_data["memory_clock_mhz"] = (
                                int(parts[7].strip()) if parts[7].strip() else 0
                            )
                        except Exception:
                            pass

                    return gpu_data
            return {"available": False, "error": "nvidia-smi failed"}
        except Exception as e:
            return {"available": False, "error": str(e)}

    def get_npu_status(self) -> Dict[str, Any]:
        """Get comprehensive Intel NPU status."""
        try:
            npu_status = {
                "hardware_detected": False,
                "driver_available": False,
                "openvino_support": False,
                "utilization_percent": 0,
                "wsl_limitation": False,
                "cpu_model": "",
                "recommendation": "",
            }

            # Check CPU model
            try:
                result = subprocess.run(
                    ["lscpu"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.split("\n"):
                        if "Model name:" in line:
                            cpu_model = line.split(":", 1)[1].strip()
                            npu_status["cpu_model"] = cpu_model
                            if "Intel(R) Core(TM) Ultra" in cpu_model:
                                npu_status["hardware_detected"] = True
                                break
            except Exception:
                pass

            # Check WSL limitation
            try:
                with open("/proc/version", "r") as f:
                    version_info = f.read()
                    if "WSL" in version_info or "Microsoft" in version_info:
                        npu_status["wsl_limitation"] = True
                        npu_status["recommendation"] = (
                            "NPU requires native Windows or Linux for hardware access"
                        )
            except Exception:
                pass

            # Check OpenVINO NPU support
            try:
                from openvino.runtime import Core

                core = Core()
                devices = core.available_devices
                npu_devices = [d for d in devices if "NPU" in d]
                if npu_devices:
                    npu_status["openvino_support"] = True
                    npu_status["driver_available"] = True
                    npu_status["available_devices"] = npu_devices
            except ImportError:
                npu_status["recommendation"] = "Install OpenVINO for NPU support"
            except Exception as e:
                npu_status["error"] = str(e)

            # Try Intel GPU Top for more detailed info
            try:
                result = subprocess.run(
                    ["intel_gpu_top", "--help"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if result.returncode == 0:
                    npu_status["intel_gpu_top_available"] = True
            except Exception:
                npu_status["intel_gpu_top_available"] = False

            return npu_status

        except Exception as e:
            return {"error": str(e), "hardware_detected": False}

    def get_system_resources(self) -> Dict[str, Any]:
        """Get detailed system resource utilization."""
        try:
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=0.1, percpu=True)
            disk = psutil.disk_usage("/")
            network = psutil.net_io_counters()

            return {
                "cpu": {
                    "percent_overall": sum(cpu_percent) / len(cpu_percent),
                    "percent_per_core": cpu_percent[:8],  # Show first 8 cores
                    "cores_physical": psutil.cpu_count(logical=False),
                    "cores_logical": psutil.cpu_count(logical=True),
                    "frequency_mhz": (
                        psutil.cpu_freq().current if psutil.cpu_freq() else 0
                    ),
                    "load_average": (
                        psutil.getloadavg()
                        if hasattr(psutil, "getloadavg")
                        else [0, 0, 0]
                    ),
                },
                "memory": {
                    "total_gb": round(memory.total / (1024**3), 2),
                    "used_gb": round(memory.used / (1024**3), 2),
                    "available_gb": round(memory.available / (1024**3), 2),
                    "percent": memory.percent,
                    "swap_total_gb": round(psutil.swap_memory().total / (1024**3), 2),
                    "swap_used_gb": round(psutil.swap_memory().used / (1024**3), 2),
                },
                "disk": {
                    "total_gb": round(disk.total / (1024**3), 2),
                    "used_gb": round(disk.used / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "percent": round((disk.used / disk.total) * 100, 1),
                },
                "network": {
                    "bytes_sent": network.bytes_sent,
                    "bytes_recv": network.bytes_recv,
                    "packets_sent": network.packets_sent,
                    "packets_recv": network.packets_recv,
                },
            }
        except Exception as e:
            return {"error": str(e)}

    async def get_comprehensive_status(self) -> MonitoringData:
        """Get comprehensive system monitoring data."""
        timestamp = datetime.now().isoformat()

        # Get all monitoring data
        system_health = await self.get_system_health()
        gpu_status = self.get_gpu_status()
        npu_status = self.get_npu_status()
        system_resources = self.get_system_resources()

        # Check frontend
        try:
            response = requests.get(self.frontend_url, timeout=3)
            frontend_status = {
                "available": response.status_code == 200,
                "status_code": response.status_code,
                "response_time_ms": response.elapsed.total_seconds() * 1000,
            }
        except Exception as e:
            frontend_status = {"available": False, "error": str(e)}

        # Get Ollama models
        try:
            from src.utils.service_registry import get_service_url
            ollama_url = get_service_url("ollama")

            response = requests.get(f"{ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                ollama_models = {
                    "available": True,
                    "count": len(data.get("models", [])),
                    "models": [
                        {
                            "name": model.get("name"),
                            "size_gb": round(model.get("size", 0) / (1024**3), 2),
                            "modified": model.get("modified_at"),
                        }
                        for model in data.get("models", [])
                    ],
                }
            else:
                ollama_models = {
                    "available": False,
                    "error": f"HTTP {response.status_code}",
                }
        except Exception as e:
            ollama_models = {"available": False, "error": str(e)}

        return MonitoringData(
            timestamp=timestamp,
            system_health=system_health,
            gpu_status=gpu_status,
            npu_status=npu_status,
            system_resources=system_resources,
            frontend_status=frontend_status,
            ollama_models=ollama_models,
        )


# Global monitor instance
hardware_monitor = HardwareMonitor()


@router.get("/status", response_model=MonitoringData)
async def get_monitoring_status():
    """Get current system monitoring status."""
    try:
        return await hardware_monitor.get_comprehensive_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gpu")
async def get_gpu_status():
    """Get detailed GPU status."""
    return hardware_monitor.get_gpu_status()


@router.get("/npu")
async def get_npu_status():
    """Get detailed NPU status."""
    return hardware_monitor.get_npu_status()


@router.get("/resources")
async def get_system_resources():
    """Get system resource utilization."""
    return hardware_monitor.get_system_resources()


# Health check moved to consolidated health service
# See backend/services/consolidated_health_service.py
# Use /api/system/health?detailed=true for comprehensive status


@router.post("/test-inference")
async def test_inference_performance():
    """Test AI inference performance."""
    try:
        test_prompt = "Test performance with a simple question: What is 2+2?"
        start_time = time.time()

        from src.config import API_BASE_URL

        response = requests.post(
            f"{API_BASE_URL}/api/chat/message",
            json={"message": test_prompt, "agent_type": "chat"},
            timeout=30,
        )

        end_time = time.time()
        response_time = end_time - start_time

        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "response_time_seconds": round(response_time, 2),
                "response_length": len(data.get("response", "")),
                "words_per_second": (
                    len(data.get("response", "").split()) / response_time
                    if response_time > 0
                    else 0
                ),
                "gpu_utilized": True,  # Assume GPU was used based on our configuration
            }
        return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# ADVANCED METRICS SYSTEM - Real-time monitoring with historical data
# ============================================================================

class MetricsQuery(BaseModel):
    """Model for advanced metrics query parameters"""
    categories: Optional[List[str]] = None
    metrics: Optional[List[str]] = None
    time_range_minutes: int = 10
    granularity_seconds: Optional[int] = None


@router.get("/metrics/health")
async def get_metrics_system_health():
    """Get advanced metrics system health status"""
    try:
        collector = get_metrics_collector()
        
        # Test basic functionality
        test_metrics = await collector.collect_system_metrics()
        
        health_status = {
            "status": "healthy" if test_metrics else "degraded",
            "metrics_collector": "operational" if test_metrics else "error",
            "collection_interval": collector._collection_interval,
            "retention_hours": collector._retention_hours,
            "buffer_size": len(collector._metrics_buffer),
            "is_collecting": collector._is_collecting
        }
        
        return health_status
        
    except Exception as e:
        return JSONResponse(
            content={"status": "unhealthy", "error": str(e)},
            status_code=500
        )


@router.get("/metrics/current")
async def get_current_advanced_metrics():
    """Get current system metrics snapshot with advanced data"""
    try:
        collector = get_metrics_collector()
        current_metrics = await collector.collect_all_metrics()
        
        # Convert metrics to serializable format
        metrics_data = {}
        for name, metric in current_metrics.items():
            metrics_data[name] = {
                "timestamp": metric.timestamp,
                "name": metric.name,
                "value": metric.value,
                "unit": metric.unit,
                "category": metric.category,
                "metadata": metric.metadata or {}
            }
        
        return {
            "timestamp": datetime.now().isoformat(),
            "metrics_count": len(metrics_data),
            "metrics": metrics_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get advanced metrics: {str(e)}")


@router.get("/metrics/summary")
async def get_advanced_metrics_summary():
    """Get comprehensive system metrics summary"""
    try:
        collector = get_metrics_collector()
        summary = await collector.get_metric_summary()
        
        return summary
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metrics summary: {str(e)}")


@router.get("/metrics/recent")
async def get_recent_advanced_metrics(
    category: Optional[str] = Query(None, description="Filter by metric category"),
    minutes: int = Query(10, description="Time range in minutes", ge=1, le=1440)
):
    """Get recent metrics within specified time range"""
    try:
        collector = get_metrics_collector()
        recent_metrics = await collector.get_recent_metrics(category=category, minutes=minutes)
        
        # Convert to serializable format
        metrics_data = []
        for metric in recent_metrics:
            metrics_data.append({
                "timestamp": metric.timestamp,
                "name": metric.name,
                "value": metric.value,
                "unit": metric.unit,
                "category": metric.category,
                "metadata": metric.metadata or {}
            })
        
        # Sort by timestamp (most recent first)
        metrics_data.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return {
            "time_range_minutes": minutes,
            "category_filter": category,
            "metrics_count": len(metrics_data),
            "metrics": metrics_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get recent metrics: {str(e)}")


@router.post("/metrics/query")
async def query_advanced_metrics(query: MetricsQuery):
    """Advanced metrics querying with filters and time ranges"""
    try:
        collector = get_metrics_collector()
        
        # Get recent metrics
        all_recent = await collector.get_recent_metrics(minutes=query.time_range_minutes)
        
        # Apply filters
        filtered_metrics = all_recent
        
        if query.categories:
            filtered_metrics = [
                m for m in filtered_metrics 
                if m.category in query.categories
            ]
        
        if query.metrics:
            filtered_metrics = [
                m for m in filtered_metrics 
                if m.name in query.metrics
            ]
        
        # Convert to serializable format
        metrics_data = []
        for metric in filtered_metrics:
            metrics_data.append({
                "timestamp": metric.timestamp,
                "name": metric.name,
                "value": metric.value,
                "unit": metric.unit,
                "category": metric.category,
                "metadata": metric.metadata or {}
            })
        
        # Sort by timestamp
        metrics_data.sort(key=lambda x: x["timestamp"], reverse=True)
        
        # Apply granularity (sampling) if requested
        if query.granularity_seconds and len(metrics_data) > 1:
            sampled_metrics = []
            last_timestamp = 0
            
            for metric in metrics_data:
                if metric["timestamp"] >= last_timestamp + query.granularity_seconds:
                    sampled_metrics.append(metric)
                    last_timestamp = metric["timestamp"]
            
            metrics_data = sampled_metrics
        
        return {
            "query": query.dict(),
            "metrics_count": len(metrics_data),
            "metrics": metrics_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query metrics: {str(e)}")


@router.get("/dashboard/overview")
async def get_dashboard_overview():
    """Get comprehensive dashboard overview combining existing and advanced metrics"""
    try:
        # Get existing hardware monitoring data
        hardware_data = await hardware_monitor.get_comprehensive_status()
        
        # Get advanced metrics
        collector = get_metrics_collector()
        current_metrics = await collector.collect_all_metrics()
        summary = await collector.get_metric_summary()
        
        # Combine data for comprehensive dashboard
        dashboard_overview = {
            "timestamp": datetime.now().isoformat(),
            
            # Existing hardware data
            "system_health": hardware_data.system_health,
            "gpu_status": hardware_data.gpu_status,
            "npu_status": hardware_data.npu_status,
            "frontend_status": hardware_data.frontend_status,
            "ollama_models": hardware_data.ollama_models,
            
            # Enhanced system resources with advanced metrics
            "system_resources": hardware_data.system_resources,
            "advanced_metrics": summary,
            
            # Service status from advanced metrics
            "services_status": {},
            "performance_indicators": {},
            "knowledge_base_stats": {},
            
            # Overall health assessment
            "overall_health": summary.get('overall_health', {})
        }
        
        # Populate advanced metrics categories
        for metric_name, metric in current_metrics.items():
            if metric.category == 'services':
                dashboard_overview["services_status"][metric.name] = {
                    "value": metric.value,
                    "unit": metric.unit,
                    "status": "online" if metric.value > 0.5 else "offline",
                    "metadata": metric.metadata
                }
            
            elif metric.category == 'performance':
                dashboard_overview["performance_indicators"][metric.name] = {
                    "value": metric.value,
                    "unit": metric.unit
                }
            
            elif metric.category == 'knowledge_base':
                dashboard_overview["knowledge_base_stats"][metric.name] = {
                    "value": metric.value,
                    "unit": metric.unit
                }
        
        return dashboard_overview
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard overview: {str(e)}")


@router.post("/metrics/collection/start")
async def start_advanced_metrics_collection():
    """Start continuous advanced metrics collection"""
    try:
        collector = get_metrics_collector()
        
        if collector._is_collecting:
            return {
                "status": "already_running",
                "message": "Advanced metrics collection is already active"
            }
        
        # Start collection in background
        asyncio.create_task(collector.start_collection())
        
        # Give it a moment to start
        await asyncio.sleep(0.5)
        
        return {
            "status": "started",
            "message": "Advanced metrics collection started successfully",
            "interval_seconds": collector._collection_interval
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start metrics collection: {str(e)}")


@router.post("/metrics/collection/stop")
async def stop_advanced_metrics_collection():
    """Stop continuous advanced metrics collection"""
    try:
        collector = get_metrics_collector()
        
        if not collector._is_collecting:
            return {
                "status": "not_running",
                "message": "Advanced metrics collection is not currently active"
            }
        
        await collector.stop_collection()
        
        return {
            "status": "stopped",
            "message": "Advanced metrics collection stopped successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop metrics collection: {str(e)}")


@router.get("/metrics/collection/status")
async def get_advanced_collection_status():
    """Get current advanced metrics collection status"""
    try:
        collector = get_metrics_collector()
        
        status = {
            "is_collecting": collector._is_collecting,
            "collection_interval": collector._collection_interval,
            "retention_hours": collector._retention_hours,
            "buffer_size": len(collector._metrics_buffer),
            "buffer_max_size": collector._metrics_buffer.maxlen
        }
        
        # Add recent collection stats
        recent_metrics = await collector.get_recent_metrics(minutes=5)
        if recent_metrics:
            status["recent_collections"] = len(recent_metrics)
            status["last_collection"] = max(m.timestamp for m in recent_metrics)
        else:
            status["recent_collections"] = 0
            status["last_collection"] = None
        
        return status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get collection status: {str(e)}")


@router.get("/alerts/check")
async def check_advanced_system_alerts():
    """Check for system alerts based on advanced metrics"""
    try:
        collector = get_metrics_collector()
        current_metrics = await collector.collect_all_metrics()
        
        # Define alert rules
        alert_rules = [
            {"metric": "cpu_percent", "threshold": 90, "comparison": "gt", "severity": "warning"},
            {"metric": "memory_percent", "threshold": 90, "comparison": "gt", "severity": "warning"},
            {"metric": "disk_usage", "threshold": 85, "comparison": "gt", "severity": "warning"},
            {"metric": "disk_usage", "threshold": 95, "comparison": "gt", "severity": "critical"},
        ]
        
        # Check for service health alerts
        for metric_name, metric in current_metrics.items():
            if 'health' in metric_name and metric.category == 'services':
                if metric.value < 1.0:
                    alert_rules.append({
                        "metric": metric_name,
                        "threshold": 1.0,
                        "comparison": "lt",
                        "severity": "critical"
                    })
        
        # Check alerts
        active_alerts = []
        for rule in alert_rules:
            metric_name = rule["metric"]
            if metric_name in current_metrics:
                metric = current_metrics[metric_name]
                threshold = rule["threshold"]
                comparison = rule["comparison"]
                
                alert_triggered = False
                if comparison == "gt" and metric.value > threshold:
                    alert_triggered = True
                elif comparison == "lt" and metric.value < threshold:
                    alert_triggered = True
                elif comparison == "eq" and metric.value == threshold:
                    alert_triggered = True
                
                if alert_triggered:
                    active_alerts.append({
                        "metric": metric_name,
                        "current_value": metric.value,
                        "threshold": threshold,
                        "comparison": comparison,
                        "severity": rule["severity"],
                        "message": f"{metric_name} is {metric.value}{metric.unit} (threshold: {threshold}{metric.unit})",
                        "timestamp": metric.timestamp
                    })
        
        return {
            "alerts_count": len(active_alerts),
            "alerts": active_alerts,
            "system_status": "critical" if any(a["severity"] == "critical" for a in active_alerts) 
                           else "warning" if active_alerts 
                           else "healthy"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check system alerts: {str(e)}")
