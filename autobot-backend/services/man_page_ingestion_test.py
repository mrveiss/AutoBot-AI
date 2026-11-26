# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one man-page ingestion path keys every fact per host (#22272)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from services import man_page_ingestion as ingest


def _ctx(machine_id: str) -> dict:
    return {
        "machine_id": machine_id,
        "machine_ip": "10.0.0.1",
        "os_name": "ubuntu",
        "os_version": "24.04",
        "os_type": "Linux",
        "architecture": "x86_64",
        "kernel_version": "6.8",
    }


def _index(machine_id: str) -> list:
    kb = MagicMock(store_fact=AsyncMock(return_value={"status": "success"}))
    with (
        patch.object(ingest, "_get_man_content", AsyncMock(return_value="NAME ls")),
        patch.object(ingest, "_get_man_page_description", AsyncMock(return_value="list")),
    ):
        asyncio.run(ingest.index_command_batch(kb, [("ls", "1")], _ctx(machine_id)))
    return [call.kwargs["metadata"] for call in kb.store_fact.await_args_list]


def test_the_same_command_on_two_hosts_is_two_facts():
    (first,), (second,) = _index("redis"), _index("ai-stack")
    assert first["unique_key"] == "redis:ubuntu:ls:1"
    assert second["unique_key"] == "ai-stack:ubuntu:ls:1"
    assert first["applies_to_machines"] == ["redis"]


def test_a_rerun_on_one_host_reuses_its_key():
    assert _index("redis")[0]["unique_key"] == _index("redis")[0]["unique_key"]


def test_the_metadata_marks_an_ingested_per_host_document():
    from knowledge.ingestion_visibility import ingested_document_class

    (metadata,) = _index("redis")
    assert metadata["visibility"] == "system"
    assert ingested_document_class(metadata) == "man_page"


def test_the_populate_endpoint_uses_this_path():
    """The curated-list writer calls index_commands_in_batches; it keeps no writer of its own."""
    from api import knowledge_population as pop

    kb = object()
    with (
        patch.object(pop, "index_commands_in_batches", AsyncMock(return_value=3)) as batches,
        patch("utils.system_context.get_system_context", return_value=_ctx("redis")),
    ):
        assert asyncio.run(pop._populate_man_pages_background(kb)) == 3
    commands = batches.await_args.args[1]
    assert ("ls", ingest.MAN_PAGE_DEFAULT_SECTION) in commands
    assert not hasattr(pop, "_store_man_page")
