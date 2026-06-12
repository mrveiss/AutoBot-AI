#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Default configuration generation for unified config manager.

SSOT Migration (Issue #639):
    Default values now source from SSOT config (ssot_config.py) when available,
    with fallback to NetworkConstants for backward compatibility.
"""

from typing import Any, Dict

from autobot_shared.ssot_config import config
from config.registry import ConfigRegistry


def _get_backend_config(llm_host: str, llm_port: int, bind_host: str, backend_port: int) -> Dict[str, Any]:
    """Get backend LLM and server configuration.

    Args:
        llm_host: LLM service host (provider-agnostic, defaults to Ollama endpoint)
        llm_port: LLM service port
        bind_host: Server bind address
        backend_port: Backend API port
    """
    # Lazy import to avoid circular dependency
    from constants.model_constants import ModelConstants

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
                        "selected_model": config.llm.default_model or ModelConstants.DEFAULT_OLLAMA_MODEL,
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
                        "selected_model": config.llm.embedding_model or "nomic-embed-text",
                    }
                },
            },
        },
        "server_host": bind_host,
        "server_port": config.port.backend,
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
            "db": config.redis.db_knowledge,
            "password": config.redis.password,
        },
        "chromadb": {
            "path": config.misc.chromadb_path or "data/chromadb",
            "collection_name": config.misc.chromadb_collection or "autobot_memory",
            "hnsw": {
                "space": config.misc.hnsw_space or "cosine",
                "construction_ef": int(config.misc.hnsw_construction_ef or "300"),
                "search_ef": int(config.misc.hnsw_search_ef or "100"),
                "M": int(config.misc.hnsw_m or "32"),
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
            "default_resolution": config.misc.desktop_resolution or "1024x768",
            "default_depth": int(config.misc.desktop_depth or "24"),
            "max_sessions": int(config.misc.desktop_max_sessions or "10"),
        },
    }


def _get_prompt_compression_config() -> Dict[str, Any]:
    """Get prompt compression configuration for LLM optimization.

    Issue #620.
    """
    return {
        "enabled": config.misc.prompt_compression_enabled if config.misc.prompt_compression_enabled else True,
        "target_ratio": float(config.misc.prompt_compression_ratio or "0.7"),
        "min_length": int(config.misc.prompt_compression_min_length or "100"),
        "preserve_code_blocks": True,
        "aggressive_mode": False,
    }


def _get_cloud_optimization_config() -> Dict[str, Any]:
    """Get cloud-specific LLM optimization configuration.

    Issue #620.
    """
    return {
        "connection_pool_size": config.misc.cloud_connection_pool_size or 100,
        "batch_window_ms": config.misc.cloud_batch_window_ms or 50,
        "max_batch_size": config.misc.cloud_max_batch_size or 10,
        "retry_max_attempts": config.misc.cloud_retry_max_attempts or 3,
        "retry_base_delay": float(config.misc.cloud_retry_base_delay or "1.0"),
        "retry_max_delay": float(config.misc.cloud_retry_max_delay or "60.0"),
    }


def _get_local_optimization_config() -> Dict[str, Any]:
    """Get local-specific LLM optimization configuration (vLLM/Ollama).

    Issue #620.
    """
    return {
        "speculation_enabled": (
            config.misc.speculation_enabled if config.misc.speculation_enabled is not None else False
        ),
        "speculation_draft_model": config.misc.speculation_draft_model or "",
        "speculation_num_tokens": config.misc.speculation_num_tokens or 5,
        "speculation_use_ngram": (
            config.misc.speculation_use_ngram if config.misc.speculation_use_ngram is not None else False
        ),
        "quantization_type": config.misc.quantization_type or "none",
        "vllm_multi_step": config.misc.vllm_multi_step or 8,
        "vllm_prefix_caching": config.misc.vllm_prefix_caching if config.misc.vllm_prefix_caching is not None else True,
        "vllm_async_output": config.misc.vllm_async_output if config.misc.vllm_async_output is not None else True,
    }


def _get_llm_optimization_config() -> Dict[str, Any]:
    """Get LLM optimization configuration (Issue #717).

    Issue #620: Refactored to extract helper methods.
    """
    return {
        "optimization": {
            "prompt_compression": _get_prompt_compression_config(),
            "cache": {
                "enabled": config.misc.cache_enabled if config.misc.cache_enabled is not None else True,
                "l1_size": config.misc.cache_l1_size or 100,
                "l2_ttl": config.misc.cache_l2_ttl or 300,
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
        "network": {
            "share": {"username": None, "password": None}
        },  # nosec B105 - default config with None values; real password provided via env
    }


def _get_deployment_config(redis_host: str, backend_port: int) -> Dict[str, Any]:
    """Get deployment configuration section.

    Issue #620.

    Args:
        redis_host: Redis server host
        backend_port: Backend API port
    """
    return {
        "mode": "local",
        "host": redis_host,
        "port": config.port.backend,
    }


def _get_redis_config(redis_host: str, redis_port: int) -> Dict[str, Any]:
    """Get Redis connection configuration section.

    Issue #620.

    Args:
        redis_host: Redis server host
        redis_port: Redis server port
    """
    return {
        "host": redis_host,
        "port": redis_port,
        "db": config.redis.db_main,
        "password": config.redis.password,
    }


def _get_celery_config() -> Dict[str, Any]:
    """Get Celery task queue configuration section.

    Issue #620.
    """
    return {
        "visibility_timeout": config.misc.celery_visibility_timeout or 43200,
        "result_expires": config.misc.celery_result_expires or 86400,
        "worker_prefetch_multiplier": 1,
        "worker_max_tasks_per_child": 100,
    }


def _get_task_transport_config(redis_host: str, redis_port: int) -> Dict[str, Any]:
    """Get task transport configuration section.

    Issue #620.

    Args:
        redis_host: Redis server host
        redis_port: Redis server port
    """
    return {
        "type": "redis",
        "redis": {
            "host": redis_host,
            "port": redis_port,
            "password": config.redis.password,
            "db": config.redis.db_tasks,
        },
    }


def get_default_config() -> Dict[str, Any]:
    """Get default configuration values.

    Issue #763: Now uses ConfigRegistry with fallback to NetworkConstants.
    Issue #620: Refactored to use extracted helpers.

    Note: LLM host/port are provider-agnostic. The default provider is Ollama,
    but agents can override via their individual configurations.
    """
    from constants.network_constants import NetworkConstants

    llm_host = ConfigRegistry.get("vm.llm", NetworkConstants.AI_STACK_HOST)
    llm_port = int(ConfigRegistry.get("port.llm", str(NetworkConstants.OLLAMA_PORT)))
    redis_host = ConfigRegistry.get("vm.redis", NetworkConstants.REDIS_VM_IP)
    redis_port = int(ConfigRegistry.get("port.redis", str(NetworkConstants.REDIS_PORT)))
    bind_host = NetworkConstants.BIND_ALL_INTERFACES
    backend_port = NetworkConstants.BACKEND_PORT

    config_dict = {
        "backend": _get_backend_config(llm_host, llm_port, bind_host, backend_port),
        "deployment": _get_deployment_config(redis_host, backend_port),
        "redis": _get_redis_config(redis_host, redis_port),
        "celery": _get_celery_config(),
        "memory": _get_memory_config(redis_host, redis_port),
        "multimodal": _get_multimodal_config(),
        "hardware": _get_hardware_config(),
        "system": _get_system_config(),
        "task_transport": _get_task_transport_config(redis_host, redis_port),
    }
    config_dict.update(_get_simple_configs())
    config_dict.update(_get_llm_optimization_config())  # Issue #717
    return config_dict
