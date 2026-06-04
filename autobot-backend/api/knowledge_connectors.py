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
    GET  /api/knowledge_base/connector_types
    GET  /api/knowledge_base/connectors
    POST /api/knowledge_base/connectors
    GET  /api/knowledge_base/connectors/health
    GET  /api/knowledge_base/connectors/scheduler/leader      (Issue #8149)
    GET  /api/knowledge_base/connectors/{connector_id}
    PUT  /api/knowledge_base/connectors/{connector_id}
    DELETE /api/knowledge_base/connectors/{connector_id}
    POST /api/knowledge_base/connectors/{connector_id}/test
    POST /api/knowledge_base/connectors/{connector_id}/sync
    GET  /api/knowledge_base/connectors/{connector_id}/history
    GET  /api/knowledge_base/connectors/{connector_id}/job    (Issue #8149)
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from redis.exceptions import RedisError

from auth_middleware import check_admin_permission
from autobot_shared.auth import validate_config_against_schema
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.time_utils import now_utc, parse_utc_iso
from constants.error_constants import ERR_CONNECTOR_NOT_FOUND
from knowledge.connectors.credential_store import get_credential_store
from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.registry import ConnectorRegistry
from knowledge.connectors.scheduler import get_connector_scheduler
from knowledge.schemas.connectors import (
    ConnectorCreateResponse,
    ConnectorDetailResponse,
    ConnectorHistoryResponse,
    ConnectorJobResponse,
    ConnectorLeaderResponse,
    ConnectorsHealthResponse,
    ConnectorsListResponse,
    ConnectorSyncResponse,
    ConnectorTestResponse,
    ConnectorTypesResponse,
    ConnectorUpdateResponse,
    CreateConnectorRequest,
    UpdateConnectorRequest,
)

logger = get_logger(__name__)

router = APIRouter(
    tags=["knowledge-connectors"],
    dependencies=[Depends(check_admin_permission)],
)

_SUPPORTED_TYPES = ["file_server", "web_crawler", "database", "notion", "gitlab", "gitea", "forgejo"]


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

_REDIS_KEY_PREFIX = "connector:"
_HISTORY_KEY_SUFFIX = ":history"
_JOB_KEY_SUFFIX = ":job:current"
_MAX_HISTORY = 50
# Suffixes / infixes that mark non-config Redis keys under connector: namespace.
_NON_CONFIG_INFIXES = (_HISTORY_KEY_SUFFIX, _JOB_KEY_SUFFIX, ":schedule:", "scheduler:")


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
        "tier": int(getattr(cfg, "tier", 0)),
        "auth_type": getattr(cfg, "auth_type", None),
        "max_concurrency": cfg.max_concurrency,
        "secret_id": cfg.secret_id,
        "owner_id": cfg.owner_id,
    }
    await asyncio.to_thread(
        redis.set,
        _connector_key(cfg.connector_id),
        json.dumps(data, ensure_ascii=False),
    )


async def _load_connector(connector_id: str) -> ConnectorConfig | None:
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
    raw_mc = data.get("max_concurrency")
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
        tier=int(data.get("tier", 0)),
        auth_type=data.get("auth_type"),
        max_concurrency=int(raw_mc) if raw_mc is not None else None,
        secret_id=data.get("secret_id"),
        owner_id=data.get("owner_id"),
    )


def _parse_dt(value: str | None) -> datetime | None:
    """Parse ISO datetime string or return None (Issue #1254: helper)."""
    if not value:
        return None
    try:
        return parse_utc_iso(value)
    except (ValueError, TypeError):
        return None


async def _list_connector_ids() -> List[str]:
    """Scan Redis for all connector keys and return their IDs (Issue #1254)."""
    redis = get_redis_client(database="knowledge")
    pattern = "%s*" % _REDIS_KEY_PREFIX
    ids: List[str] = []
    async_scan = hasattr(redis, "scan_iter") and asyncio.iscoroutinefunction(getattr(redis, "scan_iter", None))

    def _is_config_key(key_str: str) -> bool:
        stripped = key_str[len(_REDIS_KEY_PREFIX) :]
        return not any(infix in stripped for infix in _NON_CONFIG_INFIXES)

    if async_scan:
        async for key in redis.scan_iter(match=pattern):
            key_str = key.decode("utf-8") if isinstance(key, bytes) else key
            if _is_config_key(key_str):
                ids.append(key_str[len(_REDIS_KEY_PREFIX) :])
    else:
        keys = await asyncio.to_thread(lambda: list(redis.scan_iter(match=pattern)))
        for key in keys:
            key_str = key.decode("utf-8") if isinstance(key, bytes) else key
            if _is_config_key(key_str):
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


