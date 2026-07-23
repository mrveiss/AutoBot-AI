# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Mock/Replay Knowledge Connector (Issue #10538)

Offline, credential-free connector that serves documents from local JSON
fixtures instead of a live third-party API. It implements the exact same
``AbstractConnector`` interface (``test_connection``/``discover_sources``/
``fetch_content``/``detect_changes``) that Slack/Confluence/Jira use and does
NOT override ``sync()``, so a call to ``sync()`` exercises the real inherited
pipeline end-to-end (change detection -> fetch -> output-schema validation ->
KB ingest -> Redis checkpoint/job-state) with zero network access. This
de-risks the eventual credential wiring for the enterprise connectors by
making the shared framework testable offline.

Config keys (under ``ConnectorConfig.config``):
    fixtures_dir (str): Directory of ``*.json`` fixture documents. Defaults
        to the bundled ``fixtures/mock`` directory next to this module.
        Each fixture is a JSON object with keys: id, title, category,
        author, updated_at (ISO-8601), content.

Gating: registered only when the ``kb_mock_connector`` feature flag is
enabled (default disabled — see ``knowledge/connectors/__init__.py`` and
``autobot_shared/feature_flags.py``). Unlike Slack/Confluence/Jira, which are
gated because they reach real third-party SaaS APIs, this connector never
makes a network call — it is gated purely so a "mock" entry never appears in
the production ``GET /knowledge_base/connector_types`` listing by default.
Tests import this module directly, bypassing the package-level gate.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from knowledge.connectors.base import AbstractConnector
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SourceInfo,
)
from knowledge.connectors.registry import ConnectorRegistry

logger = get_logger(__name__)

_DEFAULT_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "mock"


@ConnectorRegistry.register("mock")
class MockConnector(AbstractConnector):
    """Replays local JSON fixtures through the real connector pipeline.

    Each fixture file becomes one KB fact keyed by
    ``mock:{connector_id}:doc:{doc_id}``. No network access is made at any
    point; ``discover_sources``/``fetch_content``/``detect_changes`` all read
    from disk (or an in-memory override supplied via ``docs`` at construction
    for unit tests that don't want real files).
    """

    connector_type = "mock"
    # Issue #4421: zero-config — reads local fixtures, no credentials needed.
    tier = 0

    @classmethod
    def output_schema(cls) -> Dict[str, Any]:
        """Return JSONSchema for ContentResult.metadata (Issue #8147)."""
        return {
            "type": "object",
            "required": ["category", "title"],
            "properties": {
                "category": {"type": "string", "description": "Document category"},
                "title": {"type": "string", "description": "Document title"},
                "author": {"type": "string", "description": "Document author"},
                "doc_id": {"type": "string", "description": "Fixture document ID"},
            },
        }

    def __init__(self, config: ConnectorConfig, docs: Optional[List[Dict[str, Any]]] = None) -> None:
        super().__init__(config)
        cfg = config.config
        self._fixtures_dir = Path(cfg.get("fixtures_dir", str(_DEFAULT_FIXTURES_DIR)))
        self._docs_override = docs

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Always reachable offline: True when fixtures are loadable."""
        return bool(self._load_docs())

    async def discover_sources(self) -> List[SourceInfo]:
        """Return a SourceInfo for every fixture document."""
        return [_doc_to_source_info(self.config.connector_id, doc) for doc in self._load_docs()]

    async def fetch_content(self, source_id: str) -> Optional[ContentResult]:
        """Return the fixture document content for *source_id*."""
        doc = self._find_doc(source_id)
        if doc is None:
            self.logger.warning("Mock source_id not found: %s", source_id)
            return None
        return _doc_to_content_result(source_id, doc)

    async def detect_changes(self, since: Optional[datetime] = None) -> List[ChangeInfo]:
        """Return ChangeInfo for every fixture updated after *since*."""
        changes: List[ChangeInfo] = []
        for doc in self._load_docs():
            updated_at = _parse_updated_at(doc)
            if since is not None and updated_at <= since:
                continue
            change_type = "added" if since is None else "modified"
            changes.append(
                ChangeInfo(
                    source_id=_build_source_id(self.config.connector_id, doc["id"]),
                    change_type=change_type,
                    timestamp=updated_at,
                    details={"category": doc.get("category", ""), "doc_id": doc["id"]},
                )
            )
        return changes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_docs(self) -> List[Dict[str, Any]]:
        """Load all fixture documents (or the in-memory override) — no network."""
        if self._docs_override is not None:
            return self._docs_override
        return _load_fixtures_from_dir(self._fixtures_dir, self.logger)

    def _find_doc(self, source_id: str) -> Optional[Dict[str, Any]]:
        doc_id = _parse_source_id(source_id)
        if doc_id is None:
            return None
        return next((d for d in self._load_docs() if d.get("id") == doc_id), None)


# ---------------------------------------------------------------------------
# Module-level helpers (no state, no network)
# ---------------------------------------------------------------------------


def _load_fixtures_from_dir(fixtures_dir: Path, log) -> List[Dict[str, Any]]:
    """Read and parse every ``*.json`` fixture in *fixtures_dir*, sorted by name."""
    docs: List[Dict[str, Any]] = []
    if not fixtures_dir.is_dir():
        log.warning("Mock fixtures_dir missing: %s", fixtures_dir)
        return docs
    for path in sorted(fixtures_dir.glob("*.json")):
        try:
            docs.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Failed to load fixture %s: %s", path, exc)
    return docs


def _build_source_id(connector_id: str, doc_id: str) -> str:
    return "mock:%s:doc:%s" % (connector_id, doc_id)


def _parse_source_id(source_id: str) -> Optional[str]:
    parts = source_id.split(":")
    # Format: mock:{connector_id}:doc:{doc_id}
    if len(parts) != 4 or parts[0] != "mock" or parts[2] != "doc":
        return None
    return parts[3]


def _parse_updated_at(doc: Dict[str, Any]) -> datetime:
    raw = doc.get("updated_at")
    if not raw:
        return now_utc()
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return now_utc()


def _doc_to_source_info(connector_id: str, doc: Dict[str, Any]) -> SourceInfo:
    content = doc.get("content", "")
    return SourceInfo(
        source_id=_build_source_id(connector_id, doc["id"]),
        name=doc.get("title", doc["id"]),
        path=doc["id"],
        content_type="text/plain",
        size_bytes=len(content.encode("utf-8")),
        last_modified=_parse_updated_at(doc),
        metadata={"category": doc.get("category", ""), "author": doc.get("author", "")},
    )


def _doc_to_content_result(source_id: str, doc: Dict[str, Any]) -> ContentResult:
    return ContentResult(
        source_id=source_id,
        content=doc.get("content", ""),
        content_type="text/plain",
        metadata={
            "category": doc.get("category", ""),
            "title": doc.get("title", ""),
            "author": doc.get("author", ""),
            "doc_id": doc["id"],
        },
    )


__all__ = ["MockConnector"]
