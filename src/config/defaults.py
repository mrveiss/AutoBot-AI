#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Default configuration generation for unified config manager.

SSOT Migration (Issue #639):
    Default values now source from SSOT config (ssot_config.py) when available,
    with fallback to NetworkConstants for backward compatibility.
"""

import os
from typing import Any, Dict

from src.constants.model_constants import ModelConstants
from src.constants.network_constants import NetworkConstants


def _get_ssot_config():
    """Get SSOT config with graceful fallback."""
    try:
        from src.config.ssot_config import get_config
        return get_config()
    except Exception:
        return None


# Module-level SSOT reference (lazy loaded)
_ssot = None


def _get_ssot():
    """Get or create SSOT singleton reference."""
    global _ssot
    if _ssot is None:
        _ssot = _get_ssot_config()
    return _ssot


def _get_backend_config(ollama_host: str, ollama_port: int) -> Dict[str, Any]:
    """Get backend LLM and server configuration."""
    return {
        "llm": {
            "provider_type": "local",
            "local": {
                "provider": "ollama",
                "providers": {
                    "ollama": {
                        "endpoint": f"http://{ollama_host}:{ollama_port}/api/generate",
                        "host": f"http://{ollama_host}:{ollama_port}",
                        "models": [],
                        "selected_model": os.getenv(
                            "AUTOBOT_DEFAULT_LLM_MODEL", ModelConstants.DEFAULT_OLLAMA_MODEL
                        ),
                    }
                },
            },
            "embedding": {
                "provider": "ollama",
                "providers": {
                    "ollama": {
                        "endpoint": f"http://{ollama_host}:{ollama_port}/api/embeddings",
                        "host": f"http://{ollama_host}:{ollama_port}",
                        "models": [],
                        "selected_model": os.getenv("AUTOBOT_EMBEDDING_MODEL", "nomic-embed-text"),
                    }
                },
            },
        },
        "server_host": NetworkConstants.BIND_ALL_INTERFACES,
        "server_port": int(os.getenv("AUTOBOT_BACKEND_PORT", str(NetworkConstants.BACKEND_PORT))),
        "timeout": 60,
        "max_retries": 3,
        "streaming": False,
    }


def _get_memory_config(redis_host: str, redis_port: int) -> Dict[str, Any]:
    """Get memory (Redis + ChromaDB) configuration."""
    return {
        "redis": {
            "enabled": True,
            "host": redis_host,
            "port": redis_port,
            "db": int(os.getenv("AUTOBOT_REDIS_MEMORY_DB", "1")),
            "password": os.getenv("AUTOBOT_REDIS_PASSWORD"),
        },
        "chromadb": {
            "path": os.getenv("AUTOBOT_CHROMADB_PATH", "data/chromadb"),
            "collection_name": os.getenv("AUTOBOT_CHROMADB_COLLECTION", "autobot_memory"),
            "hnsw": {
                "space": os.getenv("AUTOBOT_HNSW_SPACE", "cosine"),
                "construction_ef": int(os.getenv("AUTOBOT_HNSW_CONSTRUCTION_EF", "300")),
                "search_ef": int(os.getenv("AUTOBOT_HNSW_SEARCH_EF", "100")),
                "M": int(os.getenv("AUTOBOT_HNSW_M", "32")),
            },
        },
    }


def _get_hardware_config() -> Dict[str, Any]:
    """Get hardware and NPU configuration."""
    return {
        "environment_variables": {
            "cuda_device_order": "PCI_BUS_ID",
            "gpu_max_heap_size": "100",
            "gpu_use_sync_objects": "1",
            "openvino_device_priorities": "NPU,GPU,CPU",
            "intel_npu_enabled": "1",
            "omp_num_threads": "4",
            "mkl_num_threads": "4",
            "openblas_num_threads": "4",
        },
        "acceleration": {
            "enabled": True,
            "priority_order": ["npu", "gpu", "cpu"],
            "cpu_reserved_cores": 2,
            "memory_optimization": "enabled",
        },
    }


def _get_multimodal_config() -> Dict[str, Any]:
    """Get multimodal (vision/voice/context) configuration."""
    return {
        "vision": {"enabled": True, "confidence_threshold": 0.7, "processing_timeout": 30},
        "voice": {"enabled": True, "confidence_threshold": 0.8, "processing_timeout": 15},
        "context": {"enabled": True, "decision_threshold": 0.9, "processing_timeout": 10},
    }


def _get_system_config() -> Dict[str, Any]:
    """Get system and desktop streaming configuration."""
    return {
        "environment": {"DISPLAY": ":0", "USER": "unknown", "SHELL": "unknown"},
        "desktop_streaming": {
            "default_resolution": os.getenv("AUTOBOT_DESKTOP_RESOLUTION", "1024x768"),
            "default_depth": int(os.getenv("AUTOBOT_DESKTOP_DEPTH", "24")),
            "max_sessions": int(os.getenv("AUTOBOT_DESKTOP_MAX_SESSIONS", "10")),
        },
    }


def _get_simple_configs() -> Dict[str, Any]:
    """Get simple static configurations (ui, chat, logging, security, npu, data)."""
    return {
        "data": {
            "reliability_stats_file": "data/reliability_stats.json",
            "long_term_db_path": "data/agent_memory.db",
            "chat_history_file": "data/chat_history.json",
            "chats_directory": "data/chats",
        },
        "npu": {"enabled": False, "device": "CPU", "model_path": None, "optimization_level": "PERFORMANCE"},
        "security": {
            "enable_sandboxing": True, "allowed_commands": [],
            "blocked_commands": ["rm -rf", "format", "delete"],
            "secrets_key": None, "audit_log_file": "data/audit.log",
        },
        "ui": {"theme": "light", "font_size": "medium", "language": "en", "animations": True},
        "chat": {"auto_scroll": True, "max_messages": 100, "message_retention_days": 30},
        "logging": {"log_level": "INFO", "log_to_file": True, "log_file_path": "logs/autobot.log"},
        "network": {"share": {"username": None, "password": None}},
    }


def get_default_config() -> Dict[str, Any]:
    """Get default configuration values.

    SSOT Migration (Issue #639):
        Infrastructure defaults now come from SSOT config when available.
    """
    ssot = _get_ssot()

    # Use SSOT values with fallback to NetworkConstants
    ollama_host = ssot.vm.ollama if ssot else NetworkConstants.AI_STACK_HOST
    ollama_port = ssot.port.ollama if ssot else NetworkConstants.OLLAMA_PORT
    redis_host = ssot.vm.redis if ssot else NetworkConstants.REDIS_HOST
    redis_port = ssot.port.redis if ssot else NetworkConstants.REDIS_PORT

    config = {
        "backend": _get_backend_config(ollama_host, ollama_port),
        "deployment": {
            "mode": "local",
            "host": redis_host,
            "port": int(os.getenv("AUTOBOT_BACKEND_PORT", str(NetworkConstants.BACKEND_PORT))),
        },
        "redis": {
            "host": redis_host,
            "port": redis_port,
            "db": int(os.getenv("AUTOBOT_REDIS_DB", "0")),
            "password": os.getenv("AUTOBOT_REDIS_PASSWORD"),
        },
        "celery": {
            "visibility_timeout": int(os.getenv("AUTOBOT_CELERY_VISIBILITY_TIMEOUT", "43200")),
            "result_expires": int(os.getenv("AUTOBOT_CELERY_RESULT_EXPIRES", "86400")),
            "worker_prefetch_multiplier": 1,
            "worker_max_tasks_per_child": 100,
        },
        "memory": _get_memory_config(redis_host, redis_port),
        "multimodal": _get_multimodal_config(),
        "hardware": _get_hardware_config(),
        "system": _get_system_config(),
        "task_transport": {
            "type": "redis",
            "redis": {
                "host": redis_host, "port": redis_port,
                "password": os.getenv("AUTOBOT_REDIS_PASSWORD"),
                "db": int(os.getenv("AUTOBOT_REDIS_TASK_DB", "0")),
            },
        },
    }
    config.update(_get_simple_configs())
    return config
