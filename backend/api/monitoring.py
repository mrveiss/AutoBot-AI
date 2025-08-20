"""
Real-time system monitoring API endpoints for AutoBot.
Integrates hardware monitoring into the web interface.
"""

import subprocess
import time
from datetime import datetime
from typing import Any, Dict

import psutil
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
        self.api_base = "http://localhost:8001"
        self.frontend_url = "http://localhost:5173"
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
                        npu_status[
                            "recommendation"
                        ] = "NPU requires native Windows or Linux for hardware access"
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
            response = requests.get("http://localhost:11434/api/tags", timeout=5)
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

        response = requests.post(
            "http://localhost:8001/api/chat/message",
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
