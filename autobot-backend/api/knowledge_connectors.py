# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Knowledge Source Connector API

Issue #1254: CRUD endpoints for managing knowledge source connectors.
Connector configs are stored in Redis (knowledge DB) under
``connector:{connector_id}``.  Sync history is stored as a Redis list under
``connector:{connector_id}:history``.

Endpoints:
    GET  /api/knowledge_base/connectors
    POST /api/knowledge_base/connectors
    GET  /api/knowledge_base/connectors/{connector_id}
    PUT  /api/knowledge_base/connectors/{connector_id}
    DELETE /api/knowledge_base/connectors/{connector_id}
    POST /api/knowledge_base/connectors/{connector_id}/test
    POST /api/knowledge_base/connectors/{connector_id}/sync
    GET  /api/knowledge_base/connectors/{connector_id}/history
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.registry import ConnectorRegistry
from knowledge.connectors.scheduler import get_connector_scheduler
from pydantic import BaseModel, Field

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge-connectors"])

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

_SUPPORTED_TYPES = ["file_server", "web_crawler", "database"]


class CreateConnectorRequest(BaseModel):
    """Request body for POST /connectors."""

    connector_type: str = Field(
        ..., description="One of: file_server, web_crawler, database"
    )
    name: str = Field(..., min_length=1, max_length=128)
    config: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    verification_mode: str = "collaborative"
    schedule_cron: Optional[str] = None
    include_patterns: List[str] = Field(default_factory=list)
    exclude_patterns: List[str] = Field(default_factory=list)


class UpdateConnectorRequest(BaseModel):
    """Request body for PUT /connectors/{id}."""

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    verification_mode: Optional[str] = None
    schedule_cron: Optional[str] = None
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

_REDIS_KEY_PREFIX = "connector:"
_HISTORY_KEY_SUFFIX = ":history"
_MAX_HISTORY = 50


def _connector_key(connector_id: str) -> str:
    return "%s%s" % (_REDIS_KEY_PREFIX, connector_id)


def _history_key(connector_id: str) -> str:
    return "%s%s%s" % (_REDIS_KEY_PREFIX, connector_id, _HISTORY_KEY_SUFFIX)


async def _save_connector(cfg: ConnectorConfig) -> None:
    """Serialize and save a ConnectorConfig to Redis (Issue #1254)."""
    redis = get_redis_client(database="knowledge")
    data = {
        "connector_id": cfg.connector_id,
        "connector_type": cfg.connector_type,
        "name": cfg.name,
        "config": cfg.config,
        "enabled": cfg.enabled,
        "verification_mode": cfg.verification_mode,
        "schedule_cron": cfg.schedule_cron,
        "created_at": cfg.created_at.isoformat(),
        "last_sync_at": cfg.last_sync_at.isoformat() if cfg.last_sync_at else None,
        "include_patterns": cfg.include_patterns,
        "exclude_patterns": cfg.exclude_patterns,
    }
    await asyncio.to_thread(
        redis.set,
        _connector_key(cfg.connector_id),
        json.dumps(data, ensure_ascii=False),
    )


async def _load_connector(connector_id: str) -> Optional[ConnectorConfig]:
    """Load and deserialize a ConnectorConfig from Redis (Issue #1254)."""
    redis = get_redis_client(database="knowledge")
    raw = await asyncio.to_thread(redis.get, _connector_key(connector_id))
    if raw is None:
        return None
    return _deserialize_connector(raw)


