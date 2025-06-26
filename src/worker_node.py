# src/worker_node.py
import os
import json
import time
import platform
import psutil
import subprocess
import asyncio
import redis
import yaml
import torch # For CUDA detection
import sys # Import sys
from typing import Dict, Any, Optional, List # Import missing types

from src.llm_interface import LLMInterface
from src.knowledge_base import KnowledgeBase
from src.event_manager import event_manager
from src.system_integration import SystemIntegration # Import SystemIntegration
from src.security_layer import SecurityLayer # Import SecurityLayer

# Conditional import for GUIController based on OS
if sys.platform.startswith('linux'):
    # In WSL or other Linux environments where pygetwindow might not work
    from src.gui_controller_dummy import GUIController
    GUI_AUTOMATION_SUPPORTED = False
else:
    # For Windows or macOS where pygetwindow is expected to work
    from src.gui_controller import GUIController
    GUI_AUTOMATION_SUPPORTED = True

class WorkerNode:
    def __init__(self, config_path="config/config.yaml"):
        self.config = self._load_config(config_path)
        self.task_transport_config = self.config['task_transport']
        self.worker_id = f"worker_{os.getpid()}" # Unique ID for this worker instance

        self.redis_client = None
        if self.task_transport_config['type'] == "redis":
            redis_host = self.task_transport_config['redis']['host']
            redis_port = self.task_transport_config['redis']['port']
            self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
            print(f"Worker connected to Redis at {redis_host}:{redis_port}")
        else:
            print("Worker node configured for local task transport. No Redis connection.")

        # Initialize modules that worker might need for task execution
        self.llm_interface = LLMInterface(config_path)
        self.knowledge_base = KnowledgeBase(config_path)
        self.gui_controller = GUIController() # Initialize GUIController
        self.system_integration = SystemIntegration() # Initialize SystemIntegration
        self.security_layer = SecurityLayer() # Initialize SecurityLayer

    def _load_config(self, config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def detect_capabilities(self) -> Dict[str, Any]:
        """Detects and returns hardware and software capabilities."""
        capabilities = {
            "worker_id": self.worker_id,
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "cpu": {
                "count": psutil.cpu_count(logical=True),
                "physical_count": psutil.cpu_count(logical=False),
                "usage_percent": psutil.cpu_percent(interval=1),
                "freq_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else "N/A"
            },
            "ram": {
                "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
                "usage_percent": psutil.virtual_memory().percent
            },
            "gpu": {
                "cuda_available": torch.cuda.is_available(),
                "cuda_devices": []
            },
            "openvino_available": False,
            "onnxruntime_available": False,
            "llm_backends_supported": [],
            "kb_supported": True,
            "gui_automation_supported": GUI_AUTOMATION_SUPPORTED # Indicate GUI automation capability based on conditional import
        }

        if capabilities['gpu']['cuda_available']:
            for i in range(torch.cuda.device_count()):
                capabilities['gpu']['cuda_devices'].append({
                    "name": torch.cuda.get_device_name(i),
                    "memory_gb": round(torch.cuda.get_device_properties(i).total_memory / (1024**3), 2)
                })
            try:
                nvidia_smi_output = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,utilization.memory", "--format=csv,noheader,nounits"]).decode().strip().split('\n')
                gpu_details = []
                for line in nvidia_smi_output:
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) == 6:
                        gpu_details.append({
                            "name": parts[0],
                            "memory_total_mb": int(parts[1]),
                            "memory_used_mb": int(parts[2]),
                            "memory_free_mb": int(parts[3]),
                            "gpu_util_percent": int(parts[4]),
                            "mem_util_percent": int(parts[5])
                        })
                capabilities['gpu']['nvidia_smi_details'] = gpu_details
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

        try:
            from openvino.runtime import Core
            core = Core()
            capabilities['openvino_available'] = True
            capabilities['openvino_devices'] = core.available_devices
        except ImportError:
            pass

        try:
            import onnxruntime as rt
            capabilities['onnxruntime_available'] = True
            capabilities['onnxruntime_providers'] = rt.get_available_providers()
        except ImportError:
            pass
        
        capabilities['llm_backends_supported'].append("ollama")
        if self.llm_interface.openai_api_key:
            capabilities['llm_backends_supported'].append("openai")
        if self.config['llm_config'].get('transformers', {}).get('model_path'):
            capabilities['llm_backends_supported'].append("transformers")

        return capabilities

    async def report_capabilities(self):
        capabilities = self.detect_capabilities()
        if self.redis_client:
            channel = "worker_capabilities"
            self.redis_client.publish(channel, json.dumps(capabilities))
            print(f"Worker capabilities reported to Redis channel '{channel}'.")
        else:
            print("Worker capabilities detected (local mode):", capabilities)
            await event_manager.publish("worker_capability_report", capabilities)

    async def execute_task(self, task_payload: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_payload.get("type")
        task_id = task_payload.get("task_id", "N/A")
        user_role = task_payload.get("user_role", "guest") # Default to 'guest' if not provided

        # Initial permission check for any task execution
        if not self.security_layer.check_permission(user_role, f"allow_{task_type}"):
            self.security_layer.audit_log(f"execute_task_{task_type}", user_role, "denied", {"task_id": task_id, "payload": task_payload, "reason": "permission_denied"})
            return {"status": "error", "message": f"Permission denied for role '{user_role}' to execute task type '{task_type}'."}

        await event_manager.publish("worker_task_start", {"worker_id": self.worker_id, "task_id": task_id, "type": task_type})
        print(f"Worker {self.worker_id} executing task {task_id} of type '{task_type}' for role '{user_role}'...")

        result = {"status": "error", "message": "Unknown task type."}
        try:
            if task_type == "llm_chat_completion":
                model_name = task_payload['model_name']
                messages = task_payload['messages']
                llm_kwargs = task_payload.get('kwargs', {})
                response = await self.llm_interface.chat_completion(model_name, messages, **llm_kwargs)
                if response:
                    result = {"status": "success", "message": "LLM completion successful.", "response": response}
                    self.security_layer.audit_log("llm_chat_completion", user_role, "success", {"task_id": task_id, "model": model_name})
                else:
                    result = {"status": "error", "message": "LLM completion failed."}
                    self.security_layer.audit_log("llm_chat_completion", user_role, "failure", {"task_id": task_id, "model": model_name, "reason": "llm_failed"})
            elif task_type == "kb_add_file":
                file_path = task_payload['file_path']
                file_type = task_payload['file_type']
                metadata = task_payload.get('metadata')
                kb_result = self.knowledge_base.add_file(file_path, file_type, metadata)
                result = kb_result
                self.security_layer.audit_log("kb_add_file", user_role, result.get("status", "unknown"), {"task_id": task_id, "file_path": file_path})
            elif task_type == "kb_search":
                query = task_payload['query']
                n_results = task_payload.get('n_results', 5)
                kb_results = self.knowledge_base.search(query, n_results)
                result = {"status": "success", "message": "KB search successful.", "results": kb_results}
                self.security_layer.audit_log("kb_search", user_role, "success", {"task_id": task_id, "query": query})
            elif task_type == "kb_store_fact":
                content = task_payload['content']
                metadata = task_payload.get('metadata')
                kb_result = self.knowledge_base.store_fact(content, metadata)
                result = kb_result
                self.security_layer.audit_log("kb_store_fact", user_role, result.get("status", "unknown"), {"task_id": task_id, "content_preview": content[:50]})
            elif task_type == "execute_shell_command":
                command = task_payload['command']
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                output = stdout.decode().strip()
                error = stderr.decode().strip()
                if process.returncode == 0:
                    result = {"status": "success", "message": "Command executed.", "output": output}
                    self.security_layer.audit_log("execute_shell_command", user_role, "success", {"task_id": task_id, "command": command})
                else:
                    result = {"status": "error", "message": "Command failed.", "error": error, "output": output, "returncode": process.returncode}
                    self.security_layer.audit_log("execute_shell_command", user_role, "failure", {"task_id": task_id, "command": command, "error": error})
            # New GUI automation tasks
            elif task_type == "gui_click_element":
                image_path = task_payload['image_path']
                confidence = task_payload.get('confidence', 0.9)
                button = task_payload.get('button', 'left')
                clicks = task_payload.get('clicks', 1)
                interval = task_payload.get('interval', 0.0)
                result = self.gui_controller.click_element(image_path, confidence, button, clicks, interval)
                self.security_layer.audit_log("gui_click_element", user_role, result.get("status", "unknown"), {"task_id": task_id, "image_path": image_path})
            elif task_type == "gui_read_text_from_region":
                x, y, width, height = task_payload['x'], task_payload['y'], task_payload['width'], task_payload['height']
                result = self.gui_controller.read_text_from_region(x, y, width, height)
                self.security_layer.audit_log("gui_read_text_from_region", user_role, result.get("status", "unknown"), {"task_id": task_id, "region": f"({x},{y},{width},{height})"})
            elif task_type == "gui_type_text":
                text = task_payload['text']
                interval = task_payload.get('interval', 0.0)
                result = self.gui_controller.type_text(text, interval)
                self.security_layer.audit_log("gui_type_text", user_role, result.get("status", "unknown"), {"task_id": task_id, "text_preview": text[:50]})
            elif task_type == "gui_move_mouse":
                x, y = task_payload['x'], task_payload['y']
                duration = task_payload.get('duration', 0.0)
                result = self.gui_controller.move_mouse(x, y, duration)
                self.security_layer.audit_log("gui_move_mouse", user_role, result.get("status", "unknown"), {"task_id": task_id, "coords": f"({x},{y})"})
            elif task_type == "gui_bring_window_to_front":
                app_title = task_payload['app_title']
                result = self.gui_controller.bring_window_to_front(app_title)
                self.security_layer.audit_log("gui_bring_window_to_front", user_role, result.get("status", "unknown"), {"task_id": task_id, "app_title": app_title})
            # New System Integration tasks
            elif task_type == "system_query_info":
                result = self.system_integration.query_system_info()
                self.security_layer.audit_log("system_query_info", user_role, result.get("status", "unknown"), {"task_id": task_id})
            elif task_type == "system_list_services":
                result = self.system_integration.list_services()
                self.security_layer.audit_log("system_list_services", user_role, result.get("status", "unknown"), {"task_id": task_id})
            elif task_type == "system_manage_service":
                service_name = task_payload['service_name']
                action = task_payload['action']
                result = self.system_integration.manage_service(service_name, action)
                self.security_layer.audit_log("system_manage_service", user_role, result.get("status", "unknown"), {"task_id": task_id, "service": service_name, "action": action})
            elif task_type == "system_execute_command":
                command = task_payload['command']
                result = self.system_integration.execute_system_command(command)
                self.security_layer.audit_log("system_execute_command", user_role, result.get("status", "unknown"), {"task_id": task_id, "command": command})
            elif task_type == "system_get_process_info":
                process_name = task_payload.get('process_name')
                pid = task_payload.get('pid')
                result = self.system_integration.get_process_info(process_name, pid)
                self.security_layer.audit_log("system_get_process_info", user_role, result.get("status", "unknown"), {"task_id": task_id, "process_name": process_name, "pid": pid})
            elif task_type == "system_terminate_process":
                pid = task_payload['pid']
                result = self.system_integration.terminate_process(pid)
                self.security_layer.audit_log("system_terminate_process", user_role, result.get("status", "unknown"), {"task_id": task_id, "pid": pid})
            elif task_type == "respond_conversationally":
                response_text = task_payload.get('response_text', 'No response provided.')
                await event_manager.publish("llm_response", {"response": response_text})
                result = {"status": "success", "message": "Responded conversationally."}
                self.security_layer.audit_log("respond_conversationally", user_role, "success", {"task_id": task_id, "response_preview": response_text[:50]})
            else:
                result = {"status": "error", "message": f"Unsupported task type: {task_type}"}
        except Exception as e:
            result = {"status": "error", "message": f"Error during task execution: {e}"}
            self.security_layer.audit_log(f"execute_task_{task_type}", user_role, "failure", {"task_id": task_id, "payload": task_payload, "error": str(e)})
        
        await event_manager.publish("worker_task_end", {"worker_id": self.worker_id, "task_id": task_id, "result": result})
        print(f"Worker {self.worker_id} finished task {task_id} with status: {result['status']}")
        return result

    async def listen_for_tasks(self):
        if self.redis_client:
            pubsub = self.redis_client.pubsub()
            pubsub.subscribe("orchestrator_tasks")
            print(f"Worker {self.worker_id} listening for tasks on 'orchestrator_tasks' channel.")
            
            for message in pubsub.listen():
                if message['type'] == 'message':
                    task_payload = json.loads(message['data'])
                    task_id = task_payload.get("task_id", "N/A")
                    print(f"Worker {self.worker_id} received task: {task_id}")
                    asyncio.create_task(self._process_and_respond(task_payload))
        else:
            print(f"Worker {self.worker_id} running in local task execution mode. No external task listening.")
            while True:
                await asyncio.sleep(10)

    async def _process_and_respond(self, task_payload: Dict[str, Any]):
        task_id = task_payload.get("task_id", "N/A")
        result = await self.execute_task(task_payload)
        
        if self.redis_client:
            response_channel = f"worker_results_{task_id}"
            self.redis_client.publish(response_channel, json.dumps(result))
            print(f"Worker {self.worker_id} sent result for task {task_id} to '{response_channel}'.")
        else:
            pass

    async def start(self):
        print(f"Worker Node {self.worker_id} starting...")
        await self.report_capabilities()
        await self.listen_for_tasks()

# Example Usage (for testing)
if __name__ == "__main__":
    if not os.path.exists("config/config.yaml"):
        print("config/config.yaml not found. Copying from template for testing.")
        os.makedirs("config", exist_ok=True)
        with open("config/config.yaml.template", "r") as f_template:
            with open("config/config.yaml", "w") as f_config:
                f_config.write(f_template.read())

    async def main():
        worker = WorkerNode()
        await worker.start()

    asyncio.run(main())
