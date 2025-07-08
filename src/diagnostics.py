# src/diagnostics.py
import os
import json
import time
import traceback
import asyncio
import yaml
from collections import defaultdict
from typing import Dict, Any, Optional, List
import psutil # Import psutil for system monitoring

from src.llm_interface import LLMInterface
from src.event_manager import event_manager

class Diagnostics:
    def __init__(self, config_path="config/config.yaml"):
        self.config = self._load_config(config_path)
        self.diagnostics_config = self.config['diagnostics']
        self.llm_interface = LLMInterface(config_path) # For LLM-based analysis
        self.reliability_stats_file = self.diagnostics_config['reliability_stats_file']
        self.reliability_stats = self._load_reliability_stats()
        self.pending_fix_permission: Dict[str, asyncio.Future] = {} # task_id -> Future for user permission
        self.gpu_monitoring_enabled = False
        try:
            import pynvml # type: ignore
            pynvml.nvmlInit()
            self.gpu_monitoring_enabled = True
            print("pynvml initialized. GPU monitoring enabled.")
        except ImportError:
            print("pynvml not found. GPU monitoring disabled. Install with 'pip install pynvml' for NVIDIA GPU monitoring.")
        except Exception as e:
            print(f"Failed to initialize pynvml: {e}. GPU monitoring disabled.")

    def _load_config(self, config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _load_reliability_stats(self) -> Dict[str, Dict[str, Any]]:
        """Loads reliability stats from a JSON file, ensuring it's a defaultdict."""
        stats = defaultdict(lambda: {"successes": 0, "failures": 0})
        if os.path.exists(self.reliability_stats_file):
            with open(self.reliability_stats_file, 'r') as f:
                loaded_stats = json.load(f)
                for k, v in loaded_stats.items():
                    stats[k] = v
        return stats

    def _save_reliability_stats(self):
        """Saves reliability stats to a JSON file."""
        os.makedirs(os.path.dirname(self.reliability_stats_file), exist_ok=True)
        with open(self.reliability_stats_file, 'w') as f:
            json.dump(self.reliability_stats, f, indent=2)

    async def log_failure(self, task_info: Dict[str, Any], error_message: str, tb: Optional[str] = None):
        """Logs a task failure with details."""
        if not self.diagnostics_config['enabled']:
            return

        failure_log = {
            "timestamp": time.time(),
            "task_info": task_info,
            "error_message": error_message,
            "traceback": tb,
            "status": "failed"
        }
        await event_manager.publish("task_failure_logged", failure_log)
        print(f"Task failure logged: {json.dumps(failure_log, indent=2)}")

        # Update reliability stats
        task_type = task_info.get("type", "unknown_task")
        self.reliability_stats[task_type]["failures"] += 1
        self._save_reliability_stats()

    async def log_success(self, task_info: Dict[str, Any]):
        """Logs a task success for reliability tracking."""
        if not self.diagnostics_config['enabled']:
            return
        task_type = task_info.get("type", "unknown_task")
        self.reliability_stats[task_type]["successes"] += 1
        self._save_reliability_stats()

    async def analyze_failure(self, task_info: Dict[str, Any], error_message: str, tb: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyzes a failure, suggests causes using LLM/web search, and proposes strategies.
        """
        analysis_report = {
            "task_id": task_info.get("task_id", "N/A"),
            "task_type": task_info.get("type", "N/A"),
            "error_message": error_message,
            "suggested_causes": [],
            "suggested_strategies": [],
            "web_search_results": []
        }

        # LLM-based analysis
        if self.diagnostics_config['use_llm_for_analysis']:
            llm_prompt = f"Analyze the following error from a task execution. Suggest possible causes and potential solutions. Error: {error_message}\nTraceback:\n{tb}\nTask Info: {json.dumps(task_info)}"
            messages = [
                {"role": "system", "content": "You are an AI diagnostics expert. Provide concise analysis and solutions."},
                {"role": "user", "content": llm_prompt}
            ]
            llm_response = await self.llm_interface.chat_completion(
                llm_type="orchestrator", # Use orchestrator LLM for analysis
                messages=messages,
                temperature=0.5,
                max_tokens=1000
            )
            if llm_response and llm_response.get('choices'):
                analysis_report['suggested_causes'].append(f"LLM Analysis: {llm_response['choices'][0]['message']['content']}")
            else:
                analysis_report['suggested_causes'].append("LLM analysis failed.")

        # Web search for analysis (using mcp-webresearch tool)
        if self.diagnostics_config['use_web_search_for_analysis']:
            try:
                # This would ideally use the mcp-webresearch tool
                # For now, simulate a web search result
                # from mcp_servers.mcp_webresearch import search_google # This would be a direct import if it were a local module
                # search_query = f"{task_info.get('type', '')} {error_message} fix"
                # web_results = search_google(query=search_query) # Assuming this returns a list of dicts
                # analysis_report['web_search_results'] = web_results[:3] # Limit results
                analysis_report['web_search_results'].append({"title": "Simulated Web Search Result", "url": "http://example.com/fix", "snippet": "Found a common fix for this type of error."})
            except Exception as e:
                analysis_report['web_search_results'].append(f"Web search failed: {e}")

        # Suggest strategies (simple logic for now)
        analysis_report['suggested_strategies'].append("Retry task with exponential backoff.")
        analysis_report['suggested_strategies'].append("Try alternative tool/backend (based on reliability stats).")
        analysis_report['suggested_strategies'].append("Rewrite plan to avoid problematic step.")

        await event_manager.publish("diagnostics_report", analysis_report)
        print(f"Diagnostics report generated: {json.dumps(analysis_report, indent=2)}")
        return analysis_report

    async def request_user_permission(self, report: Dict[str, Any]) -> bool:
        """Sends a report to the frontend and waits for user permission."""
        if self.diagnostics_config['auto_apply_fixes']:
            await event_manager.publish("log_message", {"level": "INFO", "message": "Auto-applying fixes is enabled. Skipping user permission."})
            return True # Auto-apply if configured

        task_id = report.get("task_id", "N/A")
        permission_future = asyncio.Future()
        self.pending_fix_permission[task_id] = permission_future

        await event_manager.publish("user_permission_request", {
            "task_id": task_id,
            "report": report,
            "question": "A task failed. Do you approve applying the suggested fixes?"
        })
        print(f"Requested user permission for task {task_id}. Waiting...")

        try:
            permission_granted = await asyncio.wait_for(permission_future, timeout=600) # Wait for 10 minutes
            return permission_granted
        except asyncio.TimeoutError:
            await event_manager.publish("log_message", {"level": "WARNING", "message": f"User permission for task {task_id} timed out. Fixes not applied."})
            return False
        finally:
            del self.pending_fix_permission[task_id]

    def set_user_permission(self, task_id: str, granted: bool):
        """Sets the user's permission for a pending fix."""
        if task_id in self.pending_fix_permission:
            self.pending_fix_permission[task_id].set_result(granted)
            print(f"User permission for task {task_id} set to: {granted}")
        else:
            print(f"No pending permission request for task {task_id}.")

    def get_system_metrics(self) -> Dict[str, Any]:
        """
        Collects real-time CPU, RAM, and (if available) GPU/VRAM usage.
        """
        metrics = {}

        # CPU Usage
        metrics['cpu_percent'] = psutil.cpu_percent(interval=0.1) # Non-blocking call

        # RAM Usage
        virtual_memory = psutil.virtual_memory()
        metrics['ram_total_gb'] = round(virtual_memory.total / (1024**3), 2)
        metrics['ram_used_gb'] = round(virtual_memory.used / (1024**3), 2)
        metrics['ram_percent'] = virtual_memory.percent

        # GPU/VRAM Usage (NVIDIA only, using pynvml)
        metrics['gpu_info'] = []
        if self.gpu_monitoring_enabled:
            try:
                # Import pynvml here to ensure it's only accessed if enabled
                import pynvml # type: ignore
                device_count = pynvml.nvmlDeviceGetCount()
                for i in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    gpu_name = pynvml.nvmlDeviceGetName(handle)
                    memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)

                    gpu_metrics = {
                        'id': i,
                        'name': gpu_name,
                        'vram_total_gb': round(memory_info.total / (1024**3), 2),
                        'vram_used_gb': round(memory_info.used / (1024**3), 2),
                        'vram_percent': round((memory_info.used / memory_info.total) * 100, 2),
                        'gpu_utilization_percent': utilization.gpu,
                        'memory_utilization_percent': utilization.memory
                    }
                    metrics['gpu_info'].append(gpu_metrics)
            except Exception as e:
                print(f"Error collecting GPU metrics: {e}")
                metrics['gpu_info'] = [{"error": str(e), "message": "Could not retrieve GPU metrics. Ensure NVIDIA drivers are installed and pynvml is functioning."}]
        else:
            metrics['gpu_info'].append({"message": "GPU monitoring is not enabled or pynvml is not installed/initialized."})

        return metrics

    def get_reliability_stats(self) -> Dict[str, Any]:
        """Returns current reliability statistics."""
        return dict(self.reliability_stats) # Convert defaultdict to dict for clean return

# Example Usage (for testing)
if __name__ == "__main__":
    # Ensure config.yaml exists for testing
    if not os.path.exists("config/config.yaml"):
        print("config/config.yaml not found. Copying from template for testing.")
        os.makedirs("config", exist_ok=True)
        with open("config/config.yaml.template", "r") as f_template:
            with open("config/config.yaml", "w") as f_config:
                f_config.write(f_template.read())

    async def test_diagnostics():
        diagnostics = Diagnostics()
        
        # Simulate a task failure
        task_info = {"task_id": "task_abc", "type": "llm_chat_completion", "model": "ollama_tinyllama"}
        error_msg = "Connection refused: Ollama server not running."
        tb_str = "Traceback (most recent call last):\n  File \"<stdin>\", line 1, in <module>\nrequests.exceptions.ConnectionError: Connection refused"
        
        await diagnostics.log_failure(task_info, error_msg, tb_str)
        report = await diagnostics.analyze_failure(task_info, error_msg, tb_str)
        
        # Simulate user granting permission (for testing auto_apply_fixes=false)
        # In a real scenario, this would come from the frontend via an API call
        # diagnostics.set_user_permission("task_abc", True) 
        
        # Request user permission (will block until permission is set or timeout)
        permission_granted = await diagnostics.request_user_permission(report)
        print(f"User granted permission: {permission_granted}")

        # Simulate a task success
        await diagnostics.log_success({"task_id": "task_xyz", "type": "kb_add_file"})

        print("\nReliability Stats:")
        print(diagnostics.get_reliability_stats())

    asyncio.run(test_diagnostics())
