# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Each trusted ingestion site writes SYSTEM visibility on what nobody owns (#16693).

Owner decision on #16693: connectors, admin file uploads, man-page imports, the
documentation KB and the system-command reference are documents for every signed-in user.
Each site stamps the visibility itself: a generic chokepoint can't, because a caller-supplied
metadata dict could carry the same markers. Every test also checks that the backfill's
predicate recognises what the site writes, so the two definitions can't drift apart.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.ingestion_visibility import ingested_document_class


def _is_system_document(metadata: dict, kind: str) -> bool:
    return metadata["visibility"] == "system" and ingested_document_class(metadata) == kind


def test_population_builders_write_system():
    from api import knowledge_population as pop

    assert _is_system_document(pop._get_command_metadata({"command": "ls"}), "system_commands")
    assert _is_system_document(pop._get_man_page_metadata("ls"), "man_page")
    assert _is_system_document(pop._get_doc_metadata("guide.md", "docs/guide.md", "guides"), "documentation")


@pytest.mark.asyncio
async def test_the_system_configuration_document_is_written_system():
    from api import knowledge_population as pop

    kb = MagicMock()
    kb.store_fact = AsyncMock(return_value={"fact_id": "f1"})
    with patch.object(pop, "_build_system_config_info", return_value="config"):
        assert await pop._store_system_config(kb)
    assert _is_system_document(kb.store_fact.await_args.kwargs["metadata"], "documentation")


def test_the_repo_sync_writes_system_on_its_documentation_only():
    """Owner decision on #16693: the sync's reports, security docs and source code stay private."""
    from knowledge_sync_incremental import IncrementalKnowledgeSync as Sync

    sync = Sync.__new__(Sync)
    sync.current_sync_time = "2026-09-14T00:00:00+00:00"

    def base(rel: str) -> dict:
        return Sync._create_chunk_base_metadata(sync, Path("/repo") / rel, Path(rel), "text")

    assert _is_system_document(base("docs/user_guide/intro.md"), "documentation")
    assert _is_system_document(base("README.md"), "documentation")
    for private in ("reports/audit.md", "docs/security/tls.md", "src/app.py"):
        assert "visibility" not in base(private), private


def test_machine_synced_and_parsed_man_pages_are_written_system():
    from api.knowledge_maintenance import _build_document_metadata
    from services.man_page_parser import ManPageContent

    synced = _build_document_metadata({"command": "ls", "file_path": "/usr/share/man/ls.1"}, "m1", 10)
    assert _is_system_document(synced, "man_page")
    assert _is_system_document(ManPageContent(command="ls", section="1").get_metadata_for_storage(), "man_page")


async def _ingest(source_metadata: dict) -> dict:
    """Run a connector's ingestion of one item; returns the metadata it stored."""
    from knowledge.connectors.base import AbstractConnector
    from knowledge.connectors.models import ContentResult

    connector = SimpleNamespace(
        config=SimpleNamespace(connector_id="c1", verification_mode="unverified"),
        connector_type="gdrive",
        logger=MagicMock(),
    )
    kb = MagicMock()
    kb.store_fact = AsyncMock(return_value={"status": "success"})
    item = ContentResult(source_id="s1", content="text", content_type="text/plain", metadata=source_metadata)
    with patch("knowledge.get_knowledge_base", AsyncMock(return_value=kb)):
        await AbstractConnector._ingest_content(connector, item)
    return kb.store_fact.await_args.args[1]


@pytest.mark.asyncio
async def test_unclaimed_connector_content_is_written_system():
    assert _is_system_document(await _ingest({"title": "doc"}), "connector")


@pytest.mark.asyncio
async def test_connector_content_its_source_already_claims_keeps_that_claim():
    stored = await _ingest({"title": "doc", "owner_id": "u1"})
    assert "visibility" not in stored


@pytest.mark.asyncio
async def test_an_admin_file_upload_is_written_system():
    from api import knowledge as mod

    upload = SimpleNamespace(filename="guide.txt", read=AsyncMock(return_value=b"hello world"))
    req = MagicMock()
    req.form = AsyncMock(return_value={"file": upload, "title": "Guide"})
    kb = MagicMock()
    kb.store_fact = AsyncMock(return_value={"fact_id": "f1"})
    with (
        patch.object(mod, "get_or_create_knowledge_base", AsyncMock(return_value=kb)),
        patch.object(mod, "_extract_file_content", return_value=("hello world", None)),
        patch.object(mod, "_has_usable_content", return_value=True),
        patch.object(mod, "_page_provenance_metadata", return_value={}),
        patch.object(mod, "get_auth_middleware", MagicMock()),
        patch.object(mod, "audit_record", MagicMock()),
    ):
        await mod.upload_file_to_knowledge(admin_check=True, req=req)
    assert _is_system_document(kb.store_fact.await_args.kwargs["metadata"], "file_upload")


@pytest.mark.asyncio
async def test_only_an_upload_is_stamped_by_the_shared_store_helper():
    """The add-fact and URL routes share the helper; their ownerless facts stay private."""
    from api import knowledge as mod

    kb = MagicMock()
    kb.store_fact = AsyncMock(return_value={"fact_id": "f1"})
    for metadata in ({"source": "autobot_docs_population"}, {"type": "url", "source": "https://example.invalid"}):
        await mod._store_fact_in_kb(kb, "text", dict(metadata))
        assert "visibility" not in kb.store_fact.await_args.kwargs["metadata"]
