# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Trigger Service — Event-driven workflow triggers (#2139)

Implements five trigger types that fire workflow executions in response to
external events, schedules, pub/sub messages, file changes, or agent signals:

  WEBHOOK       — unique URL; external callers POST an event payload
  CRON          — periodic schedule expressed as a 5-field cron expression
  REDIS_PUBSUB  — subscribes to a Redis channel; fires on matching messages
  FILE_WATCH    — polls a Redis key for file-change notifications
  AGENT_EVENT   — fires when a named agent event is published to Redis

Design:
  - TriggerConfig  — plain dataclass; validated at registration time
  - TriggerDefinition — runtime record stored in Redis (workflows:triggers:*)
  - TriggerService — async lifecycle: register / unregister / list / fire
  - Inline cron parser — pure-Python next-run calculation (validate_cron_expression, next_cron_run)
  - WebhookHandler — generates stable per-trigger URLs; validates incoming POSTs

Redis layout (database "workflows"):
  workflows:trigger:<id>          — JSON serialised TriggerDefinition
  workflows:triggers:index        — Redis SET of all trigger IDs
  workflows:triggers:by_workflow:<workflow_id>  — Redis SET of trigger IDs
  workflows:trigger_secret:<id>   — HMAC secret for webhook validation
"""

import asyncio
import hashlib
import hmac
import json
import secrets
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.time_utils import now_utc
from constants.threshold_constants import TimingConstants
from constants.ttl_constants import TTL_90_DAYS

logger = get_logger(__name__)

# Lazy-initialised encryption service for webhook HMAC secrets at rest.
# Populated on first call to _get_encryption_service() to avoid import-time
# side effects and to tolerate environments where AUTOBOT_ENCRYPTION_KEY is
# not set until runtime.
_encryption_service = None


def _get_encryption_service():
    """Return a singleton EncryptionService, or None if unavailable."""
    global _encryption_service  # noqa: PLW0603
    if _encryption_service is None:
        try:
            from encryption_service import EncryptionService

            _encryption_service = EncryptionService()
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "EncryptionService unavailable — webhook secrets stored unencrypted: %s",
                exc,
            )
    return _encryption_service


# Redis TTL for trigger records: 90 days (triggers are long-lived)
_TRIGGER_TTL_SECONDS = TTL_90_DAYS

# Key prefixes — all under the "workflows" Redis database
_KEY_PREFIX = "workflows:trigger:"
_INDEX_KEY = "workflows:triggers:index"
_BY_WORKFLOW_PREFIX = "workflows:triggers:by_workflow:"
_SECRET_PREFIX = "workflows:trigger_secret:"


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class TriggerType(str, Enum):
    """Supported event-driven trigger types."""

    WEBHOOK = "webhook"
    CRON = "cron"
    REDIS_PUBSUB = "redis_pubsub"
    FILE_WATCH = "file_watch"
    AGENT_EVENT = "agent_event"


@dataclass
class TriggerConfig:
    """
    User-supplied trigger specification.

    Fields specific to each type:
      WEBHOOK:      secret_validation (bool, default True)
      CRON:         cron_expression (str, e.g. "*/5 * * * *")
      REDIS_PUBSUB: channel (str)
      FILE_WATCH:   redis_key (str), poll_interval_seconds (int)
      AGENT_EVENT:  event_name (str)

    Shared:
      conditions — optional list of condition dicts evaluated before firing.
                   Each dict: {"field": str, "op": str, "value": Any}
                   Supported ops: eq, ne, gt, lt, gte, lte, contains
      enabled    — when False the trigger is registered but never fires.
    """

    trigger_type: TriggerType
    workflow_id: str
    config: Dict[str, Any] = field(default_factory=dict)
    conditions: List[Dict[str, Any]] = field(default_factory=list)
    enabled: bool = True


@dataclass
class TriggerDefinition:
    """
    Persisted trigger record (stored in Redis).

    Created by TriggerService.register_trigger(); all fields are read-only
    after creation except last_fired and fire_count.
    """

    id: str
    trigger_type: TriggerType
    workflow_id: str
    config: Dict[str, Any]
    conditions: List[Dict[str, Any]]
    enabled: bool
    created_at: str  # ISO-8601
    last_fired: str | None = None  # ISO-8601 or None
    fire_count: int = 0

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict suitable for JSON encoding."""
        d = asdict(self)
        d["trigger_type"] = self.trigger_type.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TriggerDefinition":
        """Deserialise from a plain dict produced by to_dict()."""
        data = dict(data)
        data["trigger_type"] = TriggerType(data["trigger_type"])
        return cls(**data)


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------

