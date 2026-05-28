# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Celery Application Configuration for AutoBot IaC Platform

This module configures Celery for asynchronous Ansible playbook execution
with real-time event streaming and task routing.

Issue #725: Added mTLS support for Redis connections.
"""

import urllib.parse
from pathlib import Path

from celery import Celery
from celery.schedules import crontab

from autobot_shared.logging_manager import get_logger as _get_logger
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
    # #6702: resolve cert paths (explicit env vars first, legacy cert_dir fallback)
    from autobot_shared.tls import get_internal_tls_context

    _ca_cert = ssot_config.misc.tls_ca_path
    _client_cert = ssot_config.misc.tls_cert_path
    _client_key = ssot_config.misc.tls_key_path

    # Fallback to legacy cert_dir pattern for backwards compatibility
    if not _ca_cert or not _client_cert or not _client_key:
        _project_root = Path(__file__).parent.parent
        _cert_dir = ssot_config.tls.cert_dir
        _ca_cert = str(_project_root / _cert_dir / "ca" / "ca-cert.pem")
        _client_cert = str(_project_root / _cert_dir / "main-host" / "server-cert.pem")
        _client_key = str(_project_root / _cert_dir / "main-host" / "server-key.pem")

    _ssl_context = get_internal_tls_context(ca_path=_ca_cert, client_cert=_client_cert, client_key=_client_key)
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
# ssot_config env vars (CELERY_BROKER_URL / CELERY_RESULT_BACKEND) override the computed defaults
celery_app = Celery(
    "autobot",
    broker=ssot_config.celery_broker_url or _default_broker_url,
    backend=ssot_config.celery_result_backend or _default_backend_url,
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
        # GH#6505: Analytics background tasks (consolidated from BackgroundTaskManager)
        "analytics.run_import_tree_analysis": {"queue": "analytics"},
        "analytics.run_duplicate_analysis": {"queue": "analytics"},
        "analytics.run_dependency_analysis": {"queue": "analytics"},
        "analytics.run_pattern_analysis": {"queue": "analytics"},
        "analytics.run_bug_prediction_analysis": {"queue": "analytics"},
        "analytics.run_security_analysis": {"queue": "analytics"},
        "analytics.run_dashboard_analysis": {"queue": "analytics"},
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

# Auto-discover tasks from tasks and workers modules
celery_app.autodiscover_tasks(["tasks", "workers"])
# GH#6480: pricing refresh task lives in services/, not tasks/ — import explicitly so
# workers register it. autodiscover_tasks only scans the listed packages.
import services.pricing_refresh  # noqa: F401

# =========================================================================
# Issue #4455: Periodic knowledge-base cleanup schedule
# =========================================================================


def _crontab_from_string(cron_expr: str) -> crontab:
    """Parse a 5-field cron string ('m h dom mon dow') into a Celery crontab.

    Falls back to a daily 03:00 UTC schedule if the expression is malformed,
    logging a warning so misconfiguration does not prevent Beat from starting.
    """

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
    # GH#8224: detect expired active sprints and queue SPRINT_CLOSE approvals daily
    "llc-sprint-autoclose-daily": {
        "task": "llc.scheduler.sprint_autoclose.run_daily_check",
        "schedule": crontab(hour=0, minute=5),
    },
    # GH#7356: background audit daemon — testgaps, dead-code, claims
    # Beat pidfile must NOT reside on tmpfs (/run/autobot/ is wiped on reboot).
    "audit-testgaps-6h": {
        "task": "workers.audit_testgaps",
        "schedule": crontab(minute=15, hour="*/6"),  # 00:15, 06:15, 12:15, 18:15 UTC
    },
    "audit-dead-code-daily": {
        "task": "workers.audit_dead_code",
        "schedule": crontab(hour=2, minute=30),
    },
    "audit-claims-weekly": {
        "task": "workers.audit_claims",
        "schedule": crontab(hour=3, minute=0, day_of_week=1),  # Monday 03:00 UTC
    },
    # GH#6471: nightly eviction of stale per-task git worktree workspaces
    "workspace-cleanup-nightly": {
        "task": "tasks.cleanup_stale_workspaces",
        "schedule": crontab(hour=2, minute=0),
        "kwargs": {"max_age_days": 7},
    },
    # GH#6480: daily pricing refresh from provider sources into Redis (02:15 UTC)
    "pricing-refresh-daily": {
        "task": "pricing.refresh_daily",
        "schedule": crontab(hour=2, minute=15),
    },
}
