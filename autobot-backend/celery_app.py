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

from celery import Celery
from config import UnifiedConfigManager

from autobot_shared.ssot_config import config as ssot_config

# Create singleton config instance for extended config values
config = UnifiedConfigManager()

# Build Redis URLs from SSOT configuration (loads directly from .env)
# Environment variables take precedence, then SSOT config-based construction
_redis_host = ssot_config.vm.redis
_redis_password = ssot_config.redis.password
_celery_broker_db = config.get("redis.databases.celery_broker", 1)
_celery_results_db = config.get("redis.databases.celery_results", 2)

# Issue #725: Check if TLS is enabled for Redis connections
_redis_tls_enabled = ssot_config.tls.redis_tls_enabled
_redis_port = (
    ssot_config.tls.redis_tls_port if _redis_tls_enabled else ssot_config.port.redis
)
_redis_scheme = "rediss" if _redis_tls_enabled else "redis"

# Build SSL context for TLS connections - Issue #725, #164
_broker_ssl_options = None
_backend_ssl_options = None

if _redis_tls_enabled:
    # Check for explicit cert paths first (set by SLM enable-tls playbook)
    _ca_cert = os.getenv("AUTOBOT_TLS_CA_PATH")
    _client_cert = os.getenv("AUTOBOT_TLS_CERT_PATH")
    _client_key = os.getenv("AUTOBOT_TLS_KEY_PATH")

    # Fallback to legacy cert_dir pattern for backwards compatibility
    if not _ca_cert or not _client_cert or not _client_key:
        _project_root = Path(__file__).parent.parent
        _cert_dir = os.getenv("AUTOBOT_TLS_CERT_DIR", "certs")
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
    _default_broker_url = (
        f"{_redis_scheme}://{_redis_host}:{_redis_port}/{_celery_broker_db}"
    )
    _default_backend_url = (
        f"{_redis_scheme}://{_redis_host}:{_redis_port}/{_celery_results_db}"
    )

# Get Celery-specific configuration
_celery_config = config.get("celery", {})
_visibility_timeout = _celery_config.get(
    "visibility_timeout", 43200
)  # 12 hours default
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
        # Issue #687: RBAC initialization tasks
        "tasks.initialize_rbac": {"queue": "deployments"},
        # Issue #544: System update tasks
        "tasks.run_system_update": {"queue": "deployments"},
        "tasks.check_available_updates": {"queue": "deployments"},
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

# Auto-discover tasks from backend.tasks module
celery_app.autodiscover_tasks(["backend.tasks"])
