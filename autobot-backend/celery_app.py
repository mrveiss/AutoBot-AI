# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Celery Application Configuration for AutoBot IaC Platform

This module configures Celery for asynchronous Ansible playbook execution
with real-time event streaming and task routing.

Issue #725: Added mTLS support for Redis connections.
"""

import os
import ssl
import urllib.parse
from pathlib import Path
from autobot_shared.logging_manager import get_logger

from celery import Celery
from celery.schedules import crontab

from autobot_shared.redis_management.types import DATABASE_MAPPING
from autobot_shared.ssot_config import config as ssot_config
from config.manager import get_config_manager

# Use singleton config instance for extended config values
config = get_config_manager()

# Build Redis URLs from SSOT configuration (loads directly from .env)
# DB numbers come from redis-databases.yaml via DATABASE_MAPPING (#2670)
_redis_host = ssot_config.vm.redis
_redis_password = ssot_config.redis.password
_celery_broker_db = DATABASE_MAPPING["celery_broker"]
_celery_results_db = DATABASE_MAPPING["celery_results"]

# Issue #725: Check if TLS is enabled for Redis connections
_redis_tls_enabled = ssot_config.tls.redis_tls_enabled
_redis_port = ssot_config.tls.redis_tls_port if _redis_tls_enabled else ssot_config.port.redis
_redis_scheme = "rediss" if _redis_tls_enabled else "redis"

# Build SSL context for TLS connections - Issue #725, #164
_broker_ssl_options = None
_backend_ssl_options = None

if _redis_tls_enabled:
    # Check for explicit cert paths first (set by SLM enable-tls playbook)
    _ca_cert = config.tls_ca_path
    _client_cert = config.tls_cert_path
    _client_key = config.tls_key_path

    # Fallback to legacy cert_dir pattern for backwards compatibility
    if not _ca_cert or not _client_cert or not _client_key:
        _project_root = Path(__file__).parent.parent
        _cert_dir = config.tls_cert_dir
        _ca_cert = str(_project_root / _cert_dir / "ca" / "ca-cert.pem")
        _client_cert = str(_project_root / _cert_dir / "main-host" / "server-cert.pem")
        _client_key = str(_project_root / _cert_dir / "main-host" / "server-key.pem")

    # Create SSL context for mTLS
    _ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    _ssl_context.load_verify_locations(_ca_cert)
    _ssl_context.load_cert_chain(_client_cert, _client_key)

    _broker_ssl_options = {"ssl": _ssl_context}
    _backend_ssl_options = {"ssl": _ssl_context}

# Construct URLs with password authentication if available
if _redis_password:
    # URL-encode the password to handle special characters (+, /, =, etc.)
    _encoded_password = urllib.parse.quote(_redis_password, safe="")
    _default_broker_url = f"{_redis_scheme}://:{_encoded_password}@{_redis_host}:{_redis_port}/{_celery_broker_db}"
    _default_backend_url = f"{_redis_scheme}://:{_encoded_password}@{_redis_host}:{_redis_port}/{_celery_results_db}"
else:
    _default_broker_url = f"{_redis_scheme}://{_redis_host}:{_redis_port}/{_celery_broker_db}"
    _default_backend_url = f"{_redis_scheme}://{_redis_host}:{_redis_port}/{_celery_results_db}"

# Get Celery-specific configuration
_celery_config = config.get("celery", {})
_visibility_timeout = _celery_config.get("visibility_timeout", 43200)  # 12 hours default
_result_expires = _celery_config.get("result_expires", 86400)  # 24 hours default
_worker_prefetch = _celery_config.get("worker_prefetch_multiplier", 1)
_worker_max_tasks = _celery_config.get("worker_max_tasks_per_child", 100)

# Configure Celery with Redis broker and result backend
celery_app = Celery(
    "autobot",
    broker=config.celery_broker_url,
    backend=config.celery_result_backend,
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
        # Issue #687: RBAC initialization tasks
        "tasks.initialize_rbac": {"queue": "deployments"},
        # Issue #544: System update tasks
        "tasks.run_system_update": {"queue": "deployments"},
        "tasks.check_available_updates": {"queue": "deployments"},
        # Issue #5073: Memory write-path tasks (off chat hot path)
        "memory.write_verbatim": {"queue": "memory"},
        "memory.extract_facts": {"queue": "memory"},
        "memory.update_graph": {"queue": "memory"},
        "memory.compact_snapshot": {"queue": "memory"},
    },
    # Worker configuration for long-running Ansible playbooks
    # Uses centralized config from unified_config_manager
    worker_prefetch_multiplier=_worker_prefetch,
    worker_max_tasks_per_child=_worker_max_tasks,
    # Redis visibility timeout for long-running deployments
    # Issue #725: Include SSL options when TLS is enabled
    broker_transport_options={
        "visibility_timeout": _visibility_timeout,
        **(_broker_ssl_options or {}),
    },
    result_backend_transport_options={
        "visibility_timeout": _visibility_timeout,
        **(_backend_ssl_options or {}),
    },
    # Task result expiration
    result_expires=_result_expires,
    # Enable task events for monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Auto-discover tasks from tasks module
celery_app.autodiscover_tasks(["tasks"])


# =========================================================================
# Issue #4455: Periodic knowledge-base cleanup schedule
# =========================================================================


def _crontab_from_string(cron_expr: str) -> crontab:
    """Parse a 5-field cron string ('m h dom mon dow') into a Celery crontab.

    Falls back to a daily 03:00 UTC schedule if the expression is malformed,
    logging a warning so misconfiguration does not prevent Beat from starting.
    """
    import logging as _logging

    _log = _get_logger(__name__)
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        _log.warning(
            "Invalid cron expression %r (expected 5 fields); falling back to '0 3 * * *'",
            cron_expr,
        )
        parts = ["0", "3", "*", "*", "*"]
    minute, hour, day_of_month, month_of_year, day_of_week = parts
    return crontab(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
    )


celery_app.conf.beat_schedule = {
    "knowledge-cleanup-orphan-documents": {
        "task": "tasks.cleanup_orphan_documents",
        "schedule": _crontab_from_string(ssot_config.knowledge_orphan_cleanup_schedule),
        "kwargs": {"dry_run": False},
    },
    "knowledge-cleanup-generated-files": {
        "task": "tasks.cleanup_generated_files",
        "schedule": _crontab_from_string(ssot_config.knowledge_generated_files_cleanup_schedule),
        "kwargs": {"dry_run": False},
    },
    # Issue #5081: prune expired entries from the doc_sync:queue:done zset
    "knowledge-sync-queue-prune": {
        "task": "tasks.prune_sync_queue_done",
        "schedule": _crontab_from_string(ssot_config.knowledge_sync_queue_prune_schedule),
    },
}
