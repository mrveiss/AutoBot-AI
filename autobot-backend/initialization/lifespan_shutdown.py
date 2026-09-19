# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The steps of the backend's shutdown, one function each (#16250).

Moved verbatim out of ``initialization/lifespan.py``'s ``cleanup_services`` so
no function there or here is over the length limit. ``cleanup_services`` and its
three stage functions still state the ORDER -- they are the only place that does,
and ``lifespan_test.py`` and ``lifespan_shutdown_order_test.py`` pin it -- and
every step keeps its own guard, so one that fails never skips the rest.

Every import a step needs stays inside that step. Tests patch those names at
their source modules, which only works because each is looked up when the step
runs; hoisting them to module level would silently disable those patches.
"""

import asyncio
from typing import TYPE_CHECKING

from fastapi import FastAPI

from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    from initialization.lifespan import _ShutdownReport

logger = get_logger(__name__)


async def cancel_background_init_task(app: FastAPI, report: "_ShutdownReport") -> None:
    """Cancel and await the phase-2 background init task (#11679)."""
    # Issue #11679: Cancel + await the phase-2 background-init task FIRST,
    # before any other cleanup step. Without this, a fast shutdown can race
    # initialize_background_services() while it is still creating resources
    # (Redis subscriptions, background loops, etc.), voiding the "Redis
    # closed LAST" ordering guarantee below for those late-created resources.
    bg_init_task = getattr(app.state, "background_init_task", None)
    if bg_init_task is not None and not bg_init_task.done():
        bg_init_task.cancel()
        try:
            await bg_init_task
        except asyncio.CancelledError:
            pass
        except Exception as _bg_init_err:
            report.failed("Background init task raised during cancellation", _bg_init_err)
        logger.info("✅ Phase-2 background init task cancelled before shutdown")


async def shutdown_code_analysis_pool(report: "_ShutdownReport") -> None:
    """Tear down the code-analysis process pool and its children (#12866)."""
    # #12866: the code-analysis process pool holds spawned children. They are not
    # daemons, so leaving them behind keeps the unit in "deactivating" until
    # systemd's timeout expires and SIGKILLs it. Torn down here, before the
    # thread pool drains, because the shutdown call itself runs in a thread.
    try:
        from code_intelligence.shared.process_offload import shutdown_scan_pool

        await shutdown_scan_pool()
    except Exception as _pool_err:  # noqa: BLE001
        report.failed("Code-analysis process pool shutdown", _pool_err)


async def stop_state_services(app: FastAPI, report: "_ShutdownReport") -> None:
    """Close the transcriber DB, background LLM sync, memory graph and trigger loops."""
    # GH#9044: Close transcriber DB connection
    transcriber_db = getattr(app.state, "transcriber_db", None)
    if transcriber_db is not None and await report.run("Transcriber DB close", transcriber_db.close()):
        logger.info("Transcriber DB closed")

    if hasattr(app.state, "background_llm_sync") and app.state.background_llm_sync:
        await report.run("Background LLM sync stop", app.state.background_llm_sync.stop())
    if hasattr(app.state, "memory_graph") and app.state.memory_graph:
        await report.run("Memory graph close", app.state.memory_graph.close())

    # Issue #3100: Stop trigger service background loops
    if hasattr(app.state, "trigger_service") and app.state.trigger_service:
        if await report.run("Trigger service stop", app.state.trigger_service.stop()):
            logger.info("Trigger service stopped")


async def stop_connector_and_skill_schedulers(app: FastAPI, report: "_ShutdownReport") -> None:
    """Stop the connector scheduler and the skill health and distillation schedulers."""
    # Issue #6556: Stop connector scheduler local tasks
    try:
        from knowledge.connectors.scheduler import get_connector_scheduler

        await get_connector_scheduler().stop_all()
        logger.info("Connector scheduler stopped")
    except Exception as _cs_err:
        report.failed("Connector scheduler shutdown", _cs_err)

    # Issue #12810: Stop the skill health loop and cancel the task carrying it.
    try:
        health = getattr(app.state, "skill_health_scheduler", None)
        if health is not None:
            await health.stop()
        health_task = getattr(app.state, "skill_health_task", None)
        if health_task is not None and not health_task.done():
            # stop() only clears the loop flag; the task may be parked in its
            # interval sleep, so cancel rather than wait out the interval.
            health_task.cancel()
        logger.info("Skill health scheduler stopped")
    except Exception as _sh_err:
        report.failed("Skill health scheduler shutdown", _sh_err)

    # Issue #12809: Stop the skill distillation pass and release its leader lease
    # so another worker can claim it without waiting out the TTL.
    try:
        distiller = getattr(app.state, "skill_distillation_scheduler", None)
        if distiller is not None:
            await distiller.stop()
            logger.info("Skill distillation scheduler stopped")
    except Exception as _sd_err:
        report.failed("Skill distillation scheduler shutdown", _sd_err)


async def stop_vector_store_workers(app: FastAPI, report: "_ShutdownReport") -> None:
    """Stop the vector write buffer (flushing it) and the collection tier reaper."""
    # Issue #8391: Stop VectorWriteBuffer (flushes pending writes).
    kb = getattr(app.state, "knowledge_base", None)
    if kb is not None:
        write_buffer = getattr(kb, "_write_buffer", None)
        if write_buffer is not None:
            await report.run("Vector write buffer stop", write_buffer.stop())

    # Issue #8392: Stop CollectionTierManager reaper.
    tier_manager = getattr(app.state, "tier_manager", None)
    if tier_manager is not None:
        await report.run("Collection tier manager stop", tier_manager.stop())


async def stop_documentation_watchers(report: "_ShutdownReport") -> None:
    """Stop the documentation watcher and the KB folder watcher."""
    # Issue #165: Stop documentation watcher
    try:
        from services.documentation_watcher import stop_documentation_watcher

        await stop_documentation_watcher()
    except ImportError:
        pass  # Watcher not available
    except Exception as _dw_err:
        report.failed("Documentation watcher shutdown", _dw_err)

    # Issue #9000: Stop KB folder watcher
    try:
        from services.kb_folder_watcher import stop_kb_folder_watcher

        await stop_kb_folder_watcher()
        logger.info("✅ KB folder watcher stopped")
    except ImportError:
        pass  # Watcher not available
    except Exception as kb_watcher_error:
        report.failed("KB folder watcher shutdown", kb_watcher_error)


async def stop_doc_sync_queue_worker(app: FastAPI, report: "_ShutdownReport") -> None:
    """Stop the doc sync queue worker, then cancel and await its task."""
    # Issue #4453: Stop doc sync queue worker
    worker = getattr(app.state, "doc_sync_queue_worker", None)
    task = getattr(app.state, "doc_sync_queue_worker_task", None)
    if worker is not None:
        with report.step("Doc sync queue worker stop"):
            worker.stop()
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as _dsq_err:
            report.failed("Doc sync queue worker task drain", _dsq_err)


async def stop_gateway(app: FastAPI, report: "_ShutdownReport") -> None:
    """Stop the gateway."""
    # Issue #732: Shutdown Gateway
    try:
        if hasattr(app.state, "gateway") and app.state.gateway:
            await app.state.gateway.stop()
            logger.info("✅ Gateway shutdown")
    except Exception as gateway_error:
        report.failed("Gateway shutdown", gateway_error)


async def drain_llc_monitors_and_mesh_scheduler(app: FastAPI, report: "_ShutdownReport") -> None:
    """Drain the LLC liveness, budget and checkpointer loops; stop MeshBrainScheduler."""
    # GH#9028: Stop LLC liveness monitor
    # #13085: aclose() — stop() only *requests* cancellation and returns, so
    # the poll task could still be mid-tick (holding an AsyncSession) when
    # close_database() disposes the engine further down, and its interval
    # wait was left for whoever tore the event loop down. aclose() drains it
    # here, where shutdown can observe it.
    #
    # #13203: each drain is guarded individually, for the same reason the
    # MeshBrainScheduler stop below is — see the comment there. stop() was
    # synchronous and could neither raise nor suspend; await …aclose() can
    # do both, so an unguarded drain would abort the rest of the teardown.
    if hasattr(app.state, "llc_liveness_monitor") and app.state.llc_liveness_monitor:
        try:
            await app.state.llc_liveness_monitor.aclose()
            logger.info("✅ LLC liveness monitor stopped")
        except Exception as liveness_stop_error:
            report.failed("LLC liveness monitor stop", liveness_stop_error)
    # GH#9029: Stop LLC budget watchdog
    if hasattr(app.state, "llc_budget_watchdog") and app.state.llc_budget_watchdog:
        try:
            await app.state.llc_budget_watchdog.aclose()
            logger.info("✅ LLC budget watchdog stopped")
        except Exception as budget_stop_error:
            report.failed("LLC budget watchdog stop", budget_stop_error)
    # #12816: Stop MeshBrainScheduler — stop() cancels every per-job task
    # start() spawned, so none survive shutdown.
    #
    # Guarded independently: this whole shutdown block sits inside one broad
    # `except Exception`, so an error raised here would jump straight to that
    # handler and SKIP every remaining shutdown step below. Startup is
    # already treated as non-fatal; shutdown gets the same treatment so one
    # scheduler cannot abort the rest of the teardown.
    if hasattr(app.state, "mesh_brain_scheduler") and app.state.mesh_brain_scheduler:
        try:
            await app.state.mesh_brain_scheduler.stop()
            logger.info("✅ MeshBrainScheduler stopped")
        except Exception as mesh_stop_error:
            report.failed("MeshBrainScheduler stop", mesh_stop_error)
    # GH#9026: Stop LLC session checkpointer (#13085: drained, see above)
    if hasattr(app.state, "llc_session_checkpointer") and app.state.llc_session_checkpointer:
        try:
            await app.state.llc_session_checkpointer.aclose()
            logger.info("✅ LLC session checkpointer stopped")
        except Exception as checkpointer_stop_error:
            report.failed("LLC session checkpointer stop", checkpointer_stop_error)


async def stop_llc_services(app: FastAPI, report: "_ShutdownReport") -> None:
    """Stop LLC outbound sync and the notification router; drain HandoffService."""
    # GH#8257: Stop LLC outbound sync service
    if hasattr(app.state, "llc_outbound_sync") and app.state.llc_outbound_sync:
        if await report.run("LLC outbound sync stop", app.state.llc_outbound_sync.stop()):
            logger.info("✅ LLC outbound sync service stopped")
    # GH#8255: Stop LLC notification router
    if hasattr(app.state, "llc_notification_router") and app.state.llc_notification_router:
        if await report.run("LLC notification router stop", app.state.llc_notification_router.stop()):
            logger.info("✅ LLC notification router stopped")

    # GH#8651: Drain HandoffService background brief-generation tasks
    try:
        from llc.api.work_items import _get_handoff_service

        handoff_svc = _get_handoff_service()
        await handoff_svc.shutdown()
        logger.info("✅ LLC HandoffService background tasks drained")
    except Exception as _hs_err:
        report.failed("HandoffService drain", _hs_err)


async def stop_periodic_schedulers(app: FastAPI, report: "_ShutdownReport") -> None:
    """Stop the routine, heartbeat, backup and key-rotation schedulers; drain clustering."""
    # GH#8229: Stop LLC routine scheduler
    if hasattr(app.state, "llc_routine_scheduler") and app.state.llc_routine_scheduler:
        if await report.run("LLC routine scheduler shutdown", app.state.llc_routine_scheduler.shutdown()):
            logger.info("✅ LLC routine scheduler stopped")

    # GH#8225: Stop LLC heartbeat scheduler before other schedulers
    if hasattr(app.state, "heartbeat_scheduler") and app.state.heartbeat_scheduler:
        if await report.run("LLC heartbeat scheduler stop", app.state.heartbeat_scheduler.stop()):
            logger.info("✅ LLC heartbeat scheduler stopped")

    # Issue #3294: Stop backup scheduler
    if hasattr(app.state, "backup_scheduler") and app.state.backup_scheduler:
        if await report.run("Backup scheduler stop", app.state.backup_scheduler.stop()):
            logger.info("✅ Backup scheduler stopped")

    # Issue #6590: Stop LLM key rotation scheduler
    if hasattr(app.state, "llm_key_rotation_scheduler") and app.state.llm_key_rotation_scheduler:
        if await report.run("LLM key rotation scheduler stop", app.state.llm_key_rotation_scheduler.stop()):
            logger.info("✅ LLM key rotation scheduler stopped")

    # Issue #4946: Drain community clustering background task (#13210:
    # bounded + shielded via aclose(), guarded individually like its
    # sibling schedulers above — see the comment on those for why.
    scheduler = getattr(app.state, "community_cluster_scheduler", None)
    if scheduler:
        try:
            await scheduler.aclose()
            logger.info("✅ Community cluster task cancelled")
        except Exception as cluster_stop_error:
            report.failed("Community cluster task drain", cluster_stop_error)


async def stop_background_loops(app: FastAPI, report: "_ShutdownReport") -> None:
    """Stop the process adapter, the autonomous loop and metrics collection."""
    # Issue #1748: Stop process adapter dispatcher
    if hasattr(app.state, "process_adapter_service") and app.state.process_adapter_service:
        if await report.run("Process adapter stop", app.state.process_adapter_service.stop()):
            logger.info("✅ Process adapter stopped")

    # Issue #11638: Stop autonomous improvement loop background task
    try:
        from workflow_scheduler import stop_autonomous_loop

        await stop_autonomous_loop()
    except Exception as _al_err:
        report.failed("Autonomous loop shutdown", _al_err)

    # Issue #11638: Stop metrics collection loop and cancel its task
    try:
        from api.analytics import analytics_controller

        await analytics_controller.metrics_collector.stop_collection()
        logger.info("✅ Metrics collection stopped")
    except Exception as _mc_err:
        report.failed("Metrics collection stop", _mc_err)
    try:
        metrics_task = getattr(app.state, "metrics_collection_task", None)
        if metrics_task is not None and not metrics_task.done():
            metrics_task.cancel()
            await asyncio.gather(metrics_task, return_exceptions=True)
    except Exception as _mt_err:
        report.failed("Metrics task cancel", _mt_err)


async def shutdown_agent_runtime(app: FastAPI, report: "_ShutdownReport") -> None:
    """Shut down the orchestrator, WebResearcher and the AI Stack client."""
    # Issue #11638: Shutdown orchestrator singleton (agent pools, memory)
    try:
        from orchestrator import shutdown_orchestrator

        await shutdown_orchestrator()
        logger.info("✅ Orchestrator shutdown")
    except Exception as _orch_err:
        report.failed("Orchestrator shutdown", _orch_err)

    # Issue #11638: Close WebResearcher browser resources
    try:
        web_researcher = getattr(app.state, "web_researcher", None)
        if web_researcher is not None:
            await web_researcher.close()
            logger.info("✅ WebResearcher closed")
    except Exception as _wr_err:
        report.failed("WebResearcher shutdown", _wr_err)

    # Issue #11638: Cancel AI Stack client retry loop (its HTTP session
    # is the shared HTTPClientManager and is intentionally not closed)
    try:
        from services.ai_stack_client import close_ai_stack_client

        await close_ai_stack_client()
        logger.info("✅ AI Stack client closed")
    except Exception as _as_err:
        report.failed("AI Stack client shutdown", _as_err)


async def dispose_skills_engine(report: "_ShutdownReport") -> None:
    """Dispose the skills DB engine."""
    # Issue #11638: Dispose skills DB engine
    try:
        from skills.db import close_skills_engine

        await close_skills_engine()
        logger.info("✅ Skills DB engine closed")
    except Exception as _sk_err:
        report.failed("Skills DB engine dispose", _sk_err)


async def stop_log_forwarder(report: "_ShutdownReport") -> None:
    """Stop the log forwarder threads, if one was created."""
    # Issue #11638: Stop log forwarder threads if one was created
    # (off-loop: LogForwarder.stop() drains its queue synchronously)
    try:
        from api.log_forwarding import stop_forwarder_if_running

        if await stop_forwarder_if_running():
            logger.info("✅ Log forwarder stopped")
    except Exception as _lf_err:
        report.failed("Log forwarder shutdown", _lf_err)


async def stop_redis_dependent_loops(report: "_ShutdownReport") -> None:
    """Stop the NPU worker manager loops and the desktop relay, before Redis closes."""
    # Issue #11638: Stop NPU worker manager health/failover/pulse tasks
    # (started by get_worker_manager() during _wire_npu_task_queue; these
    # loops touch Redis, so stop them BEFORE closing Redis pools)
    try:
        import services.npu_worker_manager as _npu_wm

        if _npu_wm._worker_manager is not None:
            await _npu_wm._worker_manager.stop_health_monitoring()
            logger.info("✅ NPU worker manager monitoring stopped")
    except Exception as _npu_err:
        report.failed("NPU worker manager shutdown", _npu_err)

    # Issue #11639: Stop desktop streaming pub/sub relay (Redis
    # subscription — stop BEFORE closing Redis pools). No-op if no
    # streaming session ever started the relay.
    try:
        from desktop_streaming_manager import stop_desktop_relay

        await stop_desktop_relay()
    except Exception as _dsm_err:
        report.failed("Desktop streaming relay shutdown", _dsm_err)


async def shutdown_extensions(app: FastAPI, report: "_ShutdownReport") -> None:
    """Shut down the plugin manager, isolated MCP workers and the Claude API adapter."""
    # Issue #3278: Shutdown plugin manager
    try:
        if hasattr(app.state, "plugin_manager") and app.state.plugin_manager:
            await app.state.plugin_manager.shutdown()
            logger.info("✅ Plugin manager shutdown")
    except Exception as pm_err:
        report.failed("Plugin manager shutdown", pm_err)

    # Issue #4107: Stop isolated MCP bridge worker processes
    try:
        from services.mcp_isolated_runtime import get_isolated_registry

        await get_isolated_registry().shutdown_all()
        logger.info("✅ Isolated MCP bridge workers shutdown")
    except Exception as mcp_err:
        report.failed("Isolated MCP bridge shutdown", mcp_err)

    # #10796: Shutdown Claude API integration adapter
    try:
        claude_adapter = getattr(app.state, "claude_api_adapter", None)
        if claude_adapter is not None:
            await claude_adapter.shutdown()
            logger.info("Claude API integration adapter shutdown")
    except Exception as _ca_err:
        report.failed("Claude API adapter shutdown", _ca_err)


async def flush_llm_observers(report: "_ShutdownReport") -> None:
    """Flush the LangFuse / LangSmith observer buffers."""
    # GH#9012: Flush LangFuse / LangSmith observer buffers before exit
    try:
        from llm_shared.observability.registry import _registry

        for _obs in _registry:
            if callable(getattr(_obs, "flush", None)):
                _obs.flush()
        logger.info("✅ LLM observer buffers flushed")
    except Exception as obs_err:
        report.failed("LLM observer flush", obs_err)


async def dispose_database_engine(report: "_ShutdownReport") -> None:
    """Dispose the PostgreSQL async engine."""
    # Issue #11638: Dispose PostgreSQL async engine (was never disposed)
    try:
        from user_management.database import close_database

        await close_database()
    except Exception as _db_err:
        report.failed("Database engine dispose", _db_err)


async def close_redis_connections(report: "_ShutdownReport") -> None:
    """Close every Redis pool -- the last step (#11638)."""
    # Issue #11638: Close all Redis pools LAST — earlier shutdown steps
    # above may still publish events or flush state through Redis.
    try:
        from autobot_shared.redis_client import close_all_redis_connections

        await close_all_redis_connections()
        logger.info("✅ Redis connections closed")
    except Exception as _redis_err:
        report.failed("Redis connection close", _redis_err)
