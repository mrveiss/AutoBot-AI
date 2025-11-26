# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Celery Application Configuration for AutoBot IaC Platform

This module configures Celery for asynchronous Ansible playbook execution
with real-time event streaming and task routing.
"""

import os

from celery import Celery

from src.unified_config_manager import UnifiedConfigManager

# Create singleton config instance
config = UnifiedConfigManager()

# Build Redis URLs from centralized configuration
# Environment variables take precedence, then config-based construction
_redis_host = config.get_host("redis")
_redis_port = config.get_port("redis")
_celery_broker_db = config.get("redis.databases.celery_broker", 1)
_celery_results_db = config.get("redis.databases.celery_results", 2)

_default_broker_url = f"redis://{_redis_host}:{_redis_port}/{_celery_broker_db}"
_default_backend_url = f"redis://{_redis_host}:{_redis_port}/{_celery_results_db}"

# Get Celery-specific configuration
_celery_config = config.get("celery", {})
_visibility_timeout = _celery_config.get("visibility_timeout", 43200)  # 12 hours default
_result_expires = _celery_config.get("result_expires", 86400)  # 24 hours default
_worker_prefetch = _celery_config.get("worker_prefetch_multiplier", 1)
_worker_max_tasks = _celery_config.get("worker_max_tasks_per_child", 100)

# Configure Celery with Redis broker and result backend
celery_app = Celery(
    "autobot",
    broker=os.environ.get("CELERY_BROKER_URL", _default_broker_url),
    backend=os.environ.get("CELERY_RESULT_BACKEND", _default_backend_url),
)

# Celery configuration
celery_app.conf.update(
    # Serialization settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone configuration
    timezone="UTC",
    enable_utc=True,
    # Task tracking
    task_track_started=True,
    # Task routing - route tasks to appropriate queues
    task_routes={
        "tasks.deploy_host": {"queue": "deployments"},
        "tasks.provision_ssh_key": {"queue": "provisioning"},
        "tasks.manage_service": {"queue": "services"},
    },
    # Worker configuration for long-running Ansible playbooks
    # Uses centralized config from unified_config_manager
    worker_prefetch_multiplier=_worker_prefetch,
    worker_max_tasks_per_child=_worker_max_tasks,
    # Redis visibility timeout for long-running deployments
    broker_transport_options={"visibility_timeout": _visibility_timeout},
    result_backend_transport_options={"visibility_timeout": _visibility_timeout},
    # Task result expiration
    result_expires=_result_expires,
    # Enable task events for monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Auto-discover tasks from backend.tasks module
celery_app.autodiscover_tasks(["backend.tasks"])
