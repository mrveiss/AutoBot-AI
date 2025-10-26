#!/usr/bin/env python3
"""
AutoBot System Monitor - Real-time monitoring of optimized system performance.
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict

import psutil
import requests


class AutoBotMonitor:
    def __init__(self):
        self.backend_port = os.getenv("AUTOBOT_BACKEND_PORT", "8001")
        self.api_base = f"http://localhost:{self.backend_port}"
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
        """Get Intel NPU status and utilization."""
        try:
            npu_status = {
                "hardware_detected": False,
                "driver_available": False,
                "openvino_support": False,
                "utilization_percent": 0,
                "wsl_limitation": False,
            }

            # Check CPU model for NPU support
            try:
                with open("/proc/cpuinfo", "r") as f:
                    cpuinfo = f.read()
                    if "Intel(R) Core(TM) Ultra" in cpuinfo:
                        npu_status["hardware_detected"] = True
            except Exception:
                pass

            # Check if running in WSL
            try:
                with open("/proc/version", "r") as f:
                    version_info = f.read()
                    if "WSL" in version_info or "Microsoft" in version_info:
                        npu_status["wsl_limitation"] = True
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
                    # Could attempt to get utilization here if NPU was available
            except ImportError:
                pass
            except Exception:
                pass

            # Check for Intel NPU device files (Linux native)
            try:
                import os

                npu_devices = []
                if os.path.exists("/dev"):
                    for device in os.listdir("/dev"):
                        if "intel_npu" in device or "npu" in device.lower():
                            npu_devices.append(device)
                            npu_status["driver_available"] = True
            except Exception:
                pass

            # Try to get NPU utilization from Intel GPU Top (if available)
            try:
                result = subprocess.run(
                    ["intel_gpu_top", "-l", "-n", "1"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    # Parse intel_gpu_top output for NPU info
                    output = result.stdout
                    if "NPU" in output or "Neural" in output:
                        npu_status["driver_available"] = True
                        # Parse utilization if available
            except Exception:
                pass

            return npu_status

        except Exception as e:
            return {"error": str(e), "hardware_detected": False}

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
        """Get available Ollama models with accessibility testing."""
        try:
            response = requests.get("ServiceURLs.OLLAMA_LOCAL/api/tags", timeout=10)
            if response.status_code == 200:
                data = response.json()
                models = []
                for model in data.get("models", []):
                    model_info = {
                        "name": model.get("name"),
                        "size_gb": round(model.get("size", 0) / (1024**3), 2),
                        "modified": model.get("modified_at"),
                        "accessible": False,
                        "purpose": self.get_model_purpose(model.get("name", "")),
                    }

                    # Test model accessibility
                    try:
                        test_response = requests.post(
                            "ServiceURLs.OLLAMA_LOCAL/api/generate",
                            json={
                                "model": model.get("name"),
                                "prompt": "test",
                                "stream": False,
                                "options": {"num_predict": 1},
                            },
                            timeout=10,
                        )
                        model_info["accessible"] = test_response.status_code == 200
                    except Exception:
                        model_info["accessible"] = False

                    models.append(model_info)

                return {"available": True, "models": models, "count": len(models)}
            return {"available": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"available": False, "error": str(e)}

    def get_model_purpose(self, model_name: str) -> str:
        """Determine the purpose/use case of a model based on its name."""
        name_lower = model_name.lower()
        if "embed" in name_lower:
            return "Embedding/Vector Search"
        elif "uncensored" in name_lower:
            return "General Purpose (Uncensored)"
        elif "1b" in name_lower:
            return "Fast Chat/Commands (1B)"
        elif "3b" in name_lower:
            return "Balanced Chat/Analysis (3B)"
        elif "14b" in name_lower or "13b" in name_lower:
            return "Advanced Reasoning (14B)"
        elif "instruct" in name_lower:
            return "Instruction Following"
        else:
            return "General Purpose"

    def get_service_status(self) -> Dict[str, Any]:
        """Get status of all AutoBot services."""
        services = {}

        # Test LlamaIndex
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

        # Test LangChain
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

        # Test Playwright
        try:
            import playwright

            services["playwright"] = {
                "installed": True,
                "version": getattr(playwright, "__version__", "unknown"),
                "status": "available",
            }
            # Test if browsers are installed
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

        # Test ChromaDB
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

        # Test OpenVINO
        try:
            import openvino
            from openvino.runtime import Core
            from src.constants import NetworkConstants, ServiceURLs

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

        # Test Redis connection
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

        # Test FastAPI backend
        try:
            response = requests.get(f"{self.api_base}/docs", timeout=5)
            services["fastapi_backend"] = {
                "status": "running" if response.status_code == 200 else "error",
                "port": self.backend_port,
                "docs_accessible": response.status_code == 200,
            }
        except Exception as e:
            services["fastapi_backend"] = {"status": "not_running", "error": str(e)}

        # Test Vue Frontend
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

    def print_status_dashboard(self):
        """Print a comprehensive status dashboard."""
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

        # GPU Status
        gpu = self.get_gpu_status()
        print(f"\n🎮 GPU Status:")
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
        print(f"\n🧠 Intel AI Boost (NPU) Status:")
        if npu.get("hardware_detected"):
            print(f"   Hardware: ✅ Intel Core Ultra NPU detected")
            if npu.get("wsl_limitation"):
                print(f"   Status: ⚠️ WSL Environment - NPU drivers not accessible")
                print(f"   Note: NPU requires native Linux/Windows for driver access")
            elif npu.get("driver_available"):
                print(f"   Drivers: ✅ Available")
                print(
                    f"   OpenVINO: {'✅' if npu.get('openvino_support') else '❌'} {'Supported' if npu.get('openvino_support') else 'Not detected'}"
                )
                print(f"   Utilization: {npu.get('utilization_percent', 0)}%")
            else:
                print(f"   Drivers: ❌ Not installed or not accessible")
                print(f"   Recommendation: Install Intel NPU drivers on native system")
        else:
            print(f"   Hardware: ❌ No Intel NPU detected")
            print(f"   Current CPU: Check if NPU-capable processor")

        # System Resources
        resources = self.get_system_resources()
        if "error" not in resources:
            print(f"\n💾 System Resources:")
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

        # Service Status
        services = self.get_service_status()
        print(f"\n🔧 Service Status:")
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

        # Ollama Models with detailed info
        models = self.get_ollama_models()
        print(f"\n🤖 LLM Models (Ollama):")
        if models.get("available"):
            print(f"   Total Models: {models.get('count', 0)}")
            for model in models.get("models", []):
                accessible_icon = "✅" if model.get("accessible") else "❌"
                purpose = model.get("purpose", "Unknown")
                print(f"   {accessible_icon} {model['name']}")
                print(f"      Size: {model['size_gb']} GB | Purpose: {purpose}")
                if not model.get("accessible"):
                    print(f"      Status: Not responding to test prompts")
        else:
            print(f"   Error: {models.get('error', 'Unknown')}")

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
