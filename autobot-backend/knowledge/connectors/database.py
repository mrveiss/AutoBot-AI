# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Database Connector

Issue #1254: Ingests rows from a relational database using SQLAlchemy async.
Supports any database engine with a SQLAlchemy-compatible connection string.
"""

import hashlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from knowledge.connectors.base import AbstractConnector
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SourceInfo,
)
from knowledge.connectors.registry import ConnectorRegistry

logger = logging.getLogger(__name__)


def _row_to_source_id(connector_id: str, id_value: Any) -> str:
    """Derive a stable source_id from the connector ID and row primary key."""
    raw = "%s:%s" % (connector_id, id_value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@ConnectorRegistry.register("database")
class DatabaseConnector(AbstractConnector):
    """Connector that fetches rows from a relational database.

    Config keys (all under ``config.config``):
        connection_string (str): SQLAlchemy async-compatible connection string,
            e.g. ``postgresql+asyncpg://user:pass@host/db``.
        query (str): SQL to execute.  Use ``:since`` for incremental syncs, e.g.
            ``SELECT id, title, body FROM articles WHERE updated_at > :since``.
        id_column (str): Column used as the row identifier. Default "id".
        content_columns (list[str]): Columns to concatenate as document content.
        timestamp_column (str): Column used for change detection. Optional.
    """

    connector_type = "database"

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._connection_string: str = cfg.get("connection_string", "")
        self._query: str = cfg.get("query", "")
        self._id_column: str = cfg.get("id_column", "id")
        self._content_columns: List[str] = cfg.get("content_columns", [])
        self._timestamp_column: Optional[str] = cfg.get("timestamp_column")

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Try to connect and execute SELECT 1."""
        try:
            async with self._get_engine() as engine:
                from sqlalchemy import text

                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            self.logger.info("Database connection test passed")
            return True
        except Exception as exc:
            self.logger.error("Database connection test failed: %s", exc)
            return False

    async def discover_sources(self) -> List[SourceInfo]:
        """Execute the configured query (no :since filter) and list rows."""
        try:
            rows = await self._execute_query(since=None)
            return [self._row_to_source_info(row) for row in rows]
        except Exception as exc:
            self.logger.error("discover_sources failed: %s", exc)
            return []

    async def fetch_content(self, source_id: str) -> Optional[ContentResult]:
        """Fetch row matching *source_id* and assemble content."""
        try:
            rows = await self._execute_query(since=None)
            for row in rows:
                row_dict = _row_to_dict(row)
                row_source_id = _row_to_source_id(
                    self.config.connector_id, row_dict.get(self._id_column)
                )
                if row_source_id == source_id:
                    return self._build_content_result(source_id, row_dict)
            self.logger.warning("No row found for source_id: %s", source_id)
            return None
        except Exception as exc:
            self.logger.error("fetch_content failed for %s: %s", source_id, exc)
            return None

    async def detect_changes(
        self, since: Optional[datetime] = None
    ) -> List[ChangeInfo]:
        """Return rows newer than *since* based on timestamp_column."""
        try:
            rows = await self._execute_query(since=since)
            changes: List[ChangeInfo] = []

            for row in rows:
                row_dict = _row_to_dict(row)
                id_val = row_dict.get(self._id_column)
                source_id = _row_to_source_id(self.config.connector_id, id_val)
                ts = _extract_timestamp(row_dict, self._timestamp_column)
                change_type = "added" if since is None else "modified"

                changes.append(
                    ChangeInfo(
                        source_id=source_id,
                        change_type=change_type,
                        timestamp=ts or datetime.utcnow(),
                        details={"id_column": self._id_column, "id_value": id_val},
                    )
                )

            self.logger.info("detect_changes: %d rows returned", len(changes))
            return changes
        except Exception as exc:
            self.logger.error("detect_changes failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def _get_engine(self):
        """Yield a transient async SQLAlchemy engine (Issue #1254: extracted)."""
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(self._connection_string, echo=False)
        try:
            yield engine
        finally:
            await engine.dispose()

    async def _execute_query(self, since: Optional[datetime]) -> List[Any]:
        """Run the configured query, optionally binding :since (Issue #1254)."""
        from sqlalchemy import text

        params: Dict[str, Any] = {}
        query_str = self._query

        if since is not None and ":since" in query_str and self._timestamp_column:
            params["since"] = since
        elif ":since" in query_str:
            # Remove :since clause when no timestamp context is available
            query_str = _strip_since_clause(query_str)

        async with self._get_engine() as engine:
            async with engine.connect() as conn:
                result = await conn.execute(text(query_str), params)
                return result.fetchall()

    def _row_to_source_info(self, row: Any) -> SourceInfo:
        """Convert a database row to a SourceInfo (Issue #1254: extracted)."""
        row_dict = _row_to_dict(row)
        id_val = row_dict.get(self._id_column)
        source_id = _row_to_source_id(self.config.connector_id, id_val)
        ts = _extract_timestamp(row_dict, self._timestamp_column) or datetime.utcnow()

        return SourceInfo(
            source_id=source_id,
            name=str(id_val),
            path="%s=%s" % (self._id_column, id_val),
            content_type="text/plain",
            size_bytes=0,
            last_modified=ts,
            metadata={
                "id_column": self._id_column,
                "id_value": id_val,
                "connector_id": self.config.connector_id,
            },
        )

    def _build_content_result(
        self, source_id: str, row_dict: Dict[str, Any]
    ) -> ContentResult:
        """Concatenate content_columns into a ContentResult (Issue #1254)."""
        parts = []
        for col in self._content_columns:
            val = row_dict.get(col)
            if val is not None:
                parts.append("%s: %s" % (col, val))

        content = "\n\n".join(parts) if parts else str(row_dict)

        return ContentResult(
            source_id=source_id,
            content=content,
            content_type="text/plain",
            metadata={
                "connector_id": self.config.connector_id,
                "id_value": row_dict.get(self._id_column),
                "id_column": self._id_column,
            },
        )


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Convert a SQLAlchemy Row to a plain dict (Issue #1254: helper)."""
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row)


def _extract_timestamp(
    row_dict: Dict[str, Any], timestamp_column: Optional[str]
) -> Optional[datetime]:
    """Extract a datetime from row_dict using timestamp_column (Issue #1254)."""
    if not timestamp_column:
        return None
    val = row_dict.get(timestamp_column)
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            pass
    return None


def _strip_since_clause(query: str) -> str:
    """Remove a trailing WHERE/AND clause containing ':since' (Issue #1254).

    Conservative approach: if the clause cannot be located cleanly the query
    is returned unmodified so SQLAlchemy raises a descriptive bind error.
    """
    lower = query.lower()
    idx = lower.rfind(":since")
    if idx == -1:
        return query

    before = query[:idx]
    and_pos = before.lower().rfind(" and ")
    where_pos = before.lower().rfind(" where ")
    trim_pos = max(and_pos, where_pos)

    if trim_pos == -1:
        return query

    return query[:trim_pos].rstrip()