async def _cfg_with_credentials(cfg: ConnectorConfig, auth_cls: type | None) -> ConnectorConfig:
    """Return a ConnectorConfig with sensitive credentials merged back in (ADR-007).

    When cfg.secret_id is set, loads the secret and merges credentials into a
    copy of cfg.config.  Returns cfg unchanged when there is no secret_id or
    no auth_cls with __sensitive_fields__.
    """
    if not cfg.secret_id or auth_cls is None or not hasattr(auth_cls, "__sensitive_fields__"):
        return cfg
    owner_id = cfg.owner_id or "system"
    try:
        full_config = await get_credential_store().load(cfg.secret_id, cfg.config, auth_cls, owner_id)
    except (LookupError, PermissionError) as exc:
        logger.error("Failed to load credentials for connector %s: %s", cfg.connector_id, exc)
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    import dataclasses

    return dataclasses.replace(cfg, config=full_config)


async def _load_or_create_instance(cfg: ConnectorConfig):
    """Return existing instance or create+register a new one (Issue #1254)."""
    existing = ConnectorRegistry.get(cfg.connector_id)
    if existing is not None:
        existing.config = cfg
        return existing
    instance = await ConnectorRegistry.create(cfg)
    ConnectorRegistry.add_instance(instance)
    return instance


async def _run_sync_background(connector_id: str, incremental: bool) -> None:
    """Background task: run sync and persist result + last_sync_at."""
    cfg = await _load_connector(connector_id)
    if cfg is None:
        logger.error("Background sync: connector %s not found", connector_id)
        return

    # ADR-007: reconstruct full config with credentials before invoking connector.
    klass = ConnectorRegistry.get_registered_class(cfg.connector_type)
    auth_cls = klass.auth_schema() if klass else None
    try:
        cfg = await _cfg_with_credentials(cfg, auth_cls)
    except HTTPException as exc:
        logger.error("Background sync: credential load failed for %s: %s", connector_id, exc.detail)
        return

    instance = await _load_or_create_instance(cfg)
    try:
        sync_result = await instance.sync(incremental=incremental)
    except Exception as exc:
        logger.error("Background sync failed for %s: %s", connector_id, exc)
        sync_result = None

    if sync_result is not None:
        cfg.last_sync_at = sync_result.completed_at or now_utc()
        await _save_connector(cfg)

        completed_at = sync_result.completed_at
        duration_seconds = None
        if completed_at is not None:
            duration_seconds = (completed_at - sync_result.started_at).total_seconds()
        history_entry = {
            "connector_id": connector_id,
            "started_at": sync_result.started_at.isoformat(),
            "completed_at": (completed_at.isoformat() if completed_at else None),
            "status": sync_result.status,
            "added": sync_result.added,
            "updated": sync_result.updated,
            "deleted": sync_result.deleted,
            "errors": sync_result.errors,
            "resumed_from_checkpoint": getattr(sync_result, "resumed_from_checkpoint", False),
            "duration_seconds": duration_seconds,
            "sources_total": sync_result.sources_total,
            "sources_done": sync_result.sources_done,
        }
        await _append_history(connector_id, history_entry)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@router.get("/knowledge_base/connector_types", response_model=ConnectorTypesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_connector_types",
    error_code_prefix="KNOWLEDGE_CONNECTORS",
)
async def list_connector_types():
    """Return all registered connector types with readiness tier (Issue #4421).

    The frontend uses this to show a "Ready / Free key needed / Setup required"
    badge on each connector card before the user picks one.  Tier is read from
    the class attribute on each registered connector.
    """
    types = []
    for type_name, klass in ConnectorRegistry.registered_types().items():
        types.append(
            {
                "connector_type": type_name,
                "tier": int(getattr(klass, "tier", 0)),
                "output_schema": klass.output_schema(),
            }
        )
    types.sort(key=lambda t: (t["tier"], t["connector_type"]))
    return {"connector_types": types, "total": len(types)}


