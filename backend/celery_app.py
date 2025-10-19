"""
Celery Application Configuration for AutoBot IaC Platform

This module configures Celery for asynchronous Ansible playbook execution
with real-time event streaming and task routing.
"""

from celery import Celery
import os

# Configure Celery with Redis broker and result backend
celery_app = Celery(
    "autobot",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://172.16.168.23:6379/1"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://172.16.168.23:6379/2"),
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
    worker_prefetch_multiplier=1,  # Only fetch one task at a time
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks
    # Redis visibility timeout for long-running deployments
    broker_transport_options={"visibility_timeout": 43200},  # 12 hours
    result_backend_transport_options={"visibility_timeout": 43200},
    # Task result expiration (24 hours)
    result_expires=86400,
    # Enable task events for monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Auto-discover tasks from backend.tasks module
celery_app.autodiscover_tasks(["backend.tasks"])
