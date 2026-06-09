# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Abstract Connector Base Class

Issue #1254: Defines the interface every source connector must implement.
Concrete connectors subclass AbstractConnector and register via
@ConnectorRegistry.register("<type>").
Issue #8144: Added fetch_with_retry(), should_retry(), backoff_time() for
built-in exponential-backoff retry on transient HTTP errors.
Issue #8145: Added auth_schema() classmethod for typed credential declarations.
Issue #8146: Added _write_checkpoint(), _read_checkpoint(), _clear_checkpoint()
and updated sync() to skip already-processed sources on restart.
Issue #8152: Added config_version and migrate_config() hook.
"""

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Set, TypeVar

from autobot_shared.datetime_utils import datetime_now
from autobot_shared.logging_manager import get_logger
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ConnectorStatus,
    ContentResult,
    SourceInfo,
    SyncResult,
)

T = TypeVar("T")

# Issue #8144: Default retryable HTTP status codes for fetch_with_retry().
_DEFAULT_RETRYABLE_STATUS: tuple = (429, 500, 502, 503, 504)

# Issue #8146: Checkpoint TTL — 24h prevents stale state on repeated crash loops.
_CHECKPOINT_TTL_SECONDS = 86400

_JOB_KEY_SUFFIX = ":job:current"
_JOB_TTL_S = 86400  # 24 h


class RetryableError(Exception):
    """Signals a transient failure that fetch_with_retry should retry (Issue #8144)."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class AbstractConnector(ABC):
    """Base class for all knowledge source connectors.

    Subclasses must set the class attribute ``connector_type`` and implement
    the four abstract methods.  The default ``sync()`` method orchestrates
    change detection → fetch → ingest and can be overridden when a connector
    needs a custom sync strategy.

    Subclasses SHOULD also declare their setup-complexity ``tier`` (Issue #4421):

    * ``tier = 0`` — Zero-config. Works immediately once the target is
      reachable (local file server, unauthenticated web crawl, local audio).
    * ``tier = 1`` — Needs a free API key or env var (e.g. Notion integration
      token, RSS with key).
    * ``tier = 2`` — Needs credentials, OAuth, a cookie, or a private DB
      connection string (e.g. database, GitHub private repos).

    The tier is surfaced to the UI via ``/knowledge_base/connector_types`` so
    users see a readiness badge before they start filling out the config form.
    """

    connector_type: str = ""
    tier: int = 0
    config_version: int = 1

    @classmethod
    def migrate_config(cls, stored_version: int, config: dict) -> dict:
        """Migrate config dict from stored_version to current config_version.

        No-op by default — subclasses override and apply sequential migrations.
        Issue #8152.
        """
        return config

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
        self.logger = get_logger("%s.%s" % (__name__, self.connector_type or type(self).__name__))

    # ------------------------------------------------------------------
    # Abstract interface — every connector MUST implement these
    # ------------------------------------------------------------------

    @abstractmethod
    async def test_connection(self) -> bool:
        """Verify that the source is reachable and credentials are valid."""

    @abstractmethod
    async def discover_sources(self) -> List[SourceInfo]:
        """Return all sources currently available from this connector."""

    @abstractmethod
    async def fetch_content(self, source_id: str) -> ContentResult | None:
        """Fetch and return the content for a single source by ID."""

    @abstractmethod
    async def detect_changes(self, since: datetime | None = None) -> List[ChangeInfo]:
        """Return sources that changed since *since* (or all if since is None)."""

    # ------------------------------------------------------------------
    # Issue #8144 — HTTP retry with exponential backoff
    # ------------------------------------------------------------------

    @classmethod
    def auth_schema(cls) -> type | None:
        """Return the auth dataclass this connector expects, or None (Issue #8145).

        Override in subclasses to declare the expected credential type:
            return BearerAuth  # from knowledge.connectors.auth
        """
        return None

    @classmethod
    def output_schema(cls) -> Dict[str, Any]:
        """Return a JSONSchema dict describing ContentResult.metadata shape.

        Issue #8147: Used for validation at ingest time and UI field rendering.
        Default returns an empty dict (no schema → backward compatible).
        """
        return {}

    @property
    def max_concurrency(self) -> int:
        """Max parallel source fetches. Default 1 (sequential, backward compatible).

        Issue #8148: Connectors opt in by overriding this to a value > 1.
        The config field ``max_concurrency`` takes precedence when set.
        """
        cfg_val = self.config.max_concurrency
        return cfg_val if cfg_val is not None else 1

    async def fetch_with_retry(
        self,
        fetch_fn: Callable[[], Awaitable[T]],
        max_attempts: int = 5,
        backoff_base: float = 2.0,
        retryable_status: tuple = _DEFAULT_RETRYABLE_STATUS,
    ) -> T:
        """Call *fetch_fn* with exponential backoff on transient failures.

        Raises RetryableError (or the original exception) on exhausted attempts.
        Non-retryable exceptions propagate immediately without retrying.

        Args:
            fetch_fn: Zero-argument async callable to retry.
            max_attempts: Total attempts before re-raising the last exception.
            backoff_base: Base for the exponential delay; passed to backoff_time().
            retryable_status: HTTP status codes to treat as transient (informational
                only — actual retry decisions delegate to should_retry()).
        """
        last_exc: Exception = RetryableError("No attempts made")
        for attempt in range(1, max_attempts + 1):
            try:
                return await fetch_fn()
            except Exception as exc:
                if not self.should_retry(exc):
                    raise
                last_exc = exc
                if attempt < max_attempts:
                    delay = self.backoff_time(attempt)
                    self.logger.warning(
                        "Connector %s retry %d/%d after %.1fs: %s",
                        self.config.connector_id,
                        attempt,
                        max_attempts,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
        raise last_exc

    def should_retry(self, exception: Exception) -> bool:
        """Return True when *exception* represents a transient failure (Issue #8144).

        Override to customise retry decisions.  The default retries on any
        RetryableError; subclasses can widen or narrow the set.
        """
        return isinstance(exception, RetryableError)

    def backoff_time(self, attempt: int) -> float:
        """Return seconds to wait before the *attempt*-th retry (1-indexed, Issue #8144).

        Default: exponential — 1s, 2s, 4s, 8s, … Override for jitter or custom curves.
        """
        return 2.0 ** (attempt - 1)

    # ------------------------------------------------------------------
    # Issue #8146 — Mid-sync checkpoint state
    # ------------------------------------------------------------------

    async def _write_checkpoint(self, source_id: str) -> None:
        """Record *source_id* as processed in the Redis checkpoint set."""
        try:
            from autobot_shared.redis_client import get_async_redis_client

            redis = await get_async_redis_client()
            if redis is None:
                return
            key = "connector:%s:checkpoint" % self.config.connector_id
            await redis.sadd(key, source_id)
            await redis.expire(key, _CHECKPOINT_TTL_SECONDS)
        except Exception as exc:
            self.logger.warning("checkpoint write failed for %s: %s", source_id, exc)

    async def _read_checkpoint(self) -> Set[str]:
        """Return the set of already-processed source IDs from Redis."""
        try:
            from autobot_shared.redis_client import get_async_redis_client

            redis = await get_async_redis_client()
            if redis is None:
                return set()
            key = "connector:%s:checkpoint" % self.config.connector_id
            members = await redis.smembers(key)
            return {m.decode("utf-8") if isinstance(m, bytes) else m for m in members}
        except Exception as exc:
            self.logger.warning("checkpoint read failed: %s", exc)
            return set()

    async def _clear_checkpoint(self) -> None:
        """Delete the Redis checkpoint for this connector."""
        try:
            from autobot_shared.redis_client import get_async_redis_client

            redis = await get_async_redis_client()
            if redis is None:
                return
            key = "connector:%s:checkpoint" % self.config.connector_id
            await redis.delete(key)
        except Exception as exc:
            self.logger.warning("checkpoint clear failed: %s", exc)

    # ------------------------------------------------------------------
    # Default implementations — connectors may override
    # ------------------------------------------------------------------

    async def get_status(self) -> ConnectorStatus:
        """Return current health status for this connector."""
        try:
            healthy = await self.test_connection()
        except Exception as exc:
            self.logger.warning("test_connection raised: %s", exc)
            healthy = False

        last_sync_at = self.config.last_sync_at
        last_sync_status = "never" if last_sync_at is None else "success"

        return ConnectorStatus(
            connector_id=self.config.connector_id,
            is_healthy=healthy,
            last_sync_at=last_sync_at,
            last_sync_status=last_sync_status,
            documents_indexed=0,
            last_error=None,
        )

    async def sync(self, incremental: bool = True) -> SyncResult:
        """Run a full sync: detect changes, fetch content, ingest into KB.

        Each source is processed independently so a single failure does not
        abort the rest of the sync.  On restart after a crash, sources that
        were already successfully processed are skipped via a Redis checkpoint
        (Issue #8146).  When ``max_concurrency > 1``, sources are processed
        in parallel via ``asyncio.gather + Semaphore`` (Issue #8148).

        Args:
            incremental: When True, only process sources that changed since
                         ``config.last_sync_at``.  When False, re-process all
                         sources and ignore/clear any existing checkpoint.

        Returns:
            SyncResult with counts and any per-source errors.
        """
        started_at = datetime_now()
        result = SyncResult(
            connector_id=self.config.connector_id,
            started_at=started_at,
            completed_at=None,
            status="failed",
        )

        if not incremental:
            # Full-refresh always ignores and clears any stale checkpoint.
            await self._clear_checkpoint()

        since = self.config.last_sync_at if incremental else None
        job_id = str(uuid.uuid4())

        try:
            already_processed = await self._read_checkpoint()
            if already_processed:
                self.logger.info(
                    "Connector %s resuming from checkpoint (%d sources already processed)",
                    self.config.connector_id,
                    len(already_processed),
                )
                result.resumed_from_checkpoint = True

            changes = await self.detect_changes(since=since)
            result.sources_total = len(changes)
            self.logger.info(
                "Connector %s detected %d changes (incremental=%s)",
                self.config.connector_id,
                len(changes),
                incremental,
            )

            await self._write_job_state(
                job_id=job_id,
                status="running",
                started_at=started_at,
                sources_total=result.sources_total,
                sources_done=0,
                sources_failed=0,
            )

            concurrency = self.max_concurrency
            pending = [c for c in changes if c.source_id not in already_processed]
            if concurrency <= 1:
                for change in pending:
                    errors_before = len(result.errors)
                    await self._process_change(change, result)
                    if len(result.errors) == errors_before:
                        await self._write_checkpoint(change.source_id)
                    await self._write_job_state(
                        job_id=job_id,
                        status="running",
                        started_at=started_at,
                        sources_total=result.sources_total,
                        sources_done=result.sources_done,
                        sources_failed=result.sources_failed,
                    )
            else:
                sem = asyncio.Semaphore(concurrency)

                async def bounded(change: ChangeInfo) -> None:
                    async with sem:
                        errors_before = len(result.errors)
                        await self._process_change(change, result)
                        if len(result.errors) == errors_before:
                            await self._write_checkpoint(change.source_id)
                        await self._write_job_state(
                            job_id=job_id,
                            status="running",
                            started_at=started_at,
                            sources_total=result.sources_total,
                            sources_done=result.sources_done,
                            sources_failed=result.sources_failed,
                        )

                await asyncio.gather(*[bounded(c) for c in pending], return_exceptions=True)

            result.status = "success" if not result.errors else "partial"
            if result.status == "success":
                await self._clear_checkpoint()
        except Exception as exc:
            self.logger.error("Sync failed for connector %s: %s", self.config.connector_id, exc)
            result.errors.append(str(exc))
            result.status = "failed"
        finally:
            result.completed_at = datetime_now()
            await self._write_job_state(
                job_id=job_id,
                status=result.status,
                started_at=started_at,
                sources_total=result.sources_total,
                sources_done=result.sources_done,
                sources_failed=result.sources_failed,
            )

        return result

    async def _process_change(self, change: ChangeInfo, result: SyncResult) -> None:
        """Process a single ChangeInfo entry during sync (Issue #1254: extracted)."""
        try:
            if change.change_type == "deleted":
                result.deleted += 1
                result.sources_done += 1
                return

            content = await self.fetch_content(change.source_id)
            if content is None:
                self.logger.warning("fetch_content returned None for %s", change.source_id)
                result.errors.append("No content for source_id=%s" % change.source_id)
                result.sources_failed += 1
                result.sources_done += 1
                return

            self._validate_metadata(content, result)
            await self._ingest_content(content)

            if change.change_type == "added":
                result.added += 1
            else:
                result.updated += 1
            result.sources_done += 1

        except Exception as exc:
            self.logger.error("Error processing source %s: %s", change.source_id, exc)
            result.errors.append("source_id=%s: %s" % (change.source_id, exc))
            result.sources_failed += 1
            result.sources_done += 1

    def _validate_metadata(self, content: ContentResult, result: SyncResult) -> None:
        """Validate content.metadata against output_schema() if one is declared.

        Issue #8147: Soft validation — logs a warning and appends to
        result.errors but does NOT abort ingestion.
        """
        schema = self.output_schema()
        if not schema:
            return

        required = schema.get("required", [])
        props = schema.get("properties", {})

        missing = [k for k in required if k not in content.metadata]
        if missing:
            msg = "source_id=%s: metadata missing required fields %s" % (content.source_id, missing)
            self.logger.warning("Output schema violation: %s", msg)
            result.errors.append(msg)

        for key, prop_schema in props.items():
            if key not in content.metadata:
                continue
            expected_type = prop_schema.get("type")
            if expected_type is None:
                continue
            _TYPE_MAP: Dict[str, type] = {
                "string": str,
                "integer": int,
                "number": (int, float),
                "boolean": bool,
                "array": list,
                "object": dict,
            }
            py_type = _TYPE_MAP.get(expected_type)
            if py_type and not isinstance(content.metadata[key], py_type):
                msg = "source_id=%s: metadata field '%s' expected %s, got %s" % (
                    content.source_id,
                    key,
                    expected_type,
                    type(content.metadata[key]).__name__,
                )
                self.logger.warning("Output schema type mismatch: %s", msg)
                result.errors.append(msg)

    async def _ingest_content(self, content: ContentResult) -> None:
        """Store fetched content in the knowledge base (Issue #1254: extracted).

        Uses the global KB singleton so the connector does not need a direct
        reference to the KnowledgeBase instance at construction time.
        """
        from knowledge import get_knowledge_base

        kb = await get_knowledge_base()

        ingest_metadata = dict(content.metadata)
        ingest_metadata.update(
            {
                "source_type": "connector",
                "source_connector_id": self.config.connector_id,
                "connector_type": self.connector_type,
                "source_id": content.source_id,
                "content_type": content.content_type,
                "verification_status": self.config.verification_mode,
            }
        )

        text = content.content
        if not text.strip():
            self.logger.debug("Skipping empty content for source %s", content.source_id)
            return

        await kb.store_fact(text, ingest_metadata, fact_id=content.source_id)
        self.logger.debug(
            "Ingested source %s into KB (connector=%s)",
            content.source_id,
            self.config.connector_id,
        )

    # ------------------------------------------------------------------
    # Job state helpers (Issue #8149)
    # ------------------------------------------------------------------

    def _job_redis_key(self) -> str:
        return "connector:%s%s" % (self.config.connector_id, _JOB_KEY_SUFFIX)

    async def _write_job_state(
        self,
        job_id: str,
        status: str,
        started_at: datetime,
        sources_total: int,
        sources_done: int,
        sources_failed: int,
    ) -> None:
        """Write current job state to Redis with a 24h TTL."""
        import os

        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client(database="knowledge")
        if redis is None:
            return
        try:
            state = json.dumps(
                {
                    "job_id": job_id,
                    "started_at": started_at.isoformat(),
                    "status": status,
                    "sources_total": sources_total,
                    "sources_done": sources_done,
                    "sources_failed": sources_failed,
                    "worker_id": "%s-%d" % (os.uname().nodename, os.getpid()),
                    "last_updated": datetime_now().isoformat(),
                },
                ensure_ascii=False,
            )
            await redis.set(self._job_redis_key(), state, ex=_JOB_TTL_S)
        except Exception as exc:
            self.logger.debug("Job state write failed (non-critical): %s", exc)