@router.get("/knowledge_base/connectors", response_model=ConnectorsListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_connectors",
    error_code_prefix="KNOWLEDGE_CONNECTORS",
)
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/knowledge_base/connectors", status_code=201, response_model=ConnectorCreateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_connector",
    error_code_prefix="KNOWLEDGE_CONNECTORS",
)
async def create_connector(request: CreateConnectorRequest):
    """Create a new connector, test the connection, and persist the config."""
    if request.connector_type not in _SUPPORTED_TYPES:
        raise HTTPException(
            status_code=422,
            detail="connector_type must be one of: %s" % _SUPPORTED_TYPES,
        )
    connector_id = str(uuid.uuid4())
    klass = ConnectorRegistry.get_registered_class(request.connector_type)
    if klass is None:
        raise HTTPException(
            status_code=422,
            detail="connector_type '%s' is not registered" % request.connector_type,
        )
    # Issue #8145: validate config against the connector's declared auth schema.
    auth_cls = klass.auth_schema()
    auth_type: str | None = None
    if auth_cls is not None:
        auth_type = auth_cls.__name__
        errors = validate_config_against_schema(auth_cls, request.config)
        if errors:
            raise HTTPException(
                status_code=422,
                detail="Auth config invalid for %s: %s" % (auth_type, "; ".join(errors)),
            )

    # ADR-007: extract sensitive credential fields and store encrypted.
    owner_id = getattr(request, "owner_id", None) or "system"
    safe_config = request.config
    secret_id: str | None = None
    if auth_cls is not None and hasattr(auth_cls, "__sensitive_fields__"):
        credential_store = get_credential_store()
        secret_id, safe_config = await credential_store.store(
            connector_id=connector_id,
            owner_id=owner_id,
            auth_cls=auth_cls,
            config=request.config,
        )

    cfg = ConnectorConfig(
        connector_id=connector_id,
        connector_type=request.connector_type,
        name=request.name,
        config=safe_config,
        enabled=request.enabled,
        verification_mode=request.verification_mode,
        schedule_cron=request.schedule_cron,
        include_patterns=request.include_patterns,
        exclude_patterns=request.exclude_patterns,
        tier=int(getattr(klass, "tier", 0)),
        auth_type=auth_type,
        max_concurrency=request.max_concurrency,
        secret_id=secret_id,
        owner_id=owner_id,
    )
    # For the connection test pass full config with credentials reconstructed.
    test_cfg = await _cfg_with_credentials(cfg, auth_cls)
    instance = await _load_or_create_instance(test_cfg)
    healthy = await instance.test_connection()
    if not healthy:
        ConnectorRegistry.remove_instance(connector_id)
        if secret_id:
            try:
                await get_credential_store().revoke(secret_id, owner_id)
            except Exception as exc:
                logger.warning("Failed to revoke credential after failed test: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Connection test failed — verify connector config and target availability",
        )
    await _save_connector(cfg)
    await _maybe_schedule(cfg)
    logger.info("Created connector %s (%s)", connector_id, request.connector_type)
    return {"connector_id": connector_id, "config": _cfg_to_dict(cfg)}


@router.get("/knowledge_base/connectors/scheduler/leader", response_model=ConnectorLeaderResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_scheduler_leader",
    error_code_prefix="KNOWLEDGE_CONNECTORS",
)
async def get_scheduler_leader():
    """Return the currently elected scheduler leader worker ID (Issue #8149).

    Returns ``leader: null`` when no worker holds the lease (scheduler idle or
    between leader transitions).
    """
    from autobot_shared.redis_client import get_async_redis_client
    from knowledge.connectors.scheduler import _LEADER_KEY

    redis = await get_async_redis_client(database="knowledge")
    if redis is None:
        return {"leader": None}
    raw = await redis.get(_LEADER_KEY)
    if raw is None:
        return {"leader": None}
    leader = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    return {"leader": leader}


@router.get("/knowledge_base/connectors/health", response_model=ConnectorsHealthResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="connectors_health",
    error_code_prefix="KNOWLEDGE_CONNECTORS",
)
async def connectors_health():
    """Aggregate test_connection() across all live connectors (Issue #4420).

    Ensures every live instance is hydrated from Redis first so the registry
    reflects every configured connector, then runs all ``test_connection()``
    calls concurrently via ``ConnectorRegistry.health_check_all``.

    Returns:
        Dict with keys ``healthy``, ``unavailable``, ``errors``, ``checked_at``.
    """
    await _hydrate_all_instances()
    return await ConnectorRegistry.health_check_all()