_OPS: Dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "lt": lambda a, b: a < b,
    "gte": lambda a, b: a >= b,
    "lte": lambda a, b: a <= b,
    "contains": lambda a, b: b in a,
}


def _evaluate_conditions(conditions: List[Dict[str, Any]], payload: Dict[str, Any]) -> bool:
    """
    Return True when all conditions pass against *payload*.

    Each condition dict must contain: field, op, value.
    Unknown ops default to True (permissive) with a warning logged.
    Missing payload fields short-circuit to False.
    """
    for cond in conditions:
        field_path: str = cond.get("field", "")
        op: str = cond.get("op", "eq")
        expected = cond.get("value")

        # Resolve nested field path (e.g. "data.source")
        actual = payload
        for part in field_path.split("."):
            if not isinstance(actual, dict) or part not in actual:
                logger.debug(
                    "Condition field '%s' not found in payload — condition fails",
                    field_path,
                )
                return False
            actual = actual[part]

        evaluator = _OPS.get(op)
        if evaluator is None:
            logger.warning("Unknown condition op '%s' — treating as pass", op)
            continue

        try:
            if not evaluator(actual, expected):
                return False
        except (TypeError, KeyError) as exc:
            logger.debug("Condition evaluation error for field '%s': %s", field_path, exc)
            return False

    return True


# ---------------------------------------------------------------------------
# Pure-Python cron parser (no external deps)
# ---------------------------------------------------------------------------

_CRON_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]


def _parse_cron_field(field_str: str, min_val: int, max_val: int) -> List[int]:
    """
    Parse one cron field into a sorted list of matching integers.

    Supports: *, N, */step, N-M, N-M/step, comma-separated combinations.
    Raises ValueError for malformed fields.
    """
    values: set = set()
    for part in field_str.split(","):
        part = part.strip()
        if part == "*":
            values.update(range(min_val, max_val + 1))
        elif "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"Step must be > 0 in cron field '{field_str}'")
            if base == "*":
                start, end = min_val, max_val
            elif "-" in base:
                s, e = base.split("-", 1)
                start, end = int(s), int(e)
            else:
                start, end = int(base), max_val
            values.update(range(start, end + 1, step))
        elif "-" in part:
            s, e = part.split("-", 1)
            values.update(range(int(s), int(e) + 1))
        else:
            values.add(int(part))

    out = sorted(v for v in values if min_val <= v <= max_val)
    if not out:
        raise ValueError(f"Cron field '{field_str}' resolved to no values")
    return out


def _normalize_dow_field(field: str) -> str:
    """Normalize day-of-week: replace 7 with 0 (both mean Sunday).

    Handles scalars (7->0), lists (0,7->0,0), ranges (1-7->1-6,0),
    range-steps (1-7/2->1-6/2,0), and steps (*/7 left unchanged).
    """
    import re

    def _replace_token(token: str) -> str:
        # Range-step like "1-7/2" or "5-7/2"
        m = re.fullmatch(r"(\d+)-(\d+)/(\d+)", token)
        if m:
            lo, hi, step = int(m.group(1)), int(m.group(2)), m.group(3)
            if hi == 7:
                if lo == 0:
                    return f"0-6/{step}"
                return f"{lo}-6/{step},0"  # wrap: range excludes 7, add Sunday(0)
            return token
        # Range like "1-7" or "0-7"
        m = re.fullmatch(r"(\d+)-(\d+)", token)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if hi == 7:
                if lo == 0:
                    return "0-6"
                return f"{lo}-6,0"  # wrap: Mon-Sun = Mon-Sat + Sun(0)
            return token
        # Step like "*/7" -- leave as-is (unusual but not invalid)
        if re.fullmatch(r"\*/\d+", token):
            return token
        # Scalar
        return "0" if token == "7" else token

    # Split on comma, normalize each part, rejoin
    return ",".join(_replace_token(part) for part in field.split(","))


