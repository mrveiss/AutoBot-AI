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
from typing import Literal, get_args

# GH#12836: the set of valid runtimes lives here and nowhere else. It used to be
# restated by hand in the tests, including a hand-maintained *subset*
# (_LIFESPAN_RUNTIMES) that gates the #12810 startup-enforcement check. Adding a
# runtime to the Literal and forgetting the subset silently exempted every job
# using it from the gate — the exact "registered but inert" failure that gate
# exists to catch, reintroduced through a stale copy.
SchedulerRuntime = Literal["asyncio_per_worker", "celery_beat", "leader_elected", "apscheduler"]

#: Every valid runtime, derived from the type so the two can never drift.
SCHEDULER_RUNTIMES: frozenset[str] = frozenset(get_args(SchedulerRuntime))

#: Runtimes whose jobs are launched from ``initialization/lifespan.py`` and are
#: therefore subject to the startup-enforcement check.
LIFESPAN_RUNTIMES: frozenset[str] = frozenset({"asyncio_per_worker", "leader_elected", "apscheduler"})

#: Runtimes launched by something other than lifespan, and exempt from that check.
#: ``celery_beat`` jobs come from the Celery beat schedule.
NON_LIFESPAN_RUNTIMES: frozenset[str] = frozenset({"celery_beat"})


@dataclass
class ScheduledJob:
    """One background job, and — for lifespan-run jobs — proof that it starts.

    GH#12810: registration alone never made a job run. ``SkillHealthScheduler`` and
    ``MeshBrainScheduler`` were both registered, described, and dead, with the fact
    buried in prose in ``description``. Every lifespan-run job must now declare
    either ``startup_marker`` (a symbol that must appear in ``initialization/lifespan.py``)
    or ``inert_reason`` (a deliberate, stated decision not to run it).
    ``tests/services/test_scheduler_registry.py`` enforces exactly one of the two,
    so "registered but silently inert" cannot ship again.

    GH#12820: ``default_enabled`` is what the job does with no operator override
    present — the default an operator toggle departs from, and the value the
    resolver falls back to when Redis is unreachable. Jobs declared inert default
    to ``False``; every other default is set to preserve exactly what runs today.
    """

    name: str
    interval_seconds: int | str
    owner_file: str
    runtime: SchedulerRuntime
    description: str
    startup_marker: str | None = None
    inert_reason: str | None = None
    default_enabled: bool = True


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
        startup_marker="get_workflow_scheduler",
    ),
    ScheduledJob(
        name="HeartbeatScheduler",
        interval_seconds="config:db_min_10s",
        owner_file="services/heartbeat_scheduler.py",
        runtime="asyncio_per_worker",
        description=(
            "Fires agent heartbeat runs on per-agent intervals persisted in the DB; " "minimum enforced floor is 10 s."
        ),
        startup_marker="_init_heartbeat_scheduler",
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
        startup_marker="_start_connector_scheduler",
    ),
    ScheduledJob(
        name="MeshBrainScheduler",
        interval_seconds="300/86400/604800/realtime",
        owner_file="services/mesh_brain/scheduler.py",
        runtime="asyncio_per_worker",
        description=(
            "Runs four sub-tasks: edge_sync (300 s), node_promoter (24 h), "
            "edge_discoverer (24 h), mesh_pruner (7 d), edge_learner (realtime Redis consumer)."
        ),
        startup_marker="initialization/lifespan.py::_init_mesh_brain_scheduler",
        inert_reason=(
            "Wired in lifespan (#12816) but DEFAULT-OFF via "
            "AUTOBOT_MESH_BRAIN_SCHEDULER_ENABLED. mesh_pruner deletes data on a 7-day "
            "cadence, so ENABLING it remains a data-retention decision — the wiring gap "
            "is closed, the retention call is not."
        ),
        default_enabled=False,
    ),
    ScheduledJob(
        name="SkillHealthScheduler",
        interval_seconds=300,
        owner_file="services/skill_management/skill_health_scheduler.py",
        runtime="asyncio_per_worker",
        description=(
            "Checks skill health every 300 s and auto-disables skills below the health "
            "threshold. Started as a background task in lifespan.py (GH#12810) — its "
            "start() is an infinite loop, so it is spawned, never awaited."
        ),
        startup_marker="_init_skill_health_scheduler",
    ),
    ScheduledJob(
        name="SkillDistillationScheduler",
        interval_seconds="config:AUTOBOT_SKILL_DISTILLATION_INTERVAL_S",
        owner_file="services/skill_management/skill_distillation_scheduler.py",
        runtime="leader_elected",
        description=(
            "Distils conversations finished since the last run into proposed skills "
            "(SkillExtractor -> SkillProposer). Leader-elected so N workers do not each "
            "propose the same skill; cursor advances only after a proposal returns. "
            "Interval defaults to 3600 s and remains the backstop, but since #13695 a pass "
            "also runs early once the chat corpus has been quiet for "
            "AUTOBOT_SKILL_DISTILLATION_IDLE_FLUSH_S (default 900 s) and work is pending — "
            "so the effective cadence is at most one extra pass per idle window, not hourly. "
            "Gated off by default behind AUTOBOT_SKILL_DISTILLATION_ENABLED. "
            "Wired in lifespan.py (GH#12809)."
        ),
        startup_marker="_init_skill_distillation_scheduler",
        # Ships off: an hourly pass costs real LLM tokens, so it is opt-in (GH#12809).
        default_enabled=False,
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
        startup_marker="_init_llm_key_rotation_scheduler",
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
        startup_marker="_init_backup_scheduler",
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
    ScheduledJob(
        name="LLCHeartbeatScheduler",
        interval_seconds=5,
        owner_file="llc/scheduler/heartbeat_scheduler.py",
        runtime="asyncio_per_worker",
        description=(
            "Preferred agent-heartbeat dispatcher (GH#8225). Polls the "
            "llc:heartbeat:schedule Redis sorted set every 5 s and fires due "
            "agent heartbeat runs. Started in initialization/lifespan."
            "_init_heartbeat_scheduler; the legacy services/heartbeat_scheduler.py "
            "is the fallback when the LLC package is unavailable."
        ),
        startup_marker="_init_heartbeat_scheduler",
    ),
    ScheduledJob(
        name="LLCRoutineScheduler",
        interval_seconds=5,
        owner_file="llc/scheduler/routine_scheduler.py",
        runtime="asyncio_per_worker",
        description=(
            "Fires cron-based routines (GH#8229). Loads ACTIVE routines into the "
            "llc:heartbeat:schedule sorted set and polls every 5 s for due entries. "
            "Started in initialization/lifespan._init_llc_routine_scheduler."
        ),
        startup_marker="_init_llc_routine_scheduler",
    ),
    ScheduledJob(
        name="CommunityClusteringScheduler",
        interval_seconds=6 * 3600,
        owner_file="llc/scheduler/community_cluster_scheduler.py",
        runtime="asyncio_per_worker",
        description=(
            "Rebuilds mesh communities and promotes each community's highest-degree "
            "node to an anchor, so NeuralMeshRetriever's anchor seeding stays fresh "
            "(GH#4834, GH#13210). Runs every 6 h after a 300 s startup delay, over the "
            "MeshDB adapter on app.state.mesh_db; skipped when that adapter is absent. "
            "Started in initialization/lifespan._start_community_clustering_loop."
        ),
        startup_marker="_start_community_clustering_loop",
    ),
]