async def _hydrate_all_instances() -> None:
    """Load every persisted connector config into the live registry (Issue #4420).

    The registry only holds instances created via API calls; on cold start or
    after a restart, the instance map may be empty even though configs exist
    in Redis.  The health endpoint needs every configured connector to appear
    in the report, so we hydrate from Redis before aggregating.

    Degrades gracefully (Issue #5054): if Redis is unavailable, hydration
    returns without raising so the health endpoint can still report on the
    in-memory registry.  Per-connector load failures (Issue #5055) are
    isolated so a single corrupted record does not abort hydration of the
    remaining connectors.
    """
    try:
        ids = await _list_connector_ids()
    except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
        logger.warning(
            "Redis hydration failed — health check runs on in-memory registry only: %s",
            exc,
        )
        return

    for cid in ids:
        try:
            cfg = await _load_connector(cid)
            if cfg is None:
                continue
            await _load_or_create_instance(cfg)
        except Exception as exc:  # noqa: BLE001 — isolate bad records per Issue #5055
            logger.warning("Skipping corrupted connector %s: %s", cid, exc)


@router.get("/knowledge_base/connectors/{connector_id}", response_model=ConnectorDetailResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_connector",
    error_code_prefix="KNOWLEDGE_CONNECTORS",
)
async def get_connector(connector_id: str):
    """Return config and status for a single connector."""
    cfg = await _load_connector(connector_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=ERR_CONNECTOR_NOT_FOUND)
    status = await _get_status_for_config(cfg)
    return {"config": _cfg_to_dict(cfg), "status": status}


@router.put("/knowledge_base/connectors/{connector_id}", response_model=ConnectorUpdateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_connector",
    error_code_prefix="KNOWLEDGE_CONNECTORS",
)
async def update_connector(connector_id: str, request: UpdateConnectorRequest):
    """Update mutable fields of an existing connector."""
    cfg = await _load_connector(connector_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=ERR_CONNECTOR_NOT_FOUND)

    # ADR-007: if request includes sensitive fields, rotate the stored secret.
    if request.config is not None and cfg.secret_id and cfg.auth_type:
        klass = ConnectorRegistry.get_registered_class(cfg.connector_type)
        auth_cls = klass.auth_schema() if klass else None
        if auth_cls is not None and hasattr(auth_cls, "__sensitive_fields__"):
            sensitive = auth_cls.__sensitive_fields__
            new_creds = {k: v for k, v in request.config.items() if k in sensitive}
            if new_creds:
                owner_id = cfg.owner_id or "system"
                await get_credential_store().rotate(cfg.secret_id, new_creds, owner_id)
                # Strip sensitive fields from the config that goes to Redis.
                request.config = {k: v for k, v in request.config.items() if k not in sensitive}

    _apply_updates(cfg, request)
    await _save_connector(cfg)

    instance = ConnectorRegistry.get(connector_id)
    if instance is not None:
        instance.config = cfg

    await _reschedule(cfg)
    logger.info("Updated connector %s", connector_id)
    return {"connector_id": connector_id, "config": _cfg_to_dict(cfg)}


@router.delete("/knowledge_base/connectors/{connector_id}", status_code=204, response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_connector",
    error_code_prefix="KNOWLEDGE_CONNECTORS",
)
async def delete_connector(connector_id: str):
    """Remove a connector, stop its schedule, and delete its Redis keys."""
    cfg = await _load_connector(connector_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=ERR_CONNECTOR_NOT_FOUND)

    # ADR-007: revoke stored credentials before removing Redis key.
    if cfg.secret_id:
        owner_id = cfg.owner_id or "system"
        try:
            await get_credential_store().revoke(cfg.secret_id, owner_id)
        except Exception as exc:
            logger.warning("Failed to revoke credential for connector %s: %s", connector_id, exc)

    scheduler = get_connector_scheduler()
    await scheduler.stop(connector_id)
    ConnectorRegistry.remove_instance(connector_id)
    await _delete_connector_keys(connector_id)
    logger.info("Deleted connector %s", connector_id)


@router.post("/knowledge_base/connectors/{connector_id}/test", response_model=ConnectorTestResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_connector_connection",
    error_code_prefix="KNOWLEDGE_CONNECTORS",
)
async def test_connector_connection(connector_id: str):
    """Run a connection test against the connector's target."""
    cfg = await _load_connector(connector_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=ERR_CONNECTOR_NOT_FOUND)
    # ADR-007: reconstruct full config with credentials before invoking connector.
    klass = ConnectorRegistry.get_registered_class(cfg.connector_type)
    auth_cls = klass.auth_schema() if klass else None
    cfg = await _cfg_with_credentials(cfg, auth_cls)
    instance = await _load_or_create_instance(cfg)
    try:
        healthy = await instance.test_connection()
    except Exception as exc:
        logger.error("Connector %s connection test failed: %s", connector_id, exc)
        raise HTTPException(status_code=500, detail="Internal server error")
    return {"connector_id": connector_id, "healthy": healthy}


