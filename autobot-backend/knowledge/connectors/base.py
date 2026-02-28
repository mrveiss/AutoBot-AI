# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Abstract Connector Base Class

Issue #1254: Defines the interface every source connector must implement.
Concrete connectors subclass AbstractConnector and register via
@ConnectorRegistry.register("<type>").
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ConnectorStatus,
    ContentResult,
    SourceInfo,
    SyncResult,
)


class AbstractConnector(ABC):
    """Base class for all knowledge source connectors.

    Subclasses must set the class attribute ``connector_type`` and implement
    the four abstract methods.  The default ``sync()`` method orchestrates
    change detection → fetch → ingest and can be overridden when a connector
    needs a custom sync strategy.
    """

    connector_type: str = ""

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
        self.logger = logging.getLogger(
            "%s.%s" % (__name__, self.connector_type or type(self).__name__)
        )

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
    async def fetch_content(self, source_id: str) -> Optional[ContentResult]:
        """Fetch and return the content for a single source by ID."""

    @abstractmethod
    async def detect_changes(
        self, since: Optional[datetime] = None
    ) -> List[ChangeInfo]:
        """Return sources that changed since *since* (or all if since is None)."""

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
        abort the rest of the sync.

        Args:
            incremental: When True, only process sources that changed since
                         ``config.last_sync_at``.  When False, re-process all.

        Returns:
            SyncResult with counts and any per-source errors.
        """
        from datetime import datetime as _dt

        started_at = _dt.utcnow()
        result = SyncResult(
            connector_id=self.config.connector_id,
            started_at=started_at,
            completed_at=None,
            status="failed",
        )

        since = self.config.last_sync_at if incremental else None

        try:
            changes = await self.detect_changes(since=since)
            self.logger.info(
                "Connector %s detected %d changes (incremental=%s)",
                self.config.connector_id,
                len(changes),
                incremental,
            )

            for change in changes:
                await self._process_change(change, result)

            result.status = "success" if not result.errors else "partial"
        except Exception as exc:
            self.logger.error(
                "Sync failed for connector %s: %s", self.config.connector_id, exc
            )
            result.errors.append(str(exc))
            result.status = "failed"
        finally:
            result.completed_at = _dt.utcnow()

        return result

    async def _process_change(self, change: ChangeInfo, result: SyncResult) -> None:
        """Process a single ChangeInfo entry during sync (Issue #1254: extracted)."""
        try:
            if change.change_type == "deleted":
                result.deleted += 1
                return

            content = await self.fetch_content(change.source_id)
            if content is None:
                self.logger.warning(
                    "fetch_content returned None for %s", change.source_id
                )
                result.errors.append("No content for source_id=%s" % change.source_id)
                return

            await self._ingest_content(content)

            if change.change_type == "added":
                result.added += 1
            else:
                result.updated += 1

        except Exception as exc:
            self.logger.error("Error processing source %s: %s", change.source_id, exc)
            result.errors.append("source_id=%s: %s" % (change.source_id, exc))

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
