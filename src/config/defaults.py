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

from src.config.registry import ConfigRegistry


def _get_backend_config(
    llm_host: str, llm_port: int, bind_host: str, backend_port: int
) -> Dict[str, Any]:
    """Get backend LLM and server configuration.

    Args:
        llm_host: LLM service host (provider-agnostic, defaults to Ollama endpoint)
        llm_port: LLM service port
        bind_host: Server bind address
        backend_port: Backend API port
    """
    # Lazy import to avoid circular dependency
    from src.constants.model_constants import ModelConstants

    # Build provider-agnostic LLM config (default provider is Ollama)
    llm_base_url = f"http://{llm_host}:{llm_port}"

    return {
        "llm": {
            "provider_type": "local",
            "local": {
                "provider": "ollama",
                "providers": {
                    "ollama": {
                        "endpoint": f"{llm_base_url}/api/generate",
                        "host": llm_base_url,
                        "models": [],
                        "selected_model": os.getenv(
                            "AUTOBOT_DEFAULT_LLM_MODEL",
                            ModelConstants.DEFAULT_OLLAMA_MODEL,
                        ),
                    }
                },
            },
            "embedding": {
                "provider": "ollama",
                "providers": {
                    "ollama": {
                        "endpoint": f"{llm_base_url}/api/embeddings",
                        "host": llm_base_url,
                        "models": [],
                        "selected_model": os.getenv(
                            "AUTOBOT_EMBEDDING_MODEL", "nomic-embed-text"
                        ),
                    }
                },
            },
        },
        "server_host": bind_host,
        "server_port": int(os.getenv("AUTOBOT_BACKEND_PORT", str(backend_port))),
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
            "collection_name": os.getenv(
                "AUTOBOT_CHROMADB_COLLECTION", "autobot_memory"
            ),
            "hnsw": {
                "space": os.getenv("AUTOBOT_HNSW_SPACE", "cosine"),
                "construction_ef": int(
                    os.getenv("AUTOBOT_HNSW_CONSTRUCTION_EF", "300")
                ),
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
        "vision": {
            "enabled": True,
            "confidence_threshold": 0.7,
            "processing_timeout": 30,
        },
        "voice": {
            "enabled": True,
            "confidence_threshold": 0.8,
            "processing_timeout": 15,
        },
        "context": {
            "enabled": True,
            "decision_threshold": 0.9,
            "processing_timeout": 10,
        },
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


def _get_prompt_compression_config() -> Dict[str, Any]:
    """Get prompt compression configuration for LLM optimization.

    Issue #620.
    """
    return {
        "enabled": os.getenv("AUTOBOT_PROMPT_COMPRESSION_ENABLED", "true").lower()
        == "true",
        "target_ratio": float(os.getenv("AUTOBOT_PROMPT_COMPRESSION_RATIO", "0.7")),
        "min_length": int(os.getenv("AUTOBOT_PROMPT_COMPRESSION_MIN_LENGTH", "100")),
        "preserve_code_blocks": True,
        "aggressive_mode": False,
    }


def _get_cloud_optimization_config() -> Dict[str, Any]:
    """Get cloud-specific LLM optimization configuration.

    Issue #620.
    """
    return {
        "connection_pool_size": int(
            os.getenv("AUTOBOT_CLOUD_CONNECTION_POOL_SIZE", "100")
        ),
        "batch_window_ms": int(os.getenv("AUTOBOT_CLOUD_BATCH_WINDOW_MS", "50")),
        "max_batch_size": int(os.getenv("AUTOBOT_CLOUD_MAX_BATCH_SIZE", "10")),
        "retry_max_attempts": int(os.getenv("AUTOBOT_CLOUD_RETRY_MAX_ATTEMPTS", "3")),
        "retry_base_delay": float(os.getenv("AUTOBOT_CLOUD_RETRY_BASE_DELAY", "1.0")),
        "retry_max_delay": float(os.getenv("AUTOBOT_CLOUD_RETRY_MAX_DELAY", "60.0")),
    }


def _get_local_optimization_config() -> Dict[str, Any]:
    """Get local-specific LLM optimization configuration (vLLM/Ollama).

    Issue #620.
    """
    return {
        "speculation_enabled": os.getenv("AUTOBOT_SPECULATION_ENABLED", "false").lower()
        == "true",
        "speculation_draft_model": os.getenv("AUTOBOT_SPECULATION_DRAFT_MODEL", ""),
        "speculation_num_tokens": int(os.getenv("AUTOBOT_SPECULATION_NUM_TOKENS", "5")),
        "speculation_use_ngram": os.getenv(
            "AUTOBOT_SPECULATION_USE_NGRAM", "false"
        ).lower()
        == "true",
        "quantization_type": os.getenv("AUTOBOT_QUANTIZATION_TYPE", "none"),
        "vllm_multi_step": int(os.getenv("AUTOBOT_VLLM_MULTI_STEP", "8")),
        "vllm_prefix_caching": os.getenv("AUTOBOT_VLLM_PREFIX_CACHING", "true").lower()
        == "true",
        "vllm_async_output": os.getenv("AUTOBOT_VLLM_ASYNC_OUTPUT", "true").lower()
        == "true",
    }


def _get_llm_optimization_config() -> Dict[str, Any]:
    """Get LLM optimization configuration (Issue #717).

    Issue #620: Refactored to extract helper methods.
    """
    return {
        "optimization": {
            "prompt_compression": _get_prompt_compression_config(),
            "cache": {
                "enabled": os.getenv("AUTOBOT_CACHE_ENABLED", "true").lower() == "true",
                "l1_size": int(os.getenv("AUTOBOT_CACHE_L1_SIZE", "100")),
                "l2_ttl": int(os.getenv("AUTOBOT_CACHE_L2_TTL", "300")),
            },
            "cloud": _get_cloud_optimization_config(),
            "local": _get_local_optimization_config(),
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
        "npu": {
            "enabled": False,
            "device": "CPU",
            "model_path": None,
            "optimization_level": "PERFORMANCE",
        },
        "security": {
            "enable_sandboxing": True,
            "allowed_commands": [],
            "blocked_commands": ["rm -rf", "format", "delete"],
            "secrets_key": None,
            "audit_log_file": "data/audit.log",
        },
        "ui": {
            "theme": "light",
            "font_size": "medium",
            "language": "en",
            "animations": True,
        },
        "chat": {
            "auto_scroll": True,
            "max_messages": 100,
            "message_retention_days": 30,
        },
        "logging": {
            "log_level": "INFO",
            "log_to_file": True,
            "log_file_path": "logs/autobot.log",
        },
        "network": {"share": {"username": None, "password": None}},
    }


def get_default_config() -> Dict[str, Any]:
    """Get default configuration values.

    Issue #763: Now uses ConfigRegistry with fallback to NetworkConstants.

    Note: LLM host/port are provider-agnostic. The default provider is Ollama,
    but agents can override via their individual configurations.
    """
    # Lazy import to avoid circular dependency
    from src.constants.network_constants import NetworkConstants

    # LLM service configuration (provider-agnostic)
    # Default uses Ollama endpoint, but agents can use different providers
    llm_host = ConfigRegistry.get("vm.llm", NetworkConstants.AI_STACK_HOST)
    llm_port = int(ConfigRegistry.get("port.llm", str(NetworkConstants.OLLAMA_PORT)))

    # Infrastructure configuration
    redis_host = ConfigRegistry.get("vm.redis", NetworkConstants.REDIS_VM_IP)
    redis_port = int(ConfigRegistry.get("port.redis", str(NetworkConstants.REDIS_PORT)))
    bind_host = NetworkConstants.BIND_ALL_INTERFACES
    backend_port = NetworkConstants.BACKEND_PORT

    config = {
        "backend": _get_backend_config(llm_host, llm_port, bind_host, backend_port),
        "deployment": {
            "mode": "local",
            "host": redis_host,
            "port": int(os.getenv("AUTOBOT_BACKEND_PORT", str(backend_port))),
        },
        "redis": {
            "host": redis_host,
            "port": redis_port,
            "db": int(os.getenv("AUTOBOT_REDIS_DB", "0")),
            "password": os.getenv("AUTOBOT_REDIS_PASSWORD"),
        },
        "celery": {
            "visibility_timeout": int(
                os.getenv("AUTOBOT_CELERY_VISIBILITY_TIMEOUT", "43200")
            ),
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
                "host": redis_host,
                "port": redis_port,
                "password": os.getenv("AUTOBOT_REDIS_PASSWORD"),
                "db": int(os.getenv("AUTOBOT_REDIS_TASK_DB", "0")),
            },
        },
    }
    config.update(_get_simple_configs())
    config.update(_get_llm_optimization_config())  # Issue #717
    return config
