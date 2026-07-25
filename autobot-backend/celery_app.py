# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from celery.signals import beat_init, worker_process_init
from kombu import Queue

from autobot_shared.logging_manager import get_logger as _get_logger
from autobot_shared.redis_management.types import DATABASE_MAPPING
from autobot_shared.ssot_config import config as ssot_config
from config.manager import get_config_manager

# Use singleton config instance for extended config values
config = get_config_manager()
logger = _get_logger(__name__)

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

# GH#11262: priority tiers live in celery_priority (plain data so they can be
# unit-tested without importing this heavy, pytest-stubbed module, issue #7766).
from celery_priority import MAX_PRIORITY as _MAX_PRIORITY  # noqa: E402
from celery_priority import PRIORITY_NORMAL as _PRIORITY_NORMAL
from celery_priority import PRIORITY_TASK_ROUTES as _PRIORITY_TASK_ROUTES

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
    # GH#11262: enable priority queues so audit preempts low-priority maintenance.
    task_queue_max_priority=_MAX_PRIORITY,
    task_default_priority=_PRIORITY_NORMAL,
    # #11631: explicit queue set — a worker started WITHOUT -Q (the Ansible
    # systemd unit autobot-celery.service.j2) consumes exactly these queues;
    # Celery's default without this is the lone `celery` queue, which left
    # deployments/memory/analytics tasks unconsumed in that flavor. Every
    # queue referenced by task_routes below MUST be listed here (guarded by
    # celery_queue_coverage_test.py) or routed tasks sit in Redis forever.
    task_queues=(
        Queue("celery"),
        Queue("deployments"),
        Queue("memory"),
        Queue("analytics"),
    ),
    # Task routing - route tasks to appropriate queues
    # #11608: phantom routes for tasks.deploy_host / tasks.provision_ssh_key /
    # tasks.manage_service removed — those tasks moved to the SLM server (#729)
    # and nothing sends those names to this broker anymore. The orphaned
    # `provisioning` and `services` queues were dropped with them.
    task_routes={
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
        # GH#11262: priority tiers on the shared default queue (audit > maintenance).
        **_PRIORITY_TASK_ROUTES,
    },
    # Worker configuration for long-running Ansible playbooks
    # Uses centralized config from unified_config_manager
    worker_prefetch_multiplier=_worker_prefetch,
    worker_max_tasks_per_child=_worker_max_tasks,
    # Redis visibility timeout for long-running deployments
    # Issue #725: Include SSL options when TLS is enabled
    broker_transport_options={
        "visibility_timeout": _visibility_timeout,
        # GH#11262: drain higher-priority messages first so critical audit work
        # is not stuck behind a backlog of low-priority cleanup on the same queue.
        "queue_order_strategy": "priority",
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

# GH#12318: register every task package. autodiscover_tasks defaults to
# related_name="tasks", i.e. it imports "<pkg>.tasks" (tasks/tasks.py,
# workers/tasks.py) — neither exists, so the call was a silent no-op and only
# explicitly-imported modules registered. Beat then dispatched names (credential
# reconcile, snapshot cleanup, LLC sprint auto-close, audit daemons) to workers
# that never registered them ("Received unregistered task of type ...") and the
# jobs never ran. related_name=None imports each PACKAGE __init__ instead, which
# re-exports its task modules (tasks/__init__.py, workers/__init__.py,
# llc/scheduler/__init__.py), so their @celery_app.task / @shared_task
# decorators all run at worker/beat startup.
celery_app.autodiscover_tasks(["tasks", "workers", "llc.scheduler"], related_name=None)
# GH#6480: pricing refresh lives in services/, outside the discovered packages —
# import explicitly so workers register pricing.refresh_daily.
import services.pricing_refresh  # noqa: F401
from utils.celery_schedules import crontab_from_string  # noqa: E402

# =========================================================================
# Issue #4455: Periodic knowledge-base cleanup schedule
# Issue #11606: cron parser extracted to utils.celery_schedules so it stays
# importable when the test conftest stubs this module in sys.modules.
# =========================================================================


celery_app.conf.beat_schedule = {
    "knowledge-cleanup-orphan-documents": {
        "task": "tasks.cleanup_orphan_documents",
        "schedule": crontab_from_string(ssot_config.knowledge_orphan_cleanup_schedule),
        "kwargs": {"dry_run": False},
    },
    "knowledge-cleanup-generated-files": {
        "task": "tasks.cleanup_generated_files",
        "schedule": crontab_from_string(ssot_config.knowledge_generated_files_cleanup_schedule),
        "kwargs": {"dry_run": False},
    },
    # Issue #5081: prune expired entries from the doc_sync:queue:done zset
    "knowledge-sync-queue-prune": {
        "task": "tasks.prune_sync_queue_done",
        "schedule": crontab_from_string(ssot_config.knowledge_sync_queue_prune_schedule),
    },
    # GH#8224: detect expired active sprints and queue SPRINT_CLOSE approvals daily
    "llc-sprint-autoclose-daily": {
        "task": "llc.scheduler.sprint_autoclose.run_daily_check",
        "schedule": crontab(hour=0, minute=5),
    },
    # #11129 P2: dispose pending_disposal projects whose retention has elapsed
    "llc-project-disposal-sweep": {
        "task": "llc.scheduler.project_disposal_sweep.run_disposal_sweep",
        "schedule": crontab(hour=1, minute=0),
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
    # GH#11263: nightly trajectory-store consolidation (dedupe + prune) so
    # retrieval precision holds as the store grows. NORMAL priority (GH#11262).
    "memory-consolidate-trajectories-daily": {
        "task": "memory.consolidate_trajectories",
        "schedule": crontab(hour=4, minute=0),  # 04:00 UTC, after nightly cleanup
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
    # GH#4463: weekly cleanup of stale mobile devices (inactive for 90+ days)
    "mobile-devices-cleanup-weekly": {
        "task": "tasks.cleanup_stale_mobile_devices",
        "schedule": crontab(hour=3, minute=30, day_of_week=0),  # Sunday 03:30 UTC
        "kwargs": {"dry_run": False},
    },
    # MVA-2228: nightly snapshot cleanup (TTL-based eviction)
    "snapshot-cleanup-daily": {
        "task": "tasks.cleanup_expired_snapshots",
        "schedule": crontab(hour=3, minute=0),
    },
    # #10337: hourly reconciliation of mirrored credential copies against canonical
    # SQLite — bounds the revoke-resurrection window of the connector-store cutover (#10088).
    "reconcile-credentials-hourly": {
        "task": "tasks.reconcile_credentials",
        "schedule": crontab(minute=20),
    },
    # GH#8995: data-hygiene retention tasks (nightly, staggered to avoid Redis contention)
    # All tasks are no-ops when their respective retention_days == 0 (safe default).
    # Schedules are configurable via AUTOBOT_*_RETENTION_SCHEDULE env vars (5-field cron).
    "data-retention-chats-nightly": {
        "task": "tasks.cleanup_expired_chats",
        "schedule": crontab_from_string(getattr(ssot_config.misc, "chat_retention_schedule", None) or "0 1 * * *"),
        "kwargs": {"dry_run": False},
    },
    "data-retention-files-nightly": {
        "task": "tasks.cleanup_expired_files",
        "schedule": crontab_from_string(getattr(ssot_config.misc, "file_retention_schedule", None) or "15 1 * * *"),
        "kwargs": {"dry_run": False},
    },
    "data-retention-audit-nightly": {
        "task": "tasks.cleanup_expired_audit_logs",
        "schedule": crontab_from_string(getattr(ssot_config.misc, "audit_retention_schedule", None) or "30 1 * * *"),
        "kwargs": {"dry_run": False},
    },
    "data-retention-kb-nightly": {
        "task": "tasks.cleanup_expired_kb_entries",
        "schedule": crontab_from_string(getattr(ssot_config.misc, "kb_retention_schedule", None) or "45 1 * * *"),
        "kwargs": {"dry_run": False},
    },
    # GH#12439: single-tick dispatcher — scans BatchSchedule records every
    # minute and enqueues tasks.run_batch_job for each due+enabled schedule
    # (claims by advancing next_run before enqueue; skips a schedule whose
    # job is already running).
    "batch-schedules-tick": {
        "task": "tasks.dispatch_due_batch_schedules",
        "schedule": crontab(minute="*"),
    },
}


# GH#12318: fail loudly if Beat is configured to dispatch a task no worker will
# ever register. Force task discovery (import_default_modules runs the lazy
# autodiscover callbacks), then assert every beat_schedule entry resolves to a
# registered task. Previously such mismatches surfaced only as "Received
# unregistered task of type ..." in a log nobody reads, and four scheduled
# maintenance jobs silently never ran.
def _assert_beat_tasks_registered() -> None:
    celery_app.loader.import_default_modules()
    registered = set(celery_app.tasks)
    scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    missing = sorted(scheduled - registered)
    if missing:
        logger.critical(
            "Beat-scheduled tasks are NOT registered and will be dropped as "
            "'Received unregistered task of type ...': %s",
            missing,
        )


_assert_beat_tasks_registered()


# GH#12354: complement to _assert_beat_tasks_registered() (#12353, which guards
# the forward direction — every scheduled task is registered). This guards the
# reverse: prune any entry the on-disk PersistentScheduler store is still
# carrying whose task is no longer declared in beat_schedule, e.g. a
# renamed/removed task lingering in the shelve file. Celery's own
# PersistentScheduler already does an equivalent merge by entry NAME on every
# clean startup, but silently; this makes it explicit, task-name-based (not
# just key-based), and loud, running on the beat_init signal — i.e. only in
# the actual `celery beat` process, after Celery has finished setting up its
# scheduler (celery.beat.Service.start() accesses self.scheduler, which runs
# setup_schedule(), before it sends beat_init).
@beat_init.connect
def _reconcile_persisted_beat_schedule(sender=None, **kwargs) -> None:
    scheduler = getattr(sender, "scheduler", None)
    if scheduler is None:
        logger.warning("beat_init: no scheduler on sender %r — skipping reconciliation (#12354)", sender)
        return

    from utils.celery_beat_reconcile import reconcile_schedule

    valid_tasks = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    pruned = reconcile_schedule(scheduler.schedule, valid_tasks)
    if pruned:
        scheduler.sync()
    logger.info(
        "beat_init: %d schedule entries active after reconciliation (%d pruned: %s) — GH#12354",
        len(scheduler.schedule),
        len(pruned),
        pruned,
    )


# GH#4459: Register web-push task_success signal so tasks that pass user_id
# in their kwargs trigger a browser push notification on completion.
try:
    from services.push_notification_service import register_celery_task_success_hook

    register_celery_task_success_hook()
except ImportError:
    pass  # pywebpush not installed — push notifications disabled
except Exception:
    logger.warning("Push notification hook registration failed (GH#4459)", exc_info=True)


# Issue #10936: Reset async Redis pool state in each forked worker process.
#
# The singleton RedisConnectionManager is created before the prefork pool forks.
# After fork the child process inherits _async_pools populated from the parent's
# event loop (which no longer exists in the child).  Any async Redis call that
# tries to reuse those pools gets connections tied to the dead parent loop,
# causing get_async_client() to catch the error and return None — the
# AttributeError: 'NoneType' object has no attribute 'zrangebyscore' symptom.
#
# worker_process_init fires once inside each forked worker process, before any
# task executes, making it the correct hook for this one-time reset.  The reset
# is synchronous (no event loop required) and idempotent.
@worker_process_init.connect
def _reset_async_redis_pools_on_worker_init(sender=None, **kwargs):
    """Clear inherited async Redis pools so each worker gets its own."""
    try:
        from autobot_shared.redis_client import reset_async_redis_pools

        reset_async_redis_pools()
        logger.info("worker_process_init: async Redis pools reset for new worker process (#10936)")
    except Exception:
        logger.warning(
            "worker_process_init: async Redis pool reset failed (worker will still start)",
            exc_info=True,
        )
