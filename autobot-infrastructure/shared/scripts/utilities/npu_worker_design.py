#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Native NPU Worker Design for AutoBot
Hybrid architecture: WSL2 main system + Windows NPU worker for optimal performance
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class TaskType(Enum):
    """Types of tasks suitable for NPU processing."""

    CHAT_INFERENCE = "chat_inference"
    EMBEDDING_GENERATION = "embedding_generation"
    LIGHTWEIGHT_REASONING = "lightweight_reasoning"
    TEXT_CLASSIFICATION = "text_classification"
    SENTIMENT_ANALYSIS = "sentiment_analysis"
    SMALL_MODEL_INFERENCE = "small_model_inference"


@dataclass
class NPUTask:
    """NPU task definition."""

    task_id: str
    task_type: TaskType
    model_name: str
    input_data: Dict[str, Any]
    priority: int = 1
    timeout_seconds: int = 30

    def to_dict(self) -> Dict[str, Any]:
        """Convert NPU task to dictionary representation."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "model_name": self.model_name,
            "input_data": self.input_data,
            "priority": self.priority,
            "timeout_seconds": self.timeout_seconds,
        }


class NPUWorkerArchitecture:
    """Design for Native NPU Worker architecture."""

    def __init__(self):
        """Initialize NPU worker architecture design specification."""
        self.architecture = {
            "overview": {
                "concept": "Hybrid AutoBot with dedicated NPU worker on Windows host",
                "main_system": "WSL2 (orchestration, GPU workloads, storage)",
                "npu_worker": "Native Windows (NPU-optimized inference)",
                "communication": "TCP/HTTP API + Redis queue",
                "benefits": [
                    "Access to Intel NPU hardware acceleration",
                    "Optimal task distribution (NPU for small models, GPU for large)",
                    "Maintains WSL2 development environment",
                    "True hardware utilization of Intel Core Ultra",
                ],
            },
            "components": self.get_components(),
            "task_distribution": self.get_task_distribution(),
            "communication_protocol": self.get_communication_protocol(),
            "deployment_strategy": self.get_deployment_strategy(),
            "performance_optimization": self.get_performance_optimization(),
        }

    def get_components(self) -> Dict[str, Any]:
        """Define system components."""
        return {
            "wsl2_main_system": {
                "role": "Primary orchestration and heavy compute",
                "components": [
                    "AutoBot Orchestrator (main coordinator)",
                    "FastAPI Backend (web interface)",
                    "Vue Frontend (user interface)",
                    "Redis (task queue + data storage)",
                    "GPU-based agents (RAG, Research, Large models)",
                    "System Commands Agent",
                    "File Manager",
                    "ChromaDB (vector database)",
                ],
                "models": [
                    "artifish/llama3.2-uncensored:latest (2.2GB) - GPU",
                    "deepseek-r1:14b (8.4GB) - GPU for complex reasoning",
                    "llama3.2:3b-instruct-q4_K_M (2GB) - GPU backup",
                ],
            },
            "windows_npu_worker": {
                "role": "Fast, efficient small model inference",
                "components": [
                    "NPU Task Processor",
                    "OpenVINO NPU Runtime",
                    "Task Queue Client (Redis connection)",
                    "Model Cache Manager",
                    "Health Monitor",
                ],
                "models": [
                    "llama3.2:1b-instruct-q4_K_M (807MB) - Chat Agent",
                    "nomic-embed-text (274MB) - Embeddings",
                    "Custom NPU-optimized models",
                ],
                "hardware": [
                    "Intel Core Ultra 9 185H NPU",
                    "OpenVINO NPU plugin",
                    "Native Windows NPU drivers",
                ],
            },
        }

    def get_task_distribution(self) -> Dict[str, Any]:
        """Define which tasks go to which system."""
        return {
            "npu_worker_tasks": {
                "description": "Fast, lightweight tasks ideal for NPU",
                "task_types": [
                    "Chat conversations (1B model)",
                    "Text embeddings generation",
                    "System command understanding",
                    "Quick knowledge retrieval queries",
                    "Text classification/sentiment",
                    "Simple Q&A tasks",
                ],
                "characteristics": [
                    "Model size < 2GB",
                    "Response time < 2 seconds required",
                    "High frequency, low complexity",
                    "Power-efficient processing needed",
                ],
            },
            "wsl2_gpu_tasks": {
                "description": "Complex, resource-intensive tasks",
                "task_types": [
                    "Document analysis (RAG)",
                    "Web research with Playwright",
                    "Complex reasoning (14B models)",
                    "Code generation/analysis",
                    "Multi-document synthesis",
                    "Vector database operations",
                ],
                "characteristics": [
                    "Model size > 2GB",
                    "Complex multi-step reasoning",
                    "Parallel processing beneficial",
                    "Memory-intensive operations",
                ],
            },
            "routing_logic": {
                "decision_factors": [
                    "Model size requirement",
                    "Expected response time",
                    "Task complexity",
                    "Available hardware capacity",
                    "Power consumption preference",
                ],
                "fallback_strategy": "WSL2 GPU handles NPU tasks if NPU unavailable",
            },
        }

    def get_communication_protocol(self) -> Dict[str, Any]:
        """Define communication between WSL2 and NPU worker."""
        return {
            "redis_queue_system": {
                "queue_names": [
                    "npu_tasks_pending",
                    "npu_tasks_processing",
                    "npu_tasks_completed",
                    "npu_tasks_failed",
                ],
                "message_format": {
                    "task_id": "uuid4",
                    "task_type": "TaskType enum",
                    "model_name": "string",
                    "input_data": "dict",
                    "priority": "int (1-10)",
                    "timeout_seconds": "int",
                    "created_at": "ISO timestamp",
                    "worker_id": "string",
                },
            },
            "http_api": {
                "npu_worker_endpoints": [
                    "POST /npu/inference - Direct inference request",
                    "GET /npu/health - Worker health status",
                    "GET /npu/models - Available NPU models",
                    "POST /npu/model/load - Load specific model",
                    "GET /npu/stats - Performance statistics",
                ],
                "authentication": "API key or JWT tokens",
                "network": "Host network bridge (WSL2 ↔ Windows)",
            },
            "monitoring": {
                "heartbeat_interval": "10 seconds",
                "task_timeout_handling": "Automatic failover to GPU",
                "performance_metrics": [
                    "NPU utilization %",
                    "Task processing time",
                    "Queue depth",
                    "Error rate",
                    "Power consumption",
                ],
            },
        }

    def get_deployment_strategy(self) -> Dict[str, Any]:
        """Deployment and setup strategy."""
        return {
            "setup_steps": {
                "windows_host": [
                    "1. Install Intel NPU drivers",
                    "2. Install OpenVINO with NPU support",
                    "3. Deploy NPU worker service",
                    "4. Configure Windows service auto-start",
                    "5. Setup Redis client connection to WSL2",
                    "6. Pull and optimize NPU models",
                ],
                "wsl2_system": [
                    "1. Configure Redis for external connections",
                    "2. Add NPU worker client to orchestrator",
                    "3. Update task routing logic",
                    "4. Configure firewall rules",
                    "5. Test hybrid communication",
                ],
            },
            "network_configuration": {
                "wsl2_redis_bind": "0.0.0.0:6379 (accessible from Windows)",
                "npu_worker_port": "8080 (health/management API)",
                "security": "Redis AUTH + API keys",
                "firewall_rules": [
                    "Allow WSL2 ↔ Windows host communication",
                    "Block external Redis access",
                ],
            },
            "model_distribution": {
                "strategy": "Pull models on both systems",
                "npu_models": [
                    "ollama pull llama3.2:1b-instruct-q4_K_M",
                    "ollama pull nomic-embed-text",
                    "Convert to OpenVINO NPU format",
                ],
                "synchronization": "Version tracking in Redis",
            },
        }

    def get_performance_optimization(self) -> Dict[str, Any]:
        """Performance optimization strategies."""
        return {
            "npu_optimizations": {
                "model_format": "OpenVINO IR format for NPU",
                "quantization": "INT8 for maximum NPU efficiency",
                "batch_processing": "Process multiple small requests together",
                "model_caching": "Keep 1B and embedding models resident",
                "memory_management": "Efficient NPU memory usage",
            },
            "load_balancing": {
                "strategy": "Least-loaded worker selection",
                "failover": "GPU takes over if NPU overwhelmed",
                "priority_queuing": "High-priority tasks first",
                "circuit_breaker": "Disable NPU if error rate > 10%",
            },
            "monitoring_integration": {
                "metrics_collection": [
                    "NPU utilization via Intel tools",
                    "Task completion time",
                    "Queue wait time",
                    "Power consumption",
                    "Thermal throttling events",
                ],
                "alerts": [
                    "NPU worker disconnected",
                    "High error rate",
                    "Queue backlog",
                    "Performance degradation",
                ],
            },
            "expected_performance": {
                "chat_response_time": "0.5-1.5 seconds (vs 2-4s on CPU)",
                "embedding_generation": "10-50ms per text (vs 100-200ms)",
                "power_efficiency": "5-10W NPU vs 50-100W GPU",
                "concurrent_requests": "2-4 simultaneous on NPU",
                "availability": "99.9% with GPU fallback",
            },
        }

    def generate_architecture_file(self) -> str:
        """Generate comprehensive architecture documentation."""
        return json.dumps(self.architecture, indent=2, default=str)

    def print_summary(self):
        """Print architecture summary."""
        print("🏗️  AutoBot Hybrid NPU Worker Architecture")
        print("=" * 60)
        print("\n📋 Concept:")
        print(f"   {self.architecture['overview']['concept']}")

        print("\n🎯 Benefits:")
        for benefit in self.architecture["overview"]["benefits"]:
            print(f"   ✅ {benefit}")

        print("\n🔄 Task Distribution:")
        npu_tasks = self.architecture["task_distribution"]["npu_worker_tasks"]
        print(f"   NPU Worker: {', '.join(npu_tasks['task_types'][:3])}...")

        gpu_tasks = self.architecture["task_distribution"]["wsl2_gpu_tasks"]
        print(f"   WSL2 GPU: {', '.join(gpu_tasks['task_types'][:3])}...")

        print("\n⚡ Expected Performance:")
        perf = self.architecture["performance_optimization"]["expected_performance"]
        print(f"   Chat Response: {perf['chat_response_time']}")
        print(f"   Power Usage: {perf['power_efficiency']}")
        print(f"   Availability: {perf['availability']}")


if __name__ == "__main__":
    architecture = NPUWorkerArchitecture()
    architecture.print_summary()

    # Generate full architecture file
    with open("/home/kali/Desktop/AutoBot/NPU_WORKER_ARCHITECTURE.json", "w") as f:
        f.write(architecture.generate_architecture_file())

    print("\n📄 Full architecture saved to NPU_WORKER_ARCHITECTURE.json")