@router.post("/knowledge_base/connectors/{connector_id}/sync", response_model=ConnectorSyncResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="trigger_sync",
    error_code_prefix="KNOWLEDGE_CONNECTORS",
)
async def trigger_sync(
    connector_id: str,
    background_tasks: BackgroundTasks,
    incremental: bool = True,
):
    """Trigger a manual sync for a connector (runs in background)."""
    cfg = await _load_connector(connector_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=ERR_CONNECTOR_NOT_FOUND)
    background_tasks.add_task(_run_sync_background, connector_id, incremental)
    logger.info("Triggered sync for connector %s (incremental=%s)", connector_id, incremental)
    return {
        "connector_id": connector_id,
        "status": "sync_started",
        "incremental": incremental,
    }


@router.get("/knowledge_base/connectors/{connector_id}/history", response_model=ConnectorHistoryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_sync_history",
    error_code_prefix="KNOWLEDGE_CONNECTORS",
)
async def get_sync_history(connector_id: str, limit: int = 20):
    """Return recent sync results for a connector."""
    cfg = await _load_connector(connector_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=ERR_CONNECTOR_NOT_FOUND)
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


@router.get("/knowledge_base/connectors/{connector_id}/job", response_model=ConnectorJobResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_connector_job",
    error_code_prefix="KNOWLEDGE_CONNECTORS",
)
async def get_connector_job(connector_id: str):
    """Return in-flight job state for a connector sync (Issue #8149).

    Returns 404 when no sync is currently in flight (or the 24h TTL expired).
    """
    cfg = await _load_connector(connector_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=ERR_CONNECTOR_NOT_FOUND)

    from autobot_shared.redis_client import get_async_redis_client

    redis = await get_async_redis_client(database="knowledge")
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    job_key = "connector:%s:job:current" % connector_id
    raw = await redis.get(job_key)
    if raw is None:
        raise HTTPException(status_code=404, detail="No active job for connector %s" % connector_id)

    try:
        state = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except Exception as exc:
        logger.warning("Malformed job state for connector %s: %s", connector_id, exc)
        raise HTTPException(status_code=500, detail="Internal server error")

    return {
        "connector_id": connector_id,
        "job_id": state.get("job_id", ""),
        "started_at": state.get("started_at", ""),
        "status": state.get("status", "unknown"),
        "sources_total": state.get("sources_total", 0),
        "sources_done": state.get("sources_done", 0),
        "sources_failed": state.get("sources_failed", 0),
        "worker_id": state.get("worker_id", ""),
        "last_updated": state.get("last_updated", ""),
    }


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
            "last_sync_at": (status.last_sync_at.isoformat() if status.last_sync_at else None),
            "last_sync_status": status.last_sync_status,
            "documents_indexed": status.documents_indexed,
            "last_error": status.last_error,
            "scheduled": await scheduler.is_running(cfg.connector_id),
        }
    except Exception as exc:
        logger.warning("get_status failed for %s: %s", cfg.connector_id, exc)
        return {
            "connector_id": cfg.connector_id,
            "is_healthy": False,
            "last_error": "Status check failed",
        }


def _cfg_to_dict(cfg: ConnectorConfig) -> Dict[str, Any]:
    """Serialize ConnectorConfig to a plain dict for API responses.

    ADR-007: secret_id and owner_id are internal fields — never included in
    the public response.  Sensitive credential fields are already absent from
    cfg.config (stripped at write time).
    """
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
        "tier": _resolve_tier(cfg),
        "auth_type": getattr(cfg, "auth_type", None),
        "max_concurrency": cfg.max_concurrency,
    }


def _resolve_tier(cfg: ConnectorConfig) -> int:
    """Return the readiness tier, preferring the registered class attribute.

    Issue #4421: ``ConnectorConfig.tier`` defaults to 0 on old Redis records
    (before this field existed).  The class attribute on the registered
    connector is the source of truth — fall back to ``cfg.tier`` only when the
    type isn't registered.
    """
    klass = ConnectorRegistry.get_registered_class(cfg.connector_type)
    if klass is not None:
        return int(getattr(klass, "tier", 0))
    return int(getattr(cfg, "tier", 0))


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
    if req.max_concurrency is not None:
        cfg.max_concurrency = req.max_concurrency


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
