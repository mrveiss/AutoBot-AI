# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import asyncio
import json
import logging
import os
import platform
import subprocess  # nosec B404 - required for GPU detection
import sys
from typing import Any, Dict, Optional

import psutil

from constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)

# Constants for unit conversions and hardware detection
BYTES_PER_GB = 1024**3  # Bytes to gigabytes conversion
NVIDIA_SMI_EXPECTED_FIELDS = 6  # Expected field count from nvidia-smi CSV output

# Conditional torch import for environments without CUDA
try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    logger.warning("PyTorch not available or CUDA libraries missing")
    TORCH_AVAILABLE = False
    torch = None

# Import the centralized ConfigManager and Redis client utility
from config import config as global_config_manager
from event_manager import event_manager
from knowledge_base import KnowledgeBase
from llm_interface import LLMInterface
from security_layer import SecurityLayer
from system_integration import SystemIntegration
from task_handlers import TaskExecutor
from autobot_shared.redis_client import get_redis_client

# Conditional import for GUIController based on OS
if sys.platform.startswith("linux"):
    from gui_controller_dummy import GUIController

    GUI_AUTOMATION_SUPPORTED = False
else:
    from gui_controller import GUIController

    GUI_AUTOMATION_SUPPORTED = True


class WorkerNode:
    def __init__(self):
        """
        Initialize a worker node with task execution capabilities.

        Sets up task transport (Redis or local), initializes core modules
        (LLM, knowledge base, GUI, system integration, security), and
        creates the task executor using the Strategy Pattern.
        """
        self.worker_id = f"worker_{os.getpid()}"

        self.task_transport_type = global_config_manager.get_nested(
            "task_transport.type", "local"
        )
        self.redis_client = None
        if self.task_transport_type == "redis":
            # Use centralized Redis client utility
            self.redis_client = get_redis_client(async_client=False)
            if self.redis_client:
                logger.info("Worker connected to Redis via centralized utility")
            else:
                logger.error(
                    "Worker failed to get Redis client from centralized utility"
                )
        else:
            logger.info(
                "Worker node configured for local task transport. "
                "No Redis connection."
            )

        # Initialize modules that worker might need for task execution
        self.llm_interface = LLMInterface()
        self.knowledge_base = KnowledgeBase()
        self.gui_controller = GUIController()
        self.system_integration = SystemIntegration()
        self.security_layer = SecurityLayer()

        # Initialize the task executor with Strategy Pattern
        self.task_executor = TaskExecutor(self)

    def detect_capabilities(self) -> Dict[str, Any]:
        """Detects and returns hardware and software capabilities."""
        capabilities = self._get_basic_system_info()
        capabilities.update(self._detect_gpu_capabilities())
        capabilities.update(self._detect_openvino_capabilities())
        capabilities.update(self._detect_onnx_capabilities())
        capabilities.update(self._detect_llm_backends())
        return capabilities

    def get_system_capabilities(self) -> Dict[str, Any]:
        """Alias for detect_capabilities() - for backward compatibility."""
        return self.detect_capabilities()

    def _get_basic_system_info(self) -> Dict[str, Any]:
        """Get basic system information."""
        return {
            "worker_id": self.worker_id,
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "cpu": {
                "count": psutil.cpu_count(logical=True),
                "physical_count": psutil.cpu_count(logical=False),
                "usage_percent": psutil.cpu_percent(interval=1),
                "freq_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else "N/A",
            },
            "ram": {
                "total_gb": round(psutil.virtual_memory().total / BYTES_PER_GB, 2),
                "available_gb": round(
                    psutil.virtual_memory().available / BYTES_PER_GB, 2
                ),
                "usage_percent": psutil.virtual_memory().percent,
            },
            "kb_supported": True,
            "gui_automation_supported": GUI_AUTOMATION_SUPPORTED,
        }

    def _detect_gpu_capabilities(self) -> Dict[str, Any]:
        """Detect GPU and CUDA capabilities."""
        gpu_info = {
            "gpu": {
                "cuda_available": TORCH_AVAILABLE and torch.cuda.is_available(),
                "cuda_devices": [],
            }
        }

        if gpu_info["gpu"]["cuda_available"] and TORCH_AVAILABLE:
            gpu_info["gpu"]["cuda_devices"] = self._get_cuda_device_info()
            nvidia_details = self._get_nvidia_smi_details()
            if nvidia_details:
                gpu_info["gpu"]["nvidia_smi_details"] = nvidia_details

        return gpu_info

    def _get_cuda_device_info(self) -> list:
        """Get CUDA device information."""
        devices = []
        for i in range(torch.cuda.device_count()):
            devices.append(
                {
                    "name": torch.cuda.get_device_name(i),
                    "memory_gb": round(
                        torch.cuda.get_device_properties(i).total_memory / BYTES_PER_GB,
                        2,
                    ),
                }
            )
        return devices

    def _get_nvidia_smi_details(self) -> list:
        """Get detailed GPU information using nvidia-smi."""
        try:
            nvidia_smi_output = (
                subprocess.check_output(  # nosec B607 - nvidia-smi is safe
                    [
                        "nvidia-smi",
                        "--query-gpu=name,memory.total,memory.used,memory.free,"
                        "utilization.gpu,utilization.memory",
                        "--format=csv,noheader,nounits",
                    ]
                )
                .decode()
                .strip()
                .split("\n")
            )

            gpu_details = []
            for line in nvidia_smi_output:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) == NVIDIA_SMI_EXPECTED_FIELDS:
                    gpu_details.append(
                        {
                            "name": parts[0],
                            "memory_total_mb": int(parts[1]),
                            "memory_used_mb": int(parts[2]),
                            "memory_free_mb": int(parts[3]),
                            "gpu_util_percent": int(parts[4]),
                            "mem_util_percent": int(parts[5]),
                        }
                    )
            return gpu_details
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []

    def _detect_openvino_capabilities(self) -> Dict[str, Any]:
        """Detect OpenVINO capabilities."""
        try:
            from openvino.runtime import Core

            core = Core()
            available_devices = core.available_devices

            npu_devices = [d for d in available_devices if "NPU" in d]
            gpu_devices = [d for d in available_devices if "GPU" in d]

            if npu_devices:
                logger.info("NPU acceleration available: %s", npu_devices)
            if gpu_devices:
                logger.info("OpenVINO GPU acceleration available: %s", gpu_devices)

            return {
                "openvino_available": True,
                "openvino_devices": available_devices,
                "openvino_npu_available": len(npu_devices) > 0,
                "openvino_gpu_available": len(gpu_devices) > 0,
                "openvino_npu_devices": npu_devices,
                "openvino_gpu_devices": gpu_devices,
            }
        except ImportError:
            return {"openvino_available": False}
        except Exception as e:
            logger.warning("OpenVINO detection error: %s", e)
            return {"openvino_available": False}

    def _detect_onnx_capabilities(self) -> Dict[str, Any]:
        """Detect ONNX runtime capabilities."""
        try:
            import onnxruntime as rt

            return {
                "onnxruntime_available": True,
                "onnxruntime_providers": rt.get_available_providers(),
            }
        except ImportError:
            return {"onnxruntime_available": False}

    def _detect_llm_backends(self) -> Dict[str, Any]:
        """Detect available LLM backends."""
        backends = ["ollama"]

        if self.llm_interface.openai_api_key:
            backends.append("openai")
        if global_config_manager.get_nested("llm_config.transformers.model_path"):
            backends.append("transformers")

        return {"llm_backends_supported": backends}

    async def report_capabilities(self):
        """
        Report worker capabilities to orchestrator via Redis or event system.

        Publishes detected capabilities (LLM backends, features) to allow
        the orchestrator to assign appropriate tasks to this worker.
        """
        capabilities = self.detect_capabilities()
        if self.redis_client:
            channel = "worker_capabilities"
            # Issue #361 - avoid blocking
            await asyncio.to_thread(
                self.redis_client.publish, channel, json.dumps(capabilities)
            )
            logger.info("Worker capabilities reported to Redis channel '%s'.", channel)
        else:
            logger.debug("Worker capabilities detected (local mode): %s", capabilities)
            await event_manager.publish("worker_capability_report", capabilities)

    def _validate_user_role(
        self, task_type: str, task_id: str, user_role: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Validate that user_role is provided for task execution.

        Args:
            task_type: Type of task being executed
            task_id: Unique identifier for the task
            user_role: Role of user requesting task execution

        Returns:
            Error dict if validation fails, None if valid. Issue #620.
        """
        if user_role:
            return None
        self.security_layer.audit_log(
            f"execute_task_{task_type}",
            "unknown",
            "denied",
            {"task_id": task_id, "reason": "no_user_role_provided"},
        )
        return {
            "status": "error",
            "message": "Task rejected: user_role is required but not provided.",
        }

    def _check_task_permission(
        self,
        task_type: str,
        task_id: str,
        task_payload: Dict[str, Any],
        user_role: str,
    ) -> Optional[Dict[str, Any]]:
        """Check if user has permission to execute the task type.

        Args:
            task_type: Type of task being executed
            task_id: Unique identifier for the task
            task_payload: Full task payload for audit logging
            user_role: Role of user requesting task execution

        Returns:
            Error dict if permission denied, None if allowed. Issue #620.
        """
        if self.security_layer.check_permission(user_role, f"allow_{task_type}"):
            return None
        self.security_layer.audit_log(
            f"execute_task_{task_type}",
            user_role,
            "denied",
            {
                "task_id": task_id,
                "payload": task_payload,
                "reason": "permission_denied",
            },
        )
        return {
            "status": "error",
            "message": (
                f"Permission denied for role '{user_role}' to execute "
                f"task type '{task_type}'."
            ),
        }

    async def execute_task(self, task_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a task using the Strategy Pattern for clean delegation.

        This method delegates to specialized task handlers via TaskExecutor
        after validating user role and permissions.

        Args:
            task_payload: Task data including type and parameters

        Returns:
            Dict with status, message, and any result data
        """
        task_type = task_payload.get("type")
        task_id = task_payload.get("task_id", "N/A")
        user_role = task_payload.get("user_role")

        # Validate user role (Issue #744: no guest fallback for security)
        role_error = self._validate_user_role(task_type, task_id, user_role)
        if role_error:
            return role_error

        # Check task permission
        perm_error = self._check_task_permission(
            task_type, task_id, task_payload, user_role
        )
        if perm_error:
            return perm_error

        await self._publish_task_start(task_id, task_type, user_role)

        # Delegate to TaskExecutor - Strategy Pattern dispatch
        result = await self.task_executor.execute(task_payload, user_role, task_id)

        await self._publish_task_completion(task_id, result)
        return result

    async def _publish_task_start(
        self, task_id: str, task_type: str, user_role: str
    ) -> None:
        """Publish task start event and log execution start. Issue #620."""
        await event_manager.publish(
            "worker_task_start",
            {"worker_id": self.worker_id, "task_id": task_id, "type": task_type},
        )
        logger.info(
            "Worker %s executing task %s of type '%s' for role '%s'",
            self.worker_id,
            task_id,
            task_type,
            user_role,
        )

    async def _publish_task_completion(
        self, task_id: str, result: Dict[str, Any]
    ) -> None:
        """Publish task completion event and log result. Issue #620."""
        await event_manager.publish(
            "worker_task_end",
            {"worker_id": self.worker_id, "task_id": task_id, "result": result},
        )
        logger.info(
            "Worker %s finished task %s with status: %s",
            self.worker_id,
            task_id,
            result["status"],
        )

    async def listen_for_tasks(self):
        """
        Listen for tasks from orchestrator and process them asynchronously.

        In Redis mode: Subscribes to 'orchestrator_tasks' channel and processes
        incoming tasks concurrently.

        In local mode: Runs indefinitely without external task listening.
        """
        if self.redis_client:
            pubsub = self.redis_client.pubsub()
            pubsub.subscribe("orchestrator_tasks")
            logger.info(
                f"Worker {self.worker_id} listening for tasks on "
                "'orchestrator_tasks' channel."
            )

            for message in pubsub.listen():
                if message["type"] == "message":
                    task_payload = json.loads(message["data"])
                    task_id = task_payload.get("task_id", "N/A")
                    logger.info("Worker %s received task: %s", self.worker_id, task_id)
                    asyncio.create_task(self._process_and_respond(task_payload))
        else:
            logger.info(
                f"Worker {self.worker_id} running in local task execution mode. "
                "No external task listening."
            )
            while True:
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_DELAY * 2)

    async def _process_and_respond(self, task_payload: Dict[str, Any]):
        """
        Process a task and publish the result back to orchestrator.

        Args:
            task_payload: Task data including type, task_id, and parameters
        """
        task_id = task_payload.get("task_id", "N/A")
        result = await self.execute_task(task_payload)

        if self.redis_client:
            response_channel = f"worker_results_{task_id}"
            # Issue #361 - avoid blocking
            await asyncio.to_thread(
                self.redis_client.publish, response_channel, json.dumps(result)
            )
            logger.debug(
                f"Worker {self.worker_id} sent result for task {task_id} to "
                f"'{response_channel}'."
            )
        else:
            pass

    async def start(self):
        """
        Start the worker node: report capabilities and begin listening for tasks.

        This is the main entry point for the worker node lifecycle.
        """
        logger.info("Worker Node %s starting...", self.worker_id)
        await self.report_capabilities()
        await self.listen_for_tasks()