def validate_cron_expression(expression: str) -> bool:
    """Return True when *expression* is a valid 5-field cron string."""
    try:
        parts = expression.split()
        if len(parts) != 5:
            return False
        for i, (part, (lo, hi)) in enumerate(zip(parts, _CRON_RANGES)):
            if i == 4:
                part = _normalize_dow_field(part)
            _parse_cron_field(part, lo, hi)
        return True
    except (ValueError, TypeError):
        return False


def next_cron_run(expression: str, after: datetime | None = None) -> datetime:
    """
    Return the next UTC datetime when *expression* fires after *after*.

    *after* defaults to utcnow().  The returned datetime is always in UTC
    and always strictly after *after* (minimum 1-minute advance).

    Raises ValueError for invalid expressions.
    """
    parts = expression.split()
    if len(parts) != 5:
        raise ValueError(f"Cron expression must have 5 fields, got: '{expression}'")

    minutes = _parse_cron_field(parts[0], 0, 59)
    hours = _parse_cron_field(parts[1], 0, 23)
    days = _parse_cron_field(parts[2], 1, 31)
    months = _parse_cron_field(parts[3], 1, 12)
    weekdays = _parse_cron_field(_normalize_dow_field(parts[4]), 0, 6)

    base = after or now_utc()
    # Advance by at least one minute
    from datetime import timedelta

    candidate = base.replace(second=0, microsecond=0) + timedelta(minutes=1)

    # Iterate up to ~4 years to find a match (avoids infinite loop for impossible combos)
    max_iterations = 60 * 24 * 366 * 4
    for _ in range(max_iterations):
        if candidate.month not in months:
            # Fast-forward to the first valid month in the next year if needed
            next_month = next((m for m in months if m > candidate.month), months[0])
            if next_month <= candidate.month:
                candidate = candidate.replace(year=candidate.year + 1, month=next_month, day=1, hour=0, minute=0)
            else:
                candidate = candidate.replace(month=next_month, day=1, hour=0, minute=0)
            continue

        if candidate.day not in days or candidate.weekday() not in [(w - 1) % 7 for w in weekdays]:
            candidate += timedelta(days=1)
            candidate = candidate.replace(hour=0, minute=0)
            continue

        if candidate.hour not in hours:
            next_hour = next((h for h in hours if h > candidate.hour), None)
            if next_hour is None:
                candidate += timedelta(days=1)
                candidate = candidate.replace(hour=0, minute=0)
            else:
                candidate = candidate.replace(hour=next_hour, minute=minutes[0])
            continue

        if candidate.minute not in minutes:
            next_min = next((m for m in minutes if m > candidate.minute), None)
            if next_min is None:
                next_hour = next((h for h in hours if h > candidate.hour), None)
                if next_hour is None:
                    candidate += timedelta(days=1)
                    candidate = candidate.replace(hour=hours[0], minute=minutes[0])
                else:
                    candidate = candidate.replace(hour=next_hour, minute=minutes[0])
            else:
                candidate = candidate.replace(minute=next_min)
            continue

        return candidate

    raise ValueError(f"Could not find next run time for cron expression '{expression}'")


# ---------------------------------------------------------------------------
# TriggerService
# ---------------------------------------------------------------------------

# Type alias for the workflow-launch callback
WorkflowLauncher = Callable[[str, Dict[str, Any]], Coroutine[Any, Any, None]]


