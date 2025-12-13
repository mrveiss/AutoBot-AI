#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot System Monitor - Real-time monitoring of optimized system performance.
"""

import asyncio
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict

import psutil
import requests

from src.constants.network_constants import NetworkConstants, ServiceURLs


def _check_cpu_for_npu() -> bool:
    """Check if CPU model has NPU support (Issue #315 - extracted)."""
    try:
        with open("/proc/cpuinfo", "r") as f:
            cpuinfo = f.read()
            return "Intel(R) Core(TM) Ultra" in cpuinfo
    except Exception:
        return False


def _check_wsl_environment() -> bool:
    """Check if running in WSL environment (Issue #315 - extracted)."""
    try:
        with open("/proc/version", "r") as f:
            version_info = f.read()
            return "WSL" in version_info or "Microsoft" in version_info
    except Exception:
        return False


def _check_openvino_npu() -> tuple:
    """Check OpenVINO NPU support (Issue #315 - extracted).

    Returns: (openvino_support, driver_available)
    """
    try:
        from openvino.runtime import Core
        core = Core()
        devices = core.available_devices
        npu_devices = [d for d in devices if "NPU" in d]
        if npu_devices:
            return (True, True)
        return (False, False)
    except ImportError:
        return (False, False)
    except Exception:
        return (False, False)


def _get_model_purpose_map() -> dict:
    """Get model purpose keyword mappings (Issue #315 - extracted)."""
    return {
        "embed": "Embedding/Vector Search",
        "uncensored": "General Purpose (Uncensored)",
        "1b": "Fast Chat/Commands (1B)",
        "3b": "Balanced Chat/Analysis (3B)",
        "14b": "Advanced Reasoning (14B)",
        "13b": "Advanced Reasoning (14B)",
        "instruct": "Instruction Following",
    }


class AutoBotMonitor:
    def __init__(self):
        """Initialize system monitor with backend and frontend URLs."""
        self.backend_port = os.getenv("AUTOBOT_BACKEND_PORT", NetworkConstants.BACKEND_PORT)
        self.api_base = f"http://{NetworkConstants.LOCALHOST_NAME}:{self.backend_port}"
        self.frontend_url = ServiceURLs.FRONTEND_VM  # FIXED: Frontend on VM1 (172.16.168.21), not localhost

    def get_system_health(self) -> Dict[str, Any]:
        """Get AutoBot system health status."""
        try:
            response = requests.get(f"{self.api_base}/api/system/health", timeout=5)
            if response.status_code == 200:
                return response.json()
            return {"status": "error", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_gpu_status(self) -> Dict[str, Any]:
        """Get GPU utilization status."""
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                if len(parts) >= 5:
                    return {
                        "available": True,
                        "name": parts[0].strip(),
                        "memory_used_mb": int(parts[1].strip()),
                        "memory_total_mb": int(parts[2].strip()),
                        "utilization_percent": int(parts[3].strip()),
                        "temperature_c": int(parts[4].strip()),
                        "power_draw_w": float(parts[5].strip())
                        if len(parts) > 5
                        else 0,
                    }
            return {"available": False, "error": "nvidia-smi failed"}
        except Exception as e:
            return {"available": False, "error": str(e)}

    def get_npu_status(self) -> Dict[str, Any]:
        """Get Intel NPU status and utilization (Issue #315 - refactored)."""
        try:
            npu_status = {
                "hardware_detected": _check_cpu_for_npu(),
                "driver_available": False,
                "openvino_support": False,
                "utilization_percent": 0,
                "wsl_limitation": _check_wsl_environment(),
            }

            # Check OpenVINO NPU support
            openvino_support, driver_avail = _check_openvino_npu()
            npu_status["openvino_support"] = openvino_support
            if driver_avail:
                npu_status["driver_available"] = True

            # Check for Intel NPU device files (Linux native)
            self._check_npu_device_files(npu_status)

            # Try to get NPU utilization from Intel GPU Top
            self._check_intel_gpu_top(npu_status)

            return npu_status

        except Exception as e:
            return {"error": str(e), "hardware_detected": False}

    def _check_npu_device_files(self, npu_status: Dict[str, Any]) -> None:
        """Check for NPU device files in /dev (Issue #315 - extracted)."""
        try:
            if not os.path.exists("/dev"):
                return
            for device in os.listdir("/dev"):
                if "intel_npu" in device or "npu" in device.lower():
                    npu_status["driver_available"] = True
                    return
        except Exception:
            pass

    def _check_intel_gpu_top(self, npu_status: Dict[str, Any]) -> None:
        """Check Intel GPU Top for NPU info (Issue #315 - extracted)."""
        try:
            result = subprocess.run(
                ["intel_gpu_top", "-l", "-n", "1"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                output = result.stdout
                if "NPU" in output or "Neural" in output:
                    npu_status["driver_available"] = True
        except Exception:
            pass

    def get_system_resources(self) -> Dict[str, Any]:
        """Get system resource utilization."""
        try:
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=1)
            disk = psutil.disk_usage("/")

            return {
                "cpu": {
                    "percent": cpu_percent,
                    "cores": psutil.cpu_count(),
                    "threads": psutil.cpu_count(logical=True),
                },
                "memory": {
                    "total_gb": memory.total / (1024**3),
                    "used_gb": memory.used / (1024**3),
                    "available_gb": memory.available / (1024**3),
                    "percent": memory.percent,
                },
                "disk": {
                    "total_gb": disk.total / (1024**3),
                    "used_gb": disk.used / (1024**3),
                    "free_gb": disk.free / (1024**3),
                    "percent": (disk.used / disk.total) * 100,
                },
            }
        except Exception as e:
            return {"error": str(e)}

    def check_frontend_status(self) -> Dict[str, Any]:
        """Check Vue frontend status."""
        try:
            response = requests.get(self.frontend_url, timeout=5)
            return {
                "available": response.status_code == 200,
                "status_code": response.status_code,
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    def get_ollama_models(self) -> Dict[str, Any]:
        """Get available Ollama models with accessibility testing (Issue #315 - refactored)."""
        try:
            response = requests.get("ServiceURLs.OLLAMA_LOCAL/api/tags", timeout=10)
            if response.status_code != 200:
                return {"available": False, "error": f"HTTP {response.status_code}"}

            data = response.json()
            models = [self._build_model_info(model) for model in data.get("models", [])]
            return {"available": True, "models": models, "count": len(models)}
        except Exception as e:
            return {"available": False, "error": str(e)}

    def _build_model_info(self, model: dict) -> dict:
        """Build model info dict with accessibility test (Issue #315 - extracted)."""
        model_info = {
            "name": model.get("name"),
            "size_gb": round(model.get("size", 0) / (1024**3), 2),
            "modified": model.get("modified_at"),
            "accessible": self._test_model_accessibility(model.get("name")),
            "purpose": self.get_model_purpose(model.get("name", "")),
        }
        return model_info

    def _test_model_accessibility(self, model_name: str) -> bool:
        """Test if model is accessible (Issue #315 - extracted)."""
        try:
            test_response = requests.post(
                "ServiceURLs.OLLAMA_LOCAL/api/generate",
                json={
                    "model": model_name,
                    "prompt": "test",
                    "stream": False,
                    "options": {"num_predict": 1},
                },
                timeout=10,
            )
            return test_response.status_code == 200
        except Exception:
            return False

    def get_model_purpose(self, model_name: str) -> str:
        """Determine purpose/use case of a model based on its name (Issue #315 - refactored)."""
        name_lower = model_name.lower()
        purpose_map = _get_model_purpose_map()

        for keyword, purpose in purpose_map.items():
            if keyword in name_lower:
                return purpose

        return "General Purpose"

    def _check_python_library_statuses(self) -> Dict[str, Any]:
        """
        Check status of Python libraries.

        Issue #281: Extracted from get_service_status to reduce function length.

        Returns:
            Dictionary of library status information.
        """
        services = {}

        # LlamaIndex
        try:
            import llama_index

            services["llama_index"] = {
                "installed": True,
                "version": getattr(llama_index, "__version__", "unknown"),
                "status": "available",
            }
        except ImportError:
            services["llama_index"] = {
                "installed": False,
                "status": "not_installed",
                "error": "pip install llama-index",
            }

        # LangChain
        try:
            import langchain

            services["langchain"] = {
                "installed": True,
                "version": getattr(langchain, "__version__", "unknown"),
                "status": "available",
            }
        except ImportError:
            services["langchain"] = {
                "installed": False,
                "status": "not_installed",
                "error": "pip install langchain",
            }

        # Playwright
        try:
            import playwright

            services["playwright"] = {
                "installed": True,
                "version": getattr(playwright, "__version__", "unknown"),
                "status": "available",
            }
            try:
                result = subprocess.run(
                    ["playwright", "install-deps"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                services["playwright"]["browsers_available"] = result.returncode == 0
            except Exception:
                services["playwright"]["browsers_available"] = False
        except ImportError:
            services["playwright"] = {
                "installed": False,
                "status": "not_installed",
                "error": "pip install playwright",
            }

        # ChromaDB
        try:
            import chromadb

            services["chromadb"] = {
                "installed": True,
                "version": getattr(chromadb, "__version__", "unknown"),
                "status": "available",
            }
        except ImportError:
            services["chromadb"] = {
                "installed": False,
                "status": "not_installed",
                "error": "pip install chromadb",
            }

        # OpenVINO
        try:
            import openvino
            from openvino.runtime import Core

            core = Core()
            services["openvino"] = {
                "installed": True,
                "version": getattr(openvino, "__version__", "unknown"),
                "status": "available",
                "devices": core.available_devices,
            }
        except ImportError:
            services["openvino"] = {
                "installed": False,
                "status": "not_installed",
                "error": "pip install openvino",
            }

        return services

    def _check_network_service_statuses(self) -> Dict[str, Any]:
        """
        Check status of network services.

        Issue #281: Extracted from get_service_status to reduce function length.

        Returns:
            Dictionary of service status information.
        """
        services = {}

        # Redis connection
        try:
            response = requests.get(f"{self.api_base}/api/system/health", timeout=5)
            if response.status_code == 200:
                health_data = response.json()
                services["redis"] = {
                    "installed": True,
                    "status": health_data.get("redis_status", "unknown"),
                    "search_module": health_data.get(
                        "redis_search_module_loaded", False
                    ),
                    "connection": "connected"
                    if health_data.get("redis_status") == "connected"
                    else "disconnected",
                }
            else:
                services["redis"] = {
                    "status": "api_error",
                    "error": f"HTTP {response.status_code}",
                }
        except Exception as e:
            services["redis"] = {"status": "unreachable", "error": str(e)}

        # FastAPI backend
        try:
            response = requests.get(f"{self.api_base}/docs", timeout=5)
            services["fastapi_backend"] = {
                "status": "running" if response.status_code == 200 else "error",
                "port": self.backend_port,
                "docs_accessible": response.status_code == 200,
            }
        except Exception as e:
            services["fastapi_backend"] = {"status": "not_running", "error": str(e)}

        # Vue Frontend
        try:
            response = requests.get(self.frontend_url, timeout=5)
            services["vue_frontend"] = {
                "status": "running" if response.status_code == 200 else "error",
                "port": "5173",
                "response_time_ms": round(response.elapsed.total_seconds() * 1000, 2),
            }
        except Exception as e:
            services["vue_frontend"] = {"status": "not_running", "error": str(e)}

        return services

    def get_service_status(self) -> Dict[str, Any]:
        """
        Get status of all AutoBot services.

        Issue #281: Extracted library and network service checks to
        _check_python_library_statuses() and _check_network_service_statuses()
        to reduce function length from 144 to ~20 lines.
        """
        # Issue #281: Use extracted helpers
        services = self._check_python_library_statuses()
        services.update(self._check_network_service_statuses())
        return services

    def test_inference_performance(self) -> Dict[str, Any]:
        """Test inference performance with current model."""
        try:
            test_prompt = "What is AutoBot?"
            start_time = time.time()

            response = requests.post(
                f"{self.api_base}/api/chat/message",
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
                    "tokens_per_second": "calculated"
                    if "response" in data
                    else "unknown",
                }
            return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _print_hardware_status(self) -> None:
        """
        Print GPU and NPU hardware status.

        Issue #281: Extracted from print_status_dashboard to reduce function length.
        """
        # GPU Status
        gpu = self.get_gpu_status()
        print("\n🎮 GPU Status:")
        if gpu.get("available"):
            print(f"   Device: {gpu['name']}")
            print(
                f"   Memory: {gpu['memory_used_mb']}/{gpu['memory_total_mb']} MB ({(gpu['memory_used_mb']/gpu['memory_total_mb']*100):.1f}%)"
            )
            print(f"   Utilization: {gpu['utilization_percent']}%")
            print(f"   Temperature: {gpu['temperature_c']}°C")
            if gpu.get("power_draw_w"):
                print(f"   Power Draw: {gpu['power_draw_w']:.1f}W")
        else:
            print(f"   Not Available: {gpu.get('error', 'Unknown')}")

        # NPU Status
        npu = self.get_npu_status()
        print("\n🧠 Intel AI Boost (NPU) Status:")
        if npu.get("hardware_detected"):
            print("   Hardware: ✅ Intel Core Ultra NPU detected")
            if npu.get("wsl_limitation"):
                print("   Status: ⚠️ WSL Environment - NPU drivers not accessible")
                print("   Note: NPU requires native Linux/Windows for driver access")
            elif npu.get("driver_available"):
                print("   Drivers: ✅ Available")
                print(
                    f"   OpenVINO: {'✅' if npu.get('openvino_support') else '❌'} {'Supported' if npu.get('openvino_support') else 'Not detected'}"
                )
                print(f"   Utilization: {npu.get('utilization_percent', 0)}%")
            else:
                print("   Drivers: ❌ Not installed or not accessible")
                print("   Recommendation: Install Intel NPU drivers on native system")
        else:
            print("   Hardware: ❌ No Intel NPU detected")
            print("   Current CPU: Check if NPU-capable processor")

    def _print_service_details(self, services: dict) -> None:
        """
        Print detailed service status.

        Issue #281: Extracted from print_status_dashboard to reduce function length.
        """
        print("\n🔧 Service Status:")
        for service_name, service_info in services.items():
            service_display = service_name.replace("_", " ").title()
            status = service_info.get("status", "unknown")

            if status == "available" or status == "running":
                status_icon = "✅"
                if "version" in service_info:
                    extra_info = f"(v{service_info['version']})"
                elif "port" in service_info:
                    extra_info = f"(port {service_info['port']})"
                else:
                    extra_info = ""
            elif status == "not_installed":
                status_icon = "❌"
                extra_info = f"({service_info.get('error', 'Not installed')})"
            elif status == "not_running":
                status_icon = "⏹️"
                extra_info = f"(Not running: {service_info.get('error', 'Unknown')})"
            else:
                status_icon = "⚠️"
                extra_info = f"({service_info.get('error', 'Unknown status')})"

            print(
                f"   {status_icon} {service_display}: {status.replace('_', ' ').title()} {extra_info}"
            )

            # Show additional details for specific services
            if service_name == "openvino" and service_info.get("devices"):
                print(f"      Devices: {', '.join(service_info['devices'])}")
            elif service_name == "redis" and service_info.get("search_module"):
                print(
                    f"      RediSearch: {'✅ Enabled' if service_info['search_module'] else '❌ Disabled'}"
                )
            elif service_name == "playwright" and "browsers_available" in service_info:
                print(
                    f"      Browsers: {'✅ Installed' if service_info['browsers_available'] else '❌ Missing'}"
                )
            elif service_name == "vue_frontend" and service_info.get(
                "response_time_ms"
            ):
                print(f"      Response Time: {service_info['response_time_ms']}ms")

    def _print_model_status(self) -> None:
        """
        Print LLM model status.

        Issue #281: Extracted from print_status_dashboard to reduce function length.
        """
        models = self.get_ollama_models()
        print("\n🤖 LLM Models (Ollama):")
        if models.get("available"):
            print(f"   Total Models: {models.get('count', 0)}")
            for model in models.get("models", []):
                accessible_icon = "✅" if model.get("accessible") else "❌"
                purpose = model.get("purpose", "Unknown")
                print(f"   {accessible_icon} {model['name']}")
                print(f"      Size: {model['size_gb']} GB | Purpose: {purpose}")
                if not model.get("accessible"):
                    print("      Status: Not responding to test prompts")
        else:
            print(f"   Error: {models.get('error', 'Unknown')}")

    def print_status_dashboard(self):
        """
        Print a comprehensive status dashboard.

        Issue #281: Extracted hardware, service, and model printing to
        _print_hardware_status(), _print_service_details(), and _print_model_status()
        to reduce function length from 140 to ~45 lines.
        """
        print("\n" + "=" * 80)
        print(
            f"🚀 AutoBot System Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        print("=" * 80)

        # System Health
        health = self.get_system_health()
        print(f"\n📊 System Health: {health.get('status', 'unknown').upper()}")
        if health.get("status") == "healthy":
            print(f"   LLM Model: {health.get('current_model', 'unknown')}")
            print(
                f"   Embedding Model: {health.get('current_embedding_model', 'unknown')}"
            )
            print(f"   Redis: {health.get('redis_status', 'unknown')}")
            print(f"   Ollama: {health.get('ollama', 'unknown')}")
        else:
            print(f"   Error: {health.get('message', 'Unknown error')}")

        # Issue #281: Use extracted helpers for hardware, services, and models
        self._print_hardware_status()

        # System Resources
        resources = self.get_system_resources()
        if "error" not in resources:
            print("\n💾 System Resources:")
            print(
                f"   CPU: {resources['cpu']['percent']:.1f}% ({resources['cpu']['cores']} cores)"
            )
            print(
                f"   Memory: {resources['memory']['used_gb']:.1f}/{resources['memory']['total_gb']:.1f} GB ({resources['memory']['percent']:.1f}%)"
            )
            print(
                f"   Disk: {resources['disk']['used_gb']:.1f}/{resources['disk']['total_gb']:.1f} GB ({resources['disk']['percent']:.1f}%)"
            )

        # Frontend Status
        frontend = self.check_frontend_status()
        print(
            f"\n🖥️  Frontend: {'✅ Available' if frontend.get('available') else '❌ Unavailable'}"
        )
        if not frontend.get("available") and frontend.get("error"):
            print(f"   Error: {frontend['error']}")

        # Issue #281: Use extracted helpers
        services = self.get_service_status()
        self._print_service_details(services)
        self._print_model_status()

        print("\n" + "=" * 80)

    async def monitor_loop(self, interval: int = 10):
        """Continuous monitoring loop."""
        print("🔄 Starting continuous monitoring (Ctrl+C to stop)")

        try:
            while True:
                self.print_status_dashboard()
                await asyncio.sleep(interval)
        except KeyboardInterrupt:
            print("\n\n⏹️  Monitor stopped by user")


def main():
    """Main function."""
    monitor = AutoBotMonitor()

    if len(sys.argv) > 1 and sys.argv[1] == "--continuous":
        # Run continuous monitoring
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        asyncio.run(monitor.monitor_loop(interval))
    elif len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Run performance test
        print("🧪 Running inference performance test...")
        result = monitor.test_inference_performance()
        print(f"Test Result: {result}")
    else:
        # Single status check
        monitor.print_status_dashboard()


if __name__ == "__main__":
    main()
