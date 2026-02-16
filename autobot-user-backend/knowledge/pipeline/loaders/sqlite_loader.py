# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SQLite Loader - Load facts, metadata, and pipeline stats to SQLite.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

from backend.knowledge.pipeline.base import BaseLoader, PipelineContext
from backend.knowledge.pipeline.registry import TaskRegistry

logger = logging.getLogger(__name__)


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_facts (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    entities_count INTEGER DEFAULT 0,
    relationships_count INTEGER DEFAULT 0,
    events_count INTEGER DEFAULT 0,
    summaries_count INTEGER DEFAULT 0,
    chunks_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'completed',
    error_message TEXT,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_facts_document
ON knowledge_facts(document_id);

CREATE INDEX IF NOT EXISTS idx_facts_type
ON knowledge_facts(fact_type);

CREATE INDEX IF NOT EXISTS idx_runs_document
ON pipeline_runs(document_id);
"""


@TaskRegistry.register_loader("sqlite")
class SQLiteLoader(BaseLoader):
    """Load facts, metadata, and pipeline run stats to SQLite."""

    def __init__(
        self, db_path: str = "data/knowledge/pipeline.db", run_id: Optional[str] = None
    ) -> None:
        """
        Initialize SQLite loader.

        Args:
            db_path: Path to SQLite database file
            run_id: Unique pipeline run ID (generated if not provided)
        """
        self.db_path = db_path
        self.run_id = run_id
        self.db: Optional[aiosqlite.Connection] = None

    async def load(self, context: PipelineContext) -> None:
        """
        Load pipeline data to SQLite.

        Args:
            context: Pipeline context with processed data
        """
        # Ensure database directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            self.db = db
            await self._create_tables()
            await self._save_facts(context)
            await self._save_pipeline_run(context)
            await db.commit()

        logger.info("Loaded pipeline data to SQLite: %s", self.db_path)

    async def _create_tables(self) -> None:
        """Create tables if they don't exist."""
        try:
            await self.db.executescript(CREATE_TABLES_SQL)
        except Exception as e:
            logger.error("Failed to create tables: %s", e)

    async def _save_facts(self, context: PipelineContext) -> None:
        """Save extracted facts to knowledge_facts table."""
        try:
            facts = []
            facts.extend(self._build_entity_facts(context))
            facts.extend(self._build_relationship_facts(context))
            facts.extend(self._build_event_facts(context))

            if facts:
                await self.db.executemany(
                    """INSERT OR REPLACE INTO knowledge_facts
                    (id, document_id, fact_type, content, confidence, metadata)
                    VALUES (:id, :document_id, :fact_type, :content,
                    :confidence, :metadata)""",
                    facts,
                )

            logger.info("Saved %s facts to SQLite", len(facts))
        except Exception as e:
            logger.error("Failed to save facts: %s", e)

    def _build_entity_facts(self, context: PipelineContext) -> List[Dict[str, Any]]:
        """Build fact dicts from entities.

        Helper for _save_facts (Issue #759).
        """
        facts = []
        for entity in context.entities:
            facts.append(
                {
                    "id": str(entity.id),
                    "document_id": str(entity.source_document_id),
                    "fact_type": "entity",
                    "content": entity.name,
                    "confidence": entity.confidence,
                    "metadata": json.dumps(
                        {
                            "entity_type": entity.entity_type,
                            "description": entity.description,
                            "properties": entity.properties,
                        }
                    ),
                }
            )
        return facts

    def _build_relationship_facts(
        self, context: PipelineContext
    ) -> List[Dict[str, Any]]:
        """Build fact dicts from relationships.

        Helper for _save_facts (Issue #759).
        """
        facts = []
        for rel in context.relationships:
            facts.append(
                {
                    "id": str(rel.id),
                    "document_id": str(context.document_id or ""),
                    "fact_type": "relationship",
                    "content": rel.relationship_type,
                    "confidence": rel.confidence,
                    "metadata": json.dumps(
                        {
                            "source_id": str(rel.source_entity_id),
                            "target_id": str(rel.target_entity_id),
                            "description": rel.description,
                            "bidirectional": rel.bidirectional,
                        }
                    ),
                }
            )
        return facts

    def _build_event_facts(self, context: PipelineContext) -> List[Dict[str, Any]]:
        """Build fact dicts from events.

        Helper for _save_facts (Issue #759).
        """
        facts = []
        for event in context.events:
            facts.append(
                {
                    "id": str(event.id),
                    "document_id": str(event.source_document_id),
                    "fact_type": "event",
                    "content": event.name,
                    "confidence": event.confidence,
                    "metadata": json.dumps(
                        {
                            "event_type": event.event_type,
                            "temporal_type": event.temporal_type,
                            "description": event.description,
                            "temporal_expression": event.temporal_expression,
                        }
                    ),
                }
            )
        return facts

    async def _save_pipeline_run(self, context: PipelineContext) -> None:
        """Save pipeline run statistics."""
        try:
            from uuid import uuid4

            run_id = self.run_id or str(uuid4())

            await self.db.execute(
                """INSERT INTO pipeline_runs
                (id, document_id, run_timestamp, entities_count,
                relationships_count, events_count, summaries_count,
                chunks_count, status, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    str(context.document_id or ""),
                    datetime.utcnow().isoformat(),
                    len(context.entities),
                    len(context.relationships),
                    len(context.events),
                    len(context.summaries),
                    len(context.chunks),
                    "completed",
                    json.dumps(context.metadata),
                ),
            )

            logger.info("Saved pipeline run %s to SQLite", run_id)
        except Exception as e:
            logger.error("Failed to save pipeline run: %s", e)
