# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical registry of all background schedulers in the backend (GH#6594).

This is the single source of truth for what scheduled jobs exist, how often
they run, which file owns them, and which runtime model they use.

New schedulers MUST be added here before shipping; tests/services/test_scheduler_registry.py
enforces this automatically at CI time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class ScheduledJob:
    name: str
    interval_seconds: int | str
    owner_file: str
    runtime: Literal["asyncio_per_worker", "celery_beat", "leader_elected", "apscheduler"]
    description: str


REGISTRY: list[ScheduledJob] = [
    ScheduledJob(
        name="WorkflowScheduler",
        interval_seconds=10,
        owner_file="workflow_scheduler.py",
        runtime="asyncio_per_worker",
        description=(
            "Polls for pending scheduled workflows and dispatches them when due. "
            "Tick interval is WorkflowConfig.SCHEDULER_CHECK_INTERVAL_S (10 s)."
        ),
    ),
    ScheduledJob(
        name="HeartbeatScheduler",
        interval_seconds="config:db_min_10s",
        owner_file="services/heartbeat_scheduler.py",
        runtime="asyncio_per_worker",
        description=(
            "Fires agent heartbeat runs on per-agent intervals persisted in the DB; " "minimum enforced floor is 10 s."
        ),
    ),
    ScheduledJob(
        name="ConnectorScheduler",
        interval_seconds="dynamic",
        owner_file="knowledge/connectors/scheduler.py",
        runtime="leader_elected",
        description=(
            "Triggers knowledge connector syncs. Interval is per-connector and "
            "resolved dynamically from connector configuration."
        ),
    ),
    ScheduledJob(
        name="MeshBrainScheduler",
        interval_seconds="300/86400/604800/realtime",
        owner_file="services/mesh_brain/scheduler.py",
        runtime="asyncio_per_worker",
        description=(
            "Runs four sub-tasks: edge_sync (300 s), node_promoter (24 h), "
            "edge_discoverer (24 h), mesh_pruner (7 d), edge_learner (realtime Redis consumer). "
            "NOTE: not initialized in lifespan.py — currently inert."
        ),
    ),
    ScheduledJob(
        name="SkillHealthScheduler",
        interval_seconds=300,
        owner_file="services/skill_management/skill_health_scheduler.py",
        runtime="asyncio_per_worker",
        description=("Checks skill health every 300 s. " "NOTE: not initialized in lifespan.py — currently inert."),
    ),
    ScheduledJob(
        name="LLMKeyRotationScheduler",
        interval_seconds="config:AUTOBOT_LLM_KEY_ROTATION_INTERVAL_MINUTES",
        owner_file="services/llm_key_rotation_scheduler.py",
        runtime="apscheduler",
        description=(
            "Auto-revokes expired LLM API keys. Interval (in minutes) comes from "
            "the AUTOBOT_LLM_KEY_ROTATION_INTERVAL_MINUTES environment variable."
        ),
    ),
    ScheduledJob(
        name="BackupScheduler",
        interval_seconds=86400,
        owner_file="backup/scheduler.py",
        runtime="asyncio_per_worker",
        description=(
            "Daily knowledge-base backup. Wakes once per day at AUTOBOT_BACKUP_SCHEDULE_HOUR "
            "(default 02:00 UTC) and calls KnowledgeBase.create_backup(). "
            "Implemented in GH#7912."
        ),
    ),
    ScheduledJob(
        name="CeleryBeat:cleanup_orphans",
        interval_seconds="config:SSOT_CRON",
        owner_file="celery_app.py",
        runtime="celery_beat",
        description=(
            "Removes orphaned knowledge base entries. Schedule from "
            "ssot_config.knowledge_orphan_cleanup_schedule (crontab)."
        ),
    ),
    ScheduledJob(
        name="CeleryBeat:cleanup_generated",
        interval_seconds="config:SSOT_CRON",
        owner_file="celery_app.py",
        runtime="celery_beat",
        description=(
            "Removes generated knowledge files. Schedule from "
            "ssot_config.knowledge_generated_files_cleanup_schedule (crontab)."
        ),
    ),
    ScheduledJob(
        name="CeleryBeat:prune_sync_queue",
        interval_seconds="config:SSOT_CRON",
        owner_file="celery_app.py",
        runtime="celery_beat",
        description=(
            "Prunes completed entries from the knowledge sync queue. Schedule from "
            "ssot_config.knowledge_sync_queue_prune_schedule (crontab)."
        ),
    ),
]