def _deserialize_connector(raw: Any) -> ConnectorConfig:
    """Parse raw Redis bytes/str into a ConnectorConfig (Issue #1254: extracted)."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = json.loads(raw)
    return ConnectorConfig(
        connector_id=data["connector_id"],
        connector_type=data["connector_type"],
        name=data["name"],
        config=data.get("config", {}),
        enabled=data.get("enabled", True),
        verification_mode=data.get("verification_mode", "collaborative"),
        schedule_cron=data.get("schedule_cron"),
        created_at=_parse_dt(data.get("created_at")),
        last_sync_at=_parse_dt(data.get("last_sync_at")),
        include_patterns=data.get("include_patterns", []),
        exclude_patterns=data.get("exclude_patterns", []),
    )


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string or return None (Issue #1254: helper)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


async def _list_connector_ids() -> List[str]:
    """Scan Redis for all connector keys and return their IDs (Issue #1254)."""
    redis = get_redis_client(database="knowledge")
    pattern = "%s*" % _REDIS_KEY_PREFIX
    ids: List[str] = []
    async_scan = hasattr(redis, "scan_iter") and asyncio.iscoroutinefunction(
        getattr(redis, "scan_iter", None)
    )

    if async_scan:
        async for key in redis.scan_iter(match=pattern):
            key_str = key.decode("utf-8") if isinstance(key, bytes) else key
            if _HISTORY_KEY_SUFFIX not in key_str:
                ids.append(key_str[len(_REDIS_KEY_PREFIX) :])
    else:
        keys = await asyncio.to_thread(lambda: list(redis.scan_iter(match=pattern)))
        for key in keys:
            key_str = key.decode("utf-8") if isinstance(key, bytes) else key
            if _HISTORY_KEY_SUFFIX not in key_str:
                ids.append(key_str[len(_REDIS_KEY_PREFIX) :])

    return ids


async def _append_history(connector_id: str, result_data: Dict[str, Any]) -> None:
    """Prepend a sync result to the connector's history list (Issue #1254)."""
    redis = get_redis_client(database="knowledge")
    key = _history_key(connector_id)
    serialized = json.dumps(result_data, ensure_ascii=False)
    await asyncio.to_thread(redis.lpush, key, serialized)
    await asyncio.to_thread(redis.ltrim, key, 0, _MAX_HISTORY - 1)


async def _delete_connector_keys(connector_id: str) -> None:
    """Remove connector config and history from Redis (Issue #1254)."""
    redis = get_redis_client(database="knowledge")
    await asyncio.to_thread(
        redis.delete,
        _connector_key(connector_id),
        _history_key(connector_id),
    )


# ---------------------------------------------------------------------------
# Connector instance management
# ---------------------------------------------------------------------------


def _load_or_create_instance(cfg: ConnectorConfig):
    """Return existing instance or create+register a new one (Issue #1254)."""
    existing = ConnectorRegistry.get(cfg.connector_id)
    if existing is not None:
        existing.config = cfg
        return existing
    instance = ConnectorRegistry.create(cfg)
    ConnectorRegistry.add_instance(instance)
    return instance


async def _run_sync_background(connector_id: str, incremental: bool) -> None:
    """Background task: run sync and persist result + last_sync_at."""
    cfg = await _load_connector(connector_id)
    if cfg is None:
        logger.error("Background sync: connector %s not found", connector_id)
        return

    instance = _load_or_create_instance(cfg)
    try:
        sync_result = await instance.sync(incremental=incremental)
    except Exception as exc:
        logger.error("Background sync failed for %s: %s", connector_id, exc)
        sync_result = None

    if sync_result is not None:
        cfg.last_sync_at = sync_result.completed_at or datetime.utcnow()
        await _save_connector(cfg)

        history_entry = {
            "connector_id": connector_id,
            "started_at": sync_result.started_at.isoformat(),
            "completed_at": (
                sync_result.completed_at.isoformat()
                if sync_result.completed_at
                else None
            ),
            "status": sync_result.status,
            "added": sync_result.added,
            "updated": sync_result.updated,
            "deleted": sync_result.deleted,
            "errors": sync_result.errors,
        }
        await _append_history(connector_id, history_entry)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@router.get("/knowledge_base/connectors")
async def list_connectors():
    """Return all connectors with their current status."""
    try:
        ids = await _list_connector_ids()
        results = []
        for cid in ids:
            cfg = await _load_connector(cid)
            if cfg is None:
                continue
            status = await _get_status_for_config(cfg)
            results.append({"config": _cfg_to_dict(cfg), "status": status})
        return {"connectors": results, "total": len(results)}
    except Exception as exc:
        logger.error("list_connectors failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/knowledge_base/connectors", status_code=201)
async def create_connector(request: CreateConnectorRequest):
    """Create a new connector, test the connection, and persist the config."""
    if request.connector_type not in _SUPPORTED_TYPES:
        raise HTTPException(
            status_code=422,
            detail="connector_type must be one of: %s" % _SUPPORTED_TYPES,
        )
    connector_id = str(uuid.uuid4())
    cfg = ConnectorConfig(
        connector_id=connector_id,
        connector_type=request.connector_type,
        name=request.name,
        config=request.config,
        enabled=request.enabled,
        verification_mode=request.verification_mode,
        schedule_cron=request.schedule_cron,
        include_patterns=request.include_patterns,
        exclude_patterns=request.exclude_patterns,
    )
    instance = _load_or_create_instance(cfg)
    healthy = await instance.test_connection()
    if not healthy:
        ConnectorRegistry.remove_instance(connector_id)
        raise HTTPException(
            status_code=400,
            detail="Connection test failed — verify connector config and target availability",
        )
    await _save_connector(cfg)
    await _maybe_schedule(cfg)
    logger.info("Created connector %s (%s)", connector_id, request.connector_type)
    return {"connector_id": connector_id, "config": _cfg_to_dict(cfg)}


@router.get("/knowledge_base/connectors/{connector_id}")
async def get_connector(connector_id: str):
    """Return config and status for a single connector."""
    cfg = await _load_connector(connector_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    status = await _get_status_for_config(cfg)
    return {"config": _cfg_to_dict(cfg), "status": status}


@router.put("/knowledge_base/connectors/{connector_id}")
async def update_connector(connector_id: str, request: UpdateConnectorRequest):
    """Update mutable fields of an existing connector."""
    cfg = await _load_connector(connector_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Connector not found")

    _apply_updates(cfg, request)
    await _save_connector(cfg)

    instance = ConnectorRegistry.get(connector_id)
    if instance is not None:
        instance.config = cfg

    await _reschedule(cfg)
    logger.info("Updated connector %s", connector_id)
    return {"connector_id": connector_id, "config": _cfg_to_dict(cfg)}


@router.delete("/knowledge_base/connectors/{connector_id}", status_code=204)
async def delete_connector(connector_id: str):
    """Remove a connector, stop its schedule, and delete its Redis keys."""
    cfg = await _load_connector(connector_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Connector not found")

    scheduler = get_connector_scheduler()
    await scheduler.stop(connector_id)
    ConnectorRegistry.remove_instance(connector_id)
    await _delete_connector_keys(connector_id)
    logger.info("Deleted connector %s", connector_id)


@router.post("/knowledge_base/connectors/{connector_id}/test")
async def test_connector_connection(connector_id: str):
    """Run a connection test against the connector's target."""
    cfg = await _load_connector(connector_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    instance = _load_or_create_instance(cfg)
    try:
        healthy = await instance.test_connection()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"connector_id": connector_id, "healthy": healthy}


@router.post("/knowledge_base/connectors/{connector_id}/sync")
async def trigger_sync(
    connector_id: str,
    background_tasks: BackgroundTasks,
    incremental: bool = True,
):
    """Trigger a manual sync for a connector (runs in background)."""
    cfg = await _load_connector(connector_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    background_tasks.add_task(_run_sync_background, connector_id, incremental)
    logger.info(
        "Triggered sync for connector %s (incremental=%s)", connector_id, incremental
    )
    return {
        "connector_id": connector_id,
        "status": "sync_started",
        "incremental": incremental,
    }


@router.get("/knowledge_base/connectors/{connector_id}/history")
async def get_sync_history(connector_id: str, limit: int = 20):
    """Return recent sync results for a connector."""
    cfg = await _load_connector(connector_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    if limit > _MAX_HISTORY:
        limit = _MAX_HISTORY

    redis = get_redis_client(database="knowledge")
    key = _history_key(connector_id)
    raw_list = await asyncio.to_thread(redis.lrange, key, 0, limit - 1)

    history = []
    for raw in raw_list:
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            history.append(json.loads(raw))
        except Exception as exc:
            logger.warning("Skipping malformed history entry: %s", exc)

    return {"connector_id": connector_id, "history": history, "total": len(history)}


# ---------------------------------------------------------------------------
# Internal helpers (kept short per function-length policy)
# ---------------------------------------------------------------------------


async def _get_status_for_config(cfg: ConnectorConfig) -> Dict[str, Any]:
    """Return a plain-dict status for a config (Issue #1254: extracted)."""
    instance = ConnectorRegistry.get(cfg.connector_id)
    if instance is None:
        return {
            "connector_id": cfg.connector_id,
            "is_healthy": False,
            "last_sync_at": cfg.last_sync_at.isoformat() if cfg.last_sync_at else None,
            "last_sync_status": "never" if cfg.last_sync_at is None else "unknown",
            "documents_indexed": 0,
            "scheduled": False,
        }
    try:
        status = await instance.get_status()
        scheduler = get_connector_scheduler()
        return {
            "connector_id": status.connector_id,
            "is_healthy": status.is_healthy,
            "last_sync_at": (
                status.last_sync_at.isoformat() if status.last_sync_at else None
            ),
            "last_sync_status": status.last_sync_status,
            "documents_indexed": status.documents_indexed,
            "last_error": status.last_error,
            "scheduled": scheduler.is_running(cfg.connector_id),
        }
    except Exception as exc:
        logger.warning("get_status failed for %s: %s", cfg.connector_id, exc)
        return {
            "connector_id": cfg.connector_id,
            "is_healthy": False,
            "error": str(exc),
        }


def _cfg_to_dict(cfg: ConnectorConfig) -> Dict[str, Any]:
    """Serialize ConnectorConfig to a plain dict for API responses."""
    return {
        "connector_id": cfg.connector_id,
        "connector_type": cfg.connector_type,
        "name": cfg.name,
        "config": cfg.config,
        "enabled": cfg.enabled,
        "verification_mode": cfg.verification_mode,
        "schedule_cron": cfg.schedule_cron,
        "created_at": cfg.created_at.isoformat(),
        "last_sync_at": cfg.last_sync_at.isoformat() if cfg.last_sync_at else None,
        "include_patterns": cfg.include_patterns,
        "exclude_patterns": cfg.exclude_patterns,
    }


def _apply_updates(cfg: ConnectorConfig, req: UpdateConnectorRequest) -> None:
    """Mutate cfg in-place with non-None fields from req (Issue #1254)."""
    if req.name is not None:
        cfg.name = req.name
    if req.config is not None:
        cfg.config = req.config
    if req.enabled is not None:
        cfg.enabled = req.enabled
    if req.verification_mode is not None:
        cfg.verification_mode = req.verification_mode
    if req.schedule_cron is not None:
        cfg.schedule_cron = req.schedule_cron
    if req.include_patterns is not None:
        cfg.include_patterns = req.include_patterns
    if req.exclude_patterns is not None:
        cfg.exclude_patterns = req.exclude_patterns


async def _maybe_schedule(cfg: ConnectorConfig) -> None:
    """Start a schedule task if schedule_cron is set (Issue #1254)."""
    if cfg.schedule_cron and cfg.enabled:
        scheduler = get_connector_scheduler()
        await scheduler.start(cfg.connector_id, cfg.schedule_cron)


async def _reschedule(cfg: ConnectorConfig) -> None:
    """Stop existing schedule and restart with updated config (Issue #1254)."""
    scheduler = get_connector_scheduler()
    await scheduler.stop(cfg.connector_id)
    if cfg.schedule_cron and cfg.enabled:
        await scheduler.start(cfg.connector_id, cfg.schedule_cron)