class TriggerService:
    """
    Manages event-driven trigger definitions and fires workflow executions.

    Lifecycle:
      start(launcher)  — begin background loops (cron, pubsub, file watch)
      stop()           — cancel all background tasks
      register_trigger(config)   — persist a new trigger; return trigger_id
      unregister_trigger(id)     — remove a trigger and cancel its task
      list_triggers(workflow_id) — return persisted TriggerDefinitions
      fire_trigger(id, payload)  — manually fire a trigger with a payload

    The *launcher* callable receives (workflow_id, payload) and is responsible
    for actually starting the workflow execution.  It is set by start() and
    must be an async coroutine function.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, asyncio.Task] = {}
        self._launcher: WorkflowLauncher | None = None
        self._running = False
        # Keyed by trigger_id; values are HMAC secrets for webhook validation
        self._webhook_secrets: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, launcher: WorkflowLauncher) -> None:
        """
        Start background tasks for all enabled CRON / PUBSUB / FILE_WATCH triggers.

        *launcher* is called with (workflow_id, event_payload) whenever a trigger
        fires.  Must be an async coroutine function.
        """
        if self._running:
            logger.warning("TriggerService.start() called while already running")
            return
        self._launcher = launcher
        self._running = True

        triggers = await self._load_all_triggers()
        started = 0
        for tdef in triggers:
            if tdef.enabled and tdef.trigger_type in (
                TriggerType.CRON,
                TriggerType.REDIS_PUBSUB,
                TriggerType.FILE_WATCH,
                TriggerType.AGENT_EVENT,
            ):
                self._spawn_task(tdef)
                started += 1

        logger.info(
            "TriggerService started: %d triggers loaded, %d background tasks spawned",
            len(triggers),
            started,
        )

    async def stop(self) -> None:
        """Cancel all background trigger tasks."""
        self._running = False
        for trigger_id, task in list(self._tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.debug("Trigger task cancelled: %s", trigger_id)
        self._tasks.clear()
        logger.info("TriggerService stopped")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def register_trigger(self, config: TriggerConfig) -> str:
        """
        Validate *config*, persist to Redis, start background task if needed.

        Returns the new trigger_id (UUID string).
        Raises ValueError for invalid configurations.
        """
        self._validate_config(config)

        trigger_id = str(uuid.uuid4())
        now = now_utc().isoformat()

        tdef = TriggerDefinition(
            id=trigger_id,
            trigger_type=config.trigger_type,
            workflow_id=config.workflow_id,
            config=config.config,
            conditions=config.conditions,
            enabled=config.enabled,
            created_at=now,
        )

        await self._persist_trigger(tdef)
        logger.info(
            "Trigger registered: id=%s type=%s workflow=%s",
            trigger_id,
            config.trigger_type.value,
            config.workflow_id,
        )

        # Generate HMAC secret for webhook triggers
        if config.trigger_type == TriggerType.WEBHOOK:
            secret = secrets.token_hex(32)
            self._webhook_secrets[trigger_id] = secret
            await self._store_webhook_secret(trigger_id, secret)

        # Start background task for non-webhook triggers if service is running
        if self._running and config.enabled and config.trigger_type != TriggerType.WEBHOOK:
            self._spawn_task(tdef)

        return trigger_id

    async def unregister_trigger(self, trigger_id: str) -> None:
        """Remove a trigger from Redis and cancel its background task."""
        task = self._tasks.pop(trigger_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await self._delete_trigger(trigger_id)
        self._webhook_secrets.pop(trigger_id, None)
        logger.info("Trigger unregistered: %s", trigger_id)

    async def list_triggers(self, workflow_id: str | None = None) -> List[TriggerDefinition]:
        """
        Return persisted trigger definitions, optionally filtered by workflow_id.

        Returns an empty list when no triggers exist or Redis is unavailable.
        """
        try:
            redis = get_redis_client(database="workflows")
            if workflow_id:
                key = f"{_BY_WORKFLOW_PREFIX}{workflow_id}"
                trigger_ids = redis.smembers(key)
            else:
                trigger_ids = redis.smembers(_INDEX_KEY)

            results: List[TriggerDefinition] = []
            for tid in trigger_ids:
                tid_str = tid.decode() if isinstance(tid, bytes) else tid
                raw = redis.get(f"{_KEY_PREFIX}{tid_str}")
                if raw:
                    try:
                        results.append(TriggerDefinition.from_dict(json.loads(raw)))
                    except (KeyError, ValueError, json.JSONDecodeError) as exc:
                        logger.warning("Failed to deserialise trigger %s: %s", tid_str, exc)
            return results
        except Exception as exc:
            logger.error("list_triggers failed: %s", exc)
            return []

    async def fire_trigger(self, trigger_id: str, event_payload: Dict[str, Any]) -> bool:
        """
        Fire a trigger manually with *event_payload*.

        Evaluates conditions, launches the workflow if they pass, updates
        last_fired and fire_count in Redis.

        Returns True when the workflow launch was attempted, False otherwise.
        """
        tdef = await self._load_trigger(trigger_id)
        if tdef is None:
            logger.warning("fire_trigger: trigger not found: %s", trigger_id)
            return False

        if not tdef.enabled:
            logger.debug("fire_trigger: trigger %s is disabled — skipping", trigger_id)
            return False

        if not _evaluate_conditions(tdef.conditions, event_payload):
            logger.debug("fire_trigger: conditions not met for trigger %s — skipping", trigger_id)
            return False

        await self._launch_workflow(tdef, event_payload)
        return True

    # ------------------------------------------------------------------
    # Webhook helpers (called by the API layer)
    # ------------------------------------------------------------------

    async def validate_webhook_signature(self, trigger_id: str, body: bytes, signature: str) -> bool:
        """
        Return True when the HMAC-SHA256 *signature* matches *body*.

        The signature header format expected: ``sha256=<hex-digest>``.
        Timing-safe comparison used to prevent timing attacks.
        """
        secret = await self._get_webhook_secret(trigger_id)
        if not secret:
            logger.warning("validate_webhook_signature: no secret found for trigger %s", trigger_id)
            return False

        expected_sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature)

    def get_webhook_url_path(self, trigger_id: str) -> str:
        """Return the URL path for the webhook endpoint of *trigger_id*."""
        return f"/api/triggers/webhook/{trigger_id}"

    # ------------------------------------------------------------------
    # Internal — background task dispatch
    # ------------------------------------------------------------------

    def _spawn_task(self, tdef: TriggerDefinition) -> None:
        """Create and register an asyncio task for *tdef*."""
        trigger_id = tdef.id
        if trigger_id in self._tasks:
            self._tasks[trigger_id].cancel()

        if tdef.trigger_type == TriggerType.CRON:
            coro = self._cron_loop(tdef)
        elif tdef.trigger_type == TriggerType.REDIS_PUBSUB:
            coro = self._pubsub_loop(tdef)
        elif tdef.trigger_type == TriggerType.FILE_WATCH:
            coro = self._file_watch_loop(tdef)
        elif tdef.trigger_type == TriggerType.AGENT_EVENT:
            coro = self._agent_event_loop(tdef)
        else:
            logger.warning("No background task for trigger type %s", tdef.trigger_type)
            return

        task = asyncio.create_task(coro, name=f"trigger-{trigger_id[:8]}")
        self._tasks[trigger_id] = task
        logger.debug(
            "Spawned background task for trigger %s (%s)",
            trigger_id,
            tdef.trigger_type.value,
        )

    # ------------------------------------------------------------------
    # Background loops
    # ------------------------------------------------------------------

    async def _cron_loop(self, tdef: TriggerDefinition) -> None:
        """Sleep until next cron run, fire, repeat."""
        expression: str = tdef.config.get("cron_expression", "")
        logger.info("Cron loop started: trigger=%s expr='%s'", tdef.id, expression)

        while True:
            try:
                now = now_utc()
                next_run = next_cron_run(expression, after=now)
                delay = (next_run - now).total_seconds()
                logger.debug(
                    "Cron trigger %s: next run in %.1fs at %s",
                    tdef.id,
                    delay,
                    next_run.isoformat(),
                )
                await asyncio.sleep(max(delay, 0))

                # Reload to pick up any enable/disable changes
                current = await self._load_trigger(tdef.id)
                if current is None or not current.enabled:
                    logger.info("Cron trigger %s disabled — stopping loop", tdef.id)
                    return

                fired_at = now_utc().isoformat()
                await self._launch_workflow(current, {"trigger_type": "cron", "fired_at": fired_at})

            except asyncio.CancelledError:
                logger.info("Cron loop cancelled: trigger=%s", tdef.id)
                return
            except ValueError as exc:
                logger.error(
                    "Invalid cron expression for trigger %s: %s — stopping loop",
                    tdef.id,
                    exc,
                )
                return
            except Exception:
                logger.exception("Cron loop error for trigger %s (continuing)", tdef.id)
                await asyncio.sleep(TimingConstants.SESSION_CLEANUP_INTERVAL)

    async def _pubsub_loop(self, tdef: TriggerDefinition) -> None:
        """Subscribe to a Redis channel and fire on matching messages."""
        channel: str = tdef.config.get("channel", "")
        if not channel:
            logger.error("PubSub trigger %s missing 'channel' config — stopping", tdef.id)
            return

        logger.info("PubSub loop started: trigger=%s channel=%s", tdef.id, channel)

        while True:
            try:
                redis = get_redis_client(database="main")
                pubsub = redis.pubsub()
                pubsub.subscribe(channel)
                logger.debug("PubSub trigger %s: subscribed to '%s'", tdef.id, channel)

                for message in pubsub.listen():
                    if message["type"] != "message":
                        continue

                    current = await self._load_trigger(tdef.id)
                    if current is None or not current.enabled:
                        logger.info("PubSub trigger %s disabled — stopping loop", tdef.id)
                        pubsub.unsubscribe(channel)
                        return

                    try:
                        raw_data = message["data"]
                        payload = json.loads(raw_data) if isinstance(raw_data, (str, bytes)) else {"data": raw_data}
                    except (json.JSONDecodeError, TypeError):
                        payload = {"raw": str(message["data"])}

                    payload.setdefault("trigger_type", "redis_pubsub")
                    payload.setdefault("channel", channel)

                    await self.fire_trigger(tdef.id, payload)

            except asyncio.CancelledError:
                logger.info("PubSub loop cancelled: trigger=%s", tdef.id)
                return
            except Exception:
                logger.exception("PubSub loop error for trigger %s (will reconnect in 30s)", tdef.id)
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_LONG_DELAY)

    async def _file_watch_loop(self, tdef: TriggerDefinition) -> None:
        """Poll a Redis key for file-change notifications."""
        redis_key: str = tdef.config.get("redis_key", "")
        poll_interval: int = int(tdef.config.get("poll_interval_seconds", 10))

        if not redis_key:
            logger.error("FileWatch trigger %s missing 'redis_key' config — stopping", tdef.id)
            return

        logger.info(
            "FileWatch loop started: trigger=%s key=%s interval=%ss",
            tdef.id,
            redis_key,
            poll_interval,
        )

        last_value: str | None = None

        while True:
            try:
                await asyncio.sleep(poll_interval)

                current = await self._load_trigger(tdef.id)
                if current is None or not current.enabled:
                    logger.info("FileWatch trigger %s disabled — stopping loop", tdef.id)
                    return

                redis = get_redis_client(database="main")
                raw = redis.get(redis_key)
                current_value = raw.decode() if isinstance(raw, bytes) else raw

                if current_value is not None and current_value != last_value:
                    logger.debug(
                        "FileWatch trigger %s: change detected on key '%s'",
                        tdef.id,
                        redis_key,
                    )
                    payload: Dict[str, Any] = {
                        "trigger_type": "file_watch",
                        "redis_key": redis_key,
                        "value": current_value,
                        "fired_at": now_utc().isoformat(),
                    }
                    if last_value is not None:
                        payload["previous_value"] = last_value
                    last_value = current_value
                    await self.fire_trigger(tdef.id, payload)
                elif current_value is not None:
                    last_value = current_value

            except asyncio.CancelledError:
                logger.info("FileWatch loop cancelled: trigger=%s", tdef.id)
                return
            except Exception:
                logger.exception("FileWatch loop error for trigger %s (continuing)", tdef.id)

    async def _agent_event_loop(self, tdef: TriggerDefinition) -> None:
        """Subscribe to agent-event Redis channel and fire on matching event_name."""
        event_name: str = tdef.config.get("event_name", "")
        channel = f"autobot:agent_events:{event_name}" if event_name else "autobot:agent_events"

        logger.info(
            "AgentEvent loop started: trigger=%s event=%s channel=%s",
            tdef.id,
            event_name,
            channel,
        )

        while True:
            try:
                redis = get_redis_client(database="main")
                pubsub = redis.pubsub()
                pubsub.subscribe(channel)

                for message in pubsub.listen():
                    if message["type"] != "message":
                        continue

                    current = await self._load_trigger(tdef.id)
                    if current is None or not current.enabled:
                        logger.info("AgentEvent trigger %s disabled — stopping", tdef.id)
                        pubsub.unsubscribe(channel)
                        return

                    try:
                        raw_data = message["data"]
                        payload = json.loads(raw_data) if isinstance(raw_data, (str, bytes)) else {"data": raw_data}
                    except (json.JSONDecodeError, TypeError):
                        payload = {"raw": str(message["data"])}

                    payload.setdefault("trigger_type", "agent_event")
                    payload.setdefault("event_name", event_name)

                    await self.fire_trigger(tdef.id, payload)

            except asyncio.CancelledError:
                logger.info("AgentEvent loop cancelled: trigger=%s", tdef.id)
                return
            except Exception:
                logger.exception(
                    "AgentEvent loop error for trigger %s (will reconnect in 30s)",
                    tdef.id,
                )
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_LONG_DELAY)

    # ------------------------------------------------------------------
    # Internal — launch & persistence
    # ------------------------------------------------------------------

    async def _launch_workflow(self, tdef: TriggerDefinition, payload: Dict[str, Any]) -> None:
        """Call the launcher callback and update last_fired / fire_count."""
        if self._launcher is None:
            logger.warning("TriggerService: no launcher set — cannot fire trigger %s", tdef.id)
            return

        logger.info(
            "Firing trigger %s (type=%s workflow=%s)",
            tdef.id,
            tdef.trigger_type.value,
            tdef.workflow_id,
        )

        try:
            await self._launcher(tdef.workflow_id, payload)
        except Exception as exc:
            logger.error("Launcher raised for trigger %s: %s", tdef.id, exc)

        # Always update metadata, even on launcher error
        await self._update_fire_metadata(tdef.id)

    async def _update_fire_metadata(self, trigger_id: str) -> None:
        """Increment fire_count and set last_fired on the persisted record."""
        try:
            redis = get_redis_client(database="workflows")
            key = f"{_KEY_PREFIX}{trigger_id}"
            raw = redis.get(key)
            if not raw:
                return
            data = json.loads(raw)
            data["last_fired"] = now_utc().isoformat()
            data["fire_count"] = data.get("fire_count", 0) + 1
            redis.setex(key, _TRIGGER_TTL_SECONDS, json.dumps(data))
        except Exception as exc:
            logger.warning("_update_fire_metadata failed for %s: %s", trigger_id, exc)

    async def _load_trigger(self, trigger_id: str) -> TriggerDefinition | None:
        """Load and deserialise a single TriggerDefinition from Redis."""
        try:
            redis = get_redis_client(database="workflows")
            raw = redis.get(f"{_KEY_PREFIX}{trigger_id}")
            if not raw:
                return None
            return TriggerDefinition.from_dict(json.loads(raw))
        except Exception as exc:
            logger.error("_load_trigger %s failed: %s", trigger_id, exc)
            return None

    async def _load_all_triggers(self) -> List[TriggerDefinition]:
        """Load all persisted TriggerDefinitions from Redis."""
        return await self.list_triggers()

    async def _persist_trigger(self, tdef: TriggerDefinition) -> None:
        """Write *tdef* to Redis and add to index sets."""
        redis = get_redis_client(database="workflows")
        key = f"{_KEY_PREFIX}{tdef.id}"
        redis.setex(key, _TRIGGER_TTL_SECONDS, json.dumps(tdef.to_dict()))
        redis.sadd(_INDEX_KEY, tdef.id)
        redis.sadd(f"{_BY_WORKFLOW_PREFIX}{tdef.workflow_id}", tdef.id)

    async def _delete_trigger(self, trigger_id: str) -> None:
        """Remove a trigger from Redis index sets and delete its key."""
        try:
            redis = get_redis_client(database="workflows")
            raw = redis.get(f"{_KEY_PREFIX}{trigger_id}")
            if raw:
                data = json.loads(raw)
                workflow_id = data.get("workflow_id", "")
                if workflow_id:
                    redis.srem(f"{_BY_WORKFLOW_PREFIX}{workflow_id}", trigger_id)
            redis.delete(f"{_KEY_PREFIX}{trigger_id}")
            redis.srem(_INDEX_KEY, trigger_id)
            redis.delete(f"{_SECRET_PREFIX}{trigger_id}")
        except Exception as exc:
            logger.error("_delete_trigger %s failed: %s", trigger_id, exc)

    async def _store_webhook_secret(self, trigger_id: str, secret: str) -> None:
        """Persist HMAC secret for webhook signature validation.

        The secret is encrypted at rest using AES-GCM before writing to Redis
        so that a Redis dump does not expose raw HMAC signing keys.
        """
        try:
            enc = _get_encryption_service()
            stored = enc.encrypt(secret) if enc is not None else secret
            redis = get_redis_client(database="workflows")
            redis.setex(
                f"{_SECRET_PREFIX}{trigger_id}",
                _TRIGGER_TTL_SECONDS,
                stored,
            )  # codeql[py/clear-text-storage-sensitive-data]
        except Exception as exc:
            logger.warning("_store_webhook_secret failed for %s: %s", trigger_id, exc)

    async def _get_webhook_secret(self, trigger_id: str) -> str | None:
        """Retrieve HMAC secret; prefer in-memory cache, fall back to Redis."""
        if trigger_id in self._webhook_secrets:
            return self._webhook_secrets[trigger_id]
        try:
            redis = get_redis_client(database="workflows")
            raw = redis.get(f"{_SECRET_PREFIX}{trigger_id}")
            if raw:
                stored = raw.decode() if isinstance(raw, bytes) else raw
                enc = _get_encryption_service()
                secret = enc.decrypt(stored) if enc is not None else stored
                self._webhook_secrets[trigger_id] = secret
                return secret
        except Exception as exc:
            logger.warning("_get_webhook_secret failed for %s: %s", trigger_id, exc)
        return None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_config(self, config: TriggerConfig) -> None:
        """
        Raise ValueError when *config* is missing required fields.

        Type-specific required fields:
          CRON:         cron_expression (valid 5-field expression)
          REDIS_PUBSUB: channel
          FILE_WATCH:   redis_key
          AGENT_EVENT:  event_name
          WEBHOOK:      no extra required fields
        """
        if not config.workflow_id:
            raise ValueError("TriggerConfig.workflow_id must not be empty")

        t = config.trigger_type
        cfg = config.config

        if t == TriggerType.CRON:
            expr = cfg.get("cron_expression", "")
            if not expr:
                raise ValueError("CRON trigger requires config.cron_expression")
            if not validate_cron_expression(expr):
                raise ValueError(f"Invalid cron expression: '{expr}'")

        elif t == TriggerType.REDIS_PUBSUB:
            if not cfg.get("channel"):
                raise ValueError("REDIS_PUBSUB trigger requires config.channel")

        elif t == TriggerType.FILE_WATCH:
            if not cfg.get("redis_key"):
                raise ValueError("FILE_WATCH trigger requires config.redis_key")
            interval = cfg.get("poll_interval_seconds", 10)
            if int(interval) < 1:
                raise ValueError("FILE_WATCH poll_interval_seconds must be >= 1")

        elif t == TriggerType.AGENT_EVENT:
            if not cfg.get("event_name"):
                raise ValueError("AGENT_EVENT trigger requires config.event_name")
