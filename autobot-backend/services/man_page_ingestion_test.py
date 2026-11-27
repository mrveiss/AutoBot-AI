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
        patch.object(pop, "index_commands_in_batches", AsyncMock(return_value=ingest.BatchOutcome(3, 0))) as batches,
        patch("utils.system_context.get_system_context", return_value=_ctx("redis")),
    ):
        assert asyncio.run(pop._populate_man_pages_background(kb)) == 3
    commands = batches.await_args.args[1]
    assert ("ls", None) in commands  # man resolves the section, none is forced
    assert not hasattr(pop, "_store_man_page")


def test_index_all_man_pages_returns_counts_without_a_subprocess():
    """#22272: the Celery refresh reads this return value; nothing parses a script's stdout."""
    kb = MagicMock(initialized=True)
    kb.get_stats = AsyncMock(return_value={"total_facts": 7, "total_vectors": 5})
    kb._get_keyword_searcher.return_value.flush_refresh = AsyncMock()
    with (
        patch("knowledge_factory.get_knowledge_base_async", AsyncMock(return_value=kb)),
        patch.object(ingest, "get_all_available_commands", AsyncMock(return_value=["ls", "cat"])),
        patch.object(ingest, "get_system_context", return_value=_ctx("host-a")),
        patch.object(ingest, "index_commands_in_batches", AsyncMock(return_value=ingest.BatchOutcome(2, 1))),
    ):
        result = asyncio.run(ingest.index_all_man_pages())
    assert result == {
        "commands_scanned": 2,
        "commands_indexed": 2,
        "storage_failed": 1,
        "total_facts": 7,
        "total_vectors": 5,
    }
    kb._get_keyword_searcher.return_value.flush_refresh.assert_awaited_once()


def test_index_all_man_pages_without_a_knowledge_base_raises():
    import pytest

    with patch("knowledge_factory.get_knowledge_base_async", AsyncMock(return_value=None)):
        with pytest.raises(ingest.ManPageIndexingError):
            asyncio.run(ingest.index_all_man_pages())


def _stub_process(stdout: bytes = b"", returncode: int = 0) -> MagicMock:
    process = MagicMock(returncode=returncode)
    process.communicate = AsyncMock(return_value=(stdout, b""))
    process.wait = AsyncMock()
    return process


def test_a_command_with_no_section_one_page_is_indexed_under_the_resolved_section():
    """service(8) has no section-1 page: the stored key, section and title carry 8 (#22280)."""
    kb = MagicMock(store_fact=AsyncMock(return_value={"status": "success"}))
    process = _stub_process(b"/usr/share/man/man8/service.8.gz\n")
    with (
        patch.object(ingest.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)),
        patch.object(ingest, "_get_man_content", AsyncMock(return_value="NAME service")) as content,
        patch.object(ingest, "_get_man_page_description", AsyncMock(return_value="run")),
    ):
        outcome = asyncio.run(ingest.index_command_batch(kb, [("service", None)], _ctx("redis")))
    content.assert_awaited_once_with("service", "8")
    metadata = kb.store_fact.await_args.kwargs["metadata"]
    assert (metadata["section"], metadata["title"]) == ("8", "man service(8)")
    assert outcome.indexed == 1


def test_a_command_man_cannot_resolve_is_skipped_not_failed():
    kb = MagicMock(store_fact=AsyncMock())
    process = _stub_process(returncode=1)
    with patch.object(ingest.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)):
        outcome = asyncio.run(ingest.index_command_batch(kb, [("nosuch", None)], _ctx("redis")))
    assert outcome == ingest.BatchOutcome(0, 0)
    kb.store_fact.assert_not_awaited()


def test_storage_failure_for_every_page_is_a_failed_run():
    import pytest

    kb = MagicMock(store_fact=AsyncMock(side_effect=RuntimeError("down")))
    with (
        patch.object(ingest, "_get_man_content", AsyncMock(return_value="NAME ls")),
        patch.object(ingest, "_get_man_page_description", AsyncMock(return_value="list")),
    ):
        with pytest.raises(ingest.ManPageIndexingError):
            asyncio.run(ingest.index_commands_in_batches(kb, [("ls", "1"), ("cat", "1")], _ctx("redis")))


def test_partial_storage_failure_keeps_the_successful_writes():
    kb = MagicMock(store_fact=AsyncMock(side_effect=[{"status": "success"}, {"status": "error"}]))
    with (
        patch.object(ingest, "_get_man_content", AsyncMock(return_value="NAME ls")),
        patch.object(ingest, "_get_man_page_description", AsyncMock(return_value="list")),
    ):
        total = asyncio.run(ingest.index_commands_in_batches(kb, [("ls", "1"), ("cat", "1")], _ctx("redis")))
    assert total == 1


def test_a_cancelled_wait_kills_and_reaps_the_man_child_then_propagates():
    import pytest

    process = _stub_process()
    process.returncode = None
    process.kill = MagicMock()
    process.communicate = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ingest._communicate(process, 5))
    process.kill.assert_called_once()
    process.wait.assert_awaited_once()
