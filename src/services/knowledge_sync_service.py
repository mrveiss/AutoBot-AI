#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Knowledge Sync Background Service
Provides continuous incremental sync without blocking user operations

Features:
- Background sync daemon with configurable intervals
- REST API endpoints for manual sync triggers
- Real-time sync status and metrics reporting
- Integration with AutoBot's distributed architecture
- Performance monitoring and optimization recommendations
"""

import asyncio
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse

from src.advanced_rag_optimizer import get_rag_optimizer
from src.constants.threshold_constants import TimingConstants
from src.knowledge_sync_incremental import IncrementalKnowledgeSync
from src.utils.catalog_http_exceptions import raise_kb_error
from src.utils.logging_manager import get_llm_logger

logger = get_llm_logger("knowledge_sync_service")


class KnowledgeSyncService:
    """
    Background service for managing knowledge base synchronization.

    Provides:
    1. Continuous background sync daemon
    2. Manual sync triggers via API
    3. Performance monitoring and metrics
    4. Integration with AutoBot's service ecosystem
    """

    def __init__(self):
        """Initialize knowledge sync service with sync state and configuration."""
        self.incremental_sync = None
        self.rag_optimizer = None

        # Service state
        self.is_running = False
        self.daemon_task = None
        self.last_sync_time = None
        self.last_sync_metrics = None

        # Configuration
        self.sync_interval_minutes = 15
        self.max_concurrent_syncs = 1
        self.enable_auto_sync = True

        # Performance tracking
        self.sync_history = []
        self.max_history_entries = 100

        logger.info("KnowledgeSyncService initialized")

    async def initialize(self):
        """Initialize the sync service and components."""
        try:
            # Initialize incremental sync
            self.incremental_sync = IncrementalKnowledgeSync()
            await self.incremental_sync.initialize()

            # Initialize RAG optimizer
            self.rag_optimizer = await get_rag_optimizer()

            logger.info("Knowledge sync service initialized successfully")
            return True

        except Exception as e:
            logger.error("Failed to initialize sync service: %s", e)
            return False

    async def start_daemon(self, interval_minutes: int = 15):
        """Start the background sync daemon."""
        if self.is_running:
            logger.warning("Sync daemon already running")
            return

        self.sync_interval_minutes = interval_minutes
        self.is_running = True

        logger.info("Starting sync daemon (interval: %s minutes)", interval_minutes)

        try:
            while self.is_running:
                try:
                    # Wait for the interval
                    await asyncio.sleep(interval_minutes * 60)

                    if not self.is_running:
                        break

                    # Perform background sync
                    await self._background_sync()

                except asyncio.CancelledError:
                    logger.info("Sync daemon cancelled")
                    break
                except Exception as e:
                    logger.error("Background sync error: %s", e)
                    # Continue running despite errors
                    await asyncio.sleep(
                        TimingConstants.STANDARD_TIMEOUT
                    )  # Wait 1 minute before retry

        finally:
            self.is_running = False
            logger.info("Sync daemon stopped")

    async def stop_daemon(self):
        """Stop the background sync daemon."""
        if not self.is_running:
            return

        logger.info("Stopping sync daemon...")
        self.is_running = False

        if self.daemon_task and not self.daemon_task.done():
            self.daemon_task.cancel()
            try:
                await self.daemon_task
            except asyncio.CancelledError:
                logger.debug("Sync daemon task cancelled during shutdown")

        logger.info("Sync daemon stopped")

    async def _background_sync(self):
        """Perform background sync operation."""
        try:
            logger.info("Starting background sync...")
            start_time = time.time()

            # Perform incremental sync
            metrics = await self.incremental_sync.perform_incremental_sync()

            # Update service state
            self.last_sync_time = datetime.now()
            self.last_sync_metrics = metrics

            # Add to history
            sync_record = {
                "timestamp": self.last_sync_time.isoformat(),
                "metrics": asdict(metrics),
                "sync_type": "background",
                "duration": time.time() - start_time,
            }

            self.sync_history.append(sync_record)

            # Limit history size
            if len(self.sync_history) > self.max_history_entries:
                self.sync_history = self.sync_history[-self.max_history_entries :]

            # Log results
            if metrics.files_changed + metrics.files_added + metrics.files_removed > 0:
                logger.info(
                    "Background sync completed: %s files processed",
                    metrics.files_changed + metrics.files_added,
                )
            else:
                logger.debug("Background sync: no changes detected")

        except Exception as e:
            logger.error("Background sync failed: %s", e)

    async def manual_sync(self, force_full: bool = False) -> Dict[str, Any]:
        """Perform manual sync operation."""
        try:
            logger.info("Manual sync triggered (force_full=%s)", force_full)
            start_time = time.time()

            if force_full:
                # Clear metadata to force full resync
                self.incremental_sync.file_metadata = {}

            # Perform sync
            metrics = await self.incremental_sync.perform_incremental_sync()

            # Update state
            self.last_sync_time = datetime.now()
            self.last_sync_metrics = metrics

            # Add to history
            sync_record = {
                "timestamp": self.last_sync_time.isoformat(),
                "metrics": asdict(metrics),
                "sync_type": "manual_full" if force_full else "manual_incremental",
                "duration": time.time() - start_time,
            }

            self.sync_history.append(sync_record)

            # Limit history size
            if len(self.sync_history) > self.max_history_entries:
                self.sync_history = self.sync_history[-self.max_history_entries :]

            return {
                "status": "success",
                "sync_time": self.last_sync_time.isoformat(),
                "metrics": asdict(metrics),
                "duration": sync_record["duration"],
            }

        except Exception as e:
            logger.error("Manual sync failed: %s", e)
            return {
                "status": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status and statistics."""
        try:
            # Get basic status from incremental sync
            basic_status = (
                self.incremental_sync.get_sync_status() if self.incremental_sync else {}
            )

            # Add service-specific information
            status = {
                **basic_status,
                "service_running": self.is_running,
                "daemon_interval_minutes": self.sync_interval_minutes,
                "last_sync_time": (
                    self.last_sync_time.isoformat() if self.last_sync_time else None
                ),
                "auto_sync_enabled": self.enable_auto_sync,
                "sync_history_count": len(self.sync_history),
            }

            # Add last sync metrics if available
            if self.last_sync_metrics:
                status["last_sync_metrics"] = asdict(self.last_sync_metrics)

            # Add performance summary
            if self.sync_history:
                recent_syncs = self.sync_history[-10:]  # Last 10 syncs
                avg_duration = sum(s["duration"] for s in recent_syncs) / len(
                    recent_syncs
                )
                total_files_processed = sum(
                    s["metrics"]["files_changed"] + s["metrics"]["files_added"]
                    for s in recent_syncs
                )

                status["performance_summary"] = {
                    "avg_sync_duration": avg_duration,
                    "recent_syncs_count": len(recent_syncs),
                    "total_files_processed_recently": total_files_processed,
                }

            return status

        except Exception as e:
            logger.error("Failed to get sync status: %s", e)
            return {
                "status": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def _calculate_duration_stats(self, durations: list) -> tuple[float, float, float]:
        """
        Calculate duration statistics from sync history.

        Args:
            durations: List of sync durations

        Returns:
            Tuple of (avg_duration, min_duration, max_duration)

        Issue #620.
        """
        avg_duration = sum(durations) / len(durations) if durations else 0
        min_duration = min(durations) if durations else 0
        max_duration = max(durations) if durations else 0
        return avg_duration, min_duration, max_duration

    def _generate_performance_recommendations(
        self, avg_duration: float, avg_files_per_sync: float, max_duration: float
    ) -> list[str]:
        """
        Generate performance recommendations based on metrics.

        Args:
            avg_duration: Average sync duration in seconds
            avg_files_per_sync: Average files processed per sync
            max_duration: Maximum sync duration in seconds

        Returns:
            List of recommendation strings

        Issue #620.
        """
        recommendations = []

        if avg_duration > 5.0:
            recommendations.append(
                "Consider increasing sync interval to reduce overhead"
            )

        if avg_files_per_sync > 20:
            recommendations.append(
                "High file change rate detected - consider batch processing optimization"
            )

        if max_duration > avg_duration * 3:
            recommendations.append(
                "Inconsistent sync times - investigate performance bottlenecks"
            )

        return recommendations

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get detailed performance metrics and recommendations."""
        try:
            if not self.sync_history:
                return {"message": "No sync history available"}

            # Analyze performance trends from last 20 syncs
            recent_history = self.sync_history[-20:]
            durations = [s["duration"] for s in recent_history]
            file_counts = [
                s["metrics"]["files_changed"] + s["metrics"]["files_added"]
                for s in recent_history
            ]

            # Calculate statistics
            avg_duration, min_duration, max_duration = self._calculate_duration_stats(
                durations
            )
            total_files = sum(file_counts)
            avg_files_per_sync = total_files / len(file_counts) if file_counts else 0

            # Generate recommendations
            recommendations = self._generate_performance_recommendations(
                avg_duration, avg_files_per_sync, max_duration
            )

            # Estimate performance improvement
            estimated_full_sync_time = total_files * 0.5  # Conservative estimate
            actual_time = sum(durations)
            improvement_factor = estimated_full_sync_time / max(actual_time, 0.1)

            return {
                "performance_stats": {
                    "avg_sync_duration": avg_duration,
                    "min_sync_duration": min_duration,
                    "max_sync_duration": max_duration,
                    "total_syncs_analyzed": len(durations),
                    "avg_files_per_sync": avg_files_per_sync,
                    "total_files_processed": total_files,
                },
                "performance_improvement": {
                    "estimated_improvement_factor": improvement_factor,
                    "target_met": improvement_factor >= 10,
                    "target_range": "10-50x improvement",
                },
                "recommendations": recommendations,
                "analysis_timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("Failed to get performance metrics: %s", e)
            return {
                "status": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# Global service instance (thread-safe)
import asyncio as _asyncio_lock

_sync_service_instance = None
_sync_service_lock = _asyncio_lock.Lock()


async def get_sync_service() -> KnowledgeSyncService:
    """Get the global sync service instance (thread-safe)."""
    global _sync_service_instance

    if _sync_service_instance is None:
        async with _sync_service_lock:
            # Double-check after acquiring lock
            if _sync_service_instance is None:
                _sync_service_instance = KnowledgeSyncService()
                await _sync_service_instance.initialize()

    return _sync_service_instance


# FastAPI router for REST API endpoints
router = APIRouter(prefix="/api/knowledge/sync", tags=["knowledge-sync"])


@router.post("/manual")
async def trigger_manual_sync(
    force_full: bool = False, background_tasks: BackgroundTasks = None
):
    """Trigger manual knowledge base sync."""
    try:
        service = await get_sync_service()

        if background_tasks:
            # Run in background to avoid blocking
            background_tasks.add_task(service.manual_sync, force_full)
            return JSONResponse(
                {
                    "status": "started",
                    "message": "Manual sync started in background",
                    "force_full": force_full,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        else:
            # Run synchronously
            result = await service.manual_sync(force_full)
            return JSONResponse(result)

    except Exception as e:
        logger.error("Manual sync API error: %s", e)
        raise_kb_error("KB_0004", str(e))


@router.get("/status")
async def get_sync_status():
    """Get current sync status and statistics."""
    try:
        service = await get_sync_service()
        status = service.get_sync_status()
        return JSONResponse(status)

    except Exception as e:
        logger.error("Sync status API error: %s", e)
        raise_kb_error("KB_0004", str(e))


@router.get("/metrics")
async def get_performance_metrics():
    """Get detailed performance metrics and recommendations."""
    try:
        service = await get_sync_service()
        metrics = service.get_performance_metrics()
        return JSONResponse(metrics)

    except Exception as e:
        logger.error("Performance metrics API error: %s", e)
        raise_kb_error("KB_0004", str(e))


@router.post("/daemon/start")
async def start_sync_daemon(interval_minutes: int = 15):
    """Start the background sync daemon."""
    try:
        service = await get_sync_service()

        if service.is_running:
            return JSONResponse(
                {
                    "status": "already_running",
                    "message": "Sync daemon is already running",
                    "interval_minutes": service.sync_interval_minutes,
                }
            )

        # Start daemon in background task
        service.daemon_task = asyncio.create_task(
            service.start_daemon(interval_minutes)
        )

        return JSONResponse(
            {
                "status": "started",
                "message": "Sync daemon started successfully",
                "interval_minutes": interval_minutes,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error("Start daemon API error: %s", e)
        raise_kb_error("KB_0004", str(e))


@router.post("/daemon/stop")
async def stop_sync_daemon():
    """Stop the background sync daemon."""
    try:
        service = await get_sync_service()

        if not service.is_running:
            return JSONResponse(
                {"status": "not_running", "message": "Sync daemon is not running"}
            )

        await service.stop_daemon()

        return JSONResponse(
            {
                "status": "stopped",
                "message": "Sync daemon stopped successfully",
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error("Stop daemon API error: %s", e)
        raise_kb_error("KB_0004", str(e))


@router.get("/history")
async def get_sync_history(limit: int = 20):
    """Get sync history for analysis."""
    try:
        service = await get_sync_service()

        if not service.sync_history:
            return JSONResponse({"history": [], "message": "No sync history available"})

        # Return limited history
        history = service.sync_history[-limit:] if limit > 0 else service.sync_history

        return JSONResponse(
            {
                "history": history,
                "total_entries": len(service.sync_history),
                "returned_entries": len(history),
            }
        )

    except Exception as e:
        logger.error("Sync history API error: %s", e)
        raise_kb_error("KB_0004", str(e))


# Integration with AutoBot's main application
def register_sync_service_routes(app):
    """Register sync service routes with the main FastAPI app."""
    app.include_router(router)
    logger.info("Knowledge sync service routes registered")


async def initialize_sync_service():
    """Initialize the sync service for the main application."""
    try:
        service = await get_sync_service()
        logger.info("Knowledge sync service initialized for main application")
        return service
    except Exception as e:
        logger.error("Failed to initialize sync service: %s", e)
        return None
