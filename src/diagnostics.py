import os
import json
import time
import traceback
import asyncio
from collections import defaultdict
from typing import Dict, Any, Optional, List
import psutil

from src.llm_interface import LLMInterface
from src.event_manager import event_manager

# Import the centralized ConfigManager
from src.config import config as global_config_manager


class Diagnostics:
    def __init__(self):
        # Remove config_path and direct config loading
        self.llm_interface = (
            LLMInterface()
        )  # LLMInterface now uses global_config_manager

        self.reliability_stats_file = global_config_manager.get_nested(
            "data.reliability_stats_file",
            os.getenv("AUTOBOT_RELIABILITY_STATS_FILE", "data/reliability_stats.json"),
        )
        self.diagnostics_enabled = global_config_manager.get_nested(
            "diagnostics.enabled", True
        )
        self.use_llm_for_analysis = global_config_manager.get_nested(
            "diagnostics.use_llm_for_analysis", True
        )
        self.use_web_search_for_analysis = global_config_manager.get_nested(
            "diagnostics.use_web_search_for_analysis", False
        )
        self.auto_apply_fixes = global_config_manager.get_nested(
            "diagnostics.auto_apply_fixes", False
        )

        self.reliability_stats = self._load_reliability_stats()
        self.pending_fix_permission: Dict[str, asyncio.Future] = {}
        self.gpu_monitoring_enabled = False
        try:
            import pynvml

            pynvml.nvmlInit()
            self.gpu_monitoring_enabled = True
            print("pynvml initialized. GPU monitoring enabled.")
        except ImportError:
            print(
                "pynvml not found. GPU monitoring disabled. Install with 'pip install pynvml' for NVIDIA GPU monitoring."
            )
        except Exception as e:
            print(f"Failed to initialize pynvml: {e}. GPU monitoring disabled.")

    def _load_reliability_stats(self) -> Dict[str, Dict[str, Any]]:
        stats = defaultdict(lambda: {"successes": 0, "failures": 0})
        if os.path.exists(self.reliability_stats_file):
            with open(self.reliability_stats_file, "r") as f:
                loaded_stats = json.load(f)
                for k, v in loaded_stats.items():
                    stats[k] = v
        return stats

    def _save_reliability_stats(self):
        os.makedirs(os.path.dirname(self.reliability_stats_file), exist_ok=True)
        with open(self.reliability_stats_file, "w") as f:
            json.dump(self.reliability_stats, f, indent=2)

    async def log_failure(
        self, task_info: Dict[str, Any], error_message: str, tb: Optional[str] = None
    ):
        if not self.diagnostics_enabled:
            return

        failure_log = {
            "timestamp": time.time(),
            "task_info": task_info,
            "error_message": error_message,
            "traceback": tb,
            "status": "failed",
        }
        await event_manager.publish("task_failure_logged", failure_log)
        print(f"Task failure logged: {json.dumps(failure_log, indent=2)}")

        task_type = task_info.get("type", "unknown_task")
        self.reliability_stats[task_type]["failures"] += 1
        self._save_reliability_stats()

    async def log_success(self, task_info: Dict[str, Any]):
        if not self.diagnostics_enabled:
            return
        task_type = task_info.get("type", "unknown_task")
        self.reliability_stats[task_type]["successes"] += 1
        self._save_reliability_stats()

    async def analyze_failure(
        self, task_info: Dict[str, Any], error_message: str, tb: Optional[str] = None
    ) -> Dict[str, Any]:
        analysis_report = {
            "task_id": task_info.get("task_id", "N/A"),
            "task_type": task_info.get("type", "N/A"),
            "error_message": error_message,
            "suggested_causes": [],
            "suggested_strategies": [],
            "web_search_results": [],
        }

        if self.use_llm_for_analysis:
            llm_prompt = f"Analyze the following error from a task execution. Suggest possible causes and potential solutions. Error: {error_message}\nTraceback:\n{tb}\nTask Info: {json.dumps(task_info)}"
            messages = [
                {
                    "role": "system",
                    "content": "You are an AI diagnostics expert. Provide concise analysis and solutions.",
                },
                {"role": "user", "content": llm_prompt},
            ]
            llm_response = await self.llm_interface.chat_completion(
                llm_type="orchestrator",
                messages=messages,
                temperature=0.5,
                max_tokens=1000,
            )
            if llm_response and llm_response.get("choices"):
                analysis_report["suggested_causes"].append(
                    f"LLM Analysis: {llm_response['choices'][0]['message']['content']}"
                )
            else:
                analysis_report["suggested_causes"].append("LLM analysis failed.")

        if self.use_web_search_for_analysis:
            try:
                analysis_report["web_search_results"].append(
                    {
                        "title": "Simulated Web Search Result",
                        "url": "http://example.com/fix",
                        "snippet": "Found a common fix for this type of error.",
                    }
                )
            except Exception as e:
                analysis_report["web_search_results"].append(f"Web search failed: {e}")

        analysis_report["suggested_strategies"].append(
            "Retry task with exponential backoff."
        )
        analysis_report["suggested_strategies"].append(
            "Try alternative tool/backend (based on reliability stats)."
        )
        analysis_report["suggested_strategies"].append(
            "Rewrite plan to avoid problematic step."
        )

        await event_manager.publish("diagnostics_report", analysis_report)
        print(f"Diagnostics report generated: {json.dumps(analysis_report, indent=2)}")
        return analysis_report

    async def request_user_permission(self, report: Dict[str, Any]) -> bool:
        if self.auto_apply_fixes:
            await event_manager.publish(
                "log_message",
                {
                    "level": "INFO",
                    "message": "Auto-applying fixes is enabled. Skipping user permission.",
                },
            )
            return True

        task_id = report.get("task_id", "N/A")
        permission_future = asyncio.Future()
        self.pending_fix_permission[task_id] = permission_future

        await event_manager.publish(
            "user_permission_request",
            {
                "task_id": task_id,
                "report": report,
                "question": "A task failed. Do you approve applying the suggested fixes?",
            },
        )
        print(f"Requested user permission for task {task_id}. Waiting...")

        try:
            permission_granted = await asyncio.wait_for(permission_future, timeout=600)
            return permission_granted
        except asyncio.TimeoutError:
            await event_manager.publish(
                "log_message",
                {
                    "level": "WARNING",
                    "message": f"User permission for task {task_id} timed out. Fixes not applied.",
                },
            )
            return False
        finally:
            del self.pending_fix_permission[task_id]

    def set_user_permission(self, task_id: str, granted: bool):
        if task_id in self.pending_fix_permission:
            self.pending_fix_permission[task_id].set_result(granted)
            print(f"User permission for task {task_id} set to: {granted}")
        else:
            print(f"No pending permission request for task {task_id}.")

    def get_system_metrics(self) -> Dict[str, Any]:
        metrics = {}

        metrics["cpu_percent"] = psutil.cpu_percent(interval=0.1)

        virtual_memory = psutil.virtual_memory()
        metrics["ram_total_gb"] = round(virtual_memory.total / (1024**3), 2)
        metrics["ram_used_gb"] = round(virtual_memory.used / (1024**3), 2)
        metrics["ram_percent"] = virtual_memory.percent

        metrics["gpu_info"] = []
        if self.gpu_monitoring_enabled:
            try:
                import pynvml

                device_count = pynvml.nvmlDeviceGetCount()
                for i in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    gpu_name = pynvml.nvmlDeviceGetName(handle)
                    memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)

                    gpu_metrics = {
                        "id": i,
                        "name": gpu_name,
                        "vram_total_gb": round(
                            int(memory_info.total) / (1024**3), 2
                        ),  # Cast to int
                        "vram_used_gb": round(
                            int(memory_info.used) / (1024**3), 2
                        ),  # Cast to int
                        "vram_percent": round(
                            (int(memory_info.used) / int(memory_info.total)) * 100, 2
                        ),  # Cast to int
                        "gpu_utilization_percent": utilization.gpu,
                        "memory_utilization_percent": utilization.memory,
                    }
                    metrics["gpu_info"].append(gpu_metrics)
            except Exception as e:
                print(f"Error collecting GPU metrics: {e}")
                metrics["gpu_info"] = [
                    {
                        "error": str(e),
                        "message": "Could not retrieve GPU metrics. Ensure NVIDIA drivers are installed and pynvml is functioning.",
                    }
                ]
        else:
            metrics["gpu_info"].append(
                {
                    "message": "GPU monitoring is not enabled or pynvml is not installed/initialized."
                }
            )

        return metrics

    def get_reliability_stats(self) -> Dict[str, Any]:
        return dict(self.reliability_stats)
