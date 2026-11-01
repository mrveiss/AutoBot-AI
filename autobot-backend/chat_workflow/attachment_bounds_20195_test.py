# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Review fixes for #20195: the resume verdict, bounds by content, a bounded extractor, one read per turn.

* ``/chats/{id}/resume`` runs the STRICT check itself and REPLACES the verdict the paused turn checkpointed.
* The zip-bomb check goes by the file's content, so a misnamed archive is still bounded.
* A crafted archive that breaks the check is a notice, never the turn's failure.
* Extraction runs in a bounded pool whose slots outlive a timed-out thread; a full pool refuses, never queues.
* A file is extracted once per turn, and that text never reaches graph state.
"""

# flake8: noqa: F811 -- fixtures imported from the sibling test module are redefined as test arguments

from __future__ import annotations

import asyncio
import io
import threading
import time
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.ai_lines import VERIFIED_ATTACHMENT_ACCESS_KEY
from chat_workflow import attachment_context, attachment_extract, attachment_guards, limits
from chat_workflow.attachment_context_20195_test import _ALICE, _BASE, _FACT, _codes, _seed, _turn, world  # noqa: F401


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    attachment_extract.clear_text_cache()
    monkeypatch.setattr("chat_workflow.attachment_floor.chat_used_attachment", AsyncMock(return_value=False))
    monkeypatch.setattr("chat_workflow.approval_baseline.fetch_slm_policy_json", AsyncMock(return_value=None))
    yield
    attachment_extract.clear_text_cache()


def _bomb() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "A" * 200_000)  # tiny on disk, large declared
    return buffer.getvalue()


# --- 1. resume ------------------------------------------------------------------------------------------------


class _Graph:
    def __init__(self, context):
        self.context = context

    async def aget_state(self, config):
        assert config == {"configurable": {"thread_id": "chat-1"}}
        return SimpleNamespace(values={"context": self.context})


def test_resume_replaces_the_checkpointed_verdict_with_the_resumers_own():
    checkpointed = {"attachments": ["f"], VERIFIED_ATTACHMENT_ACCESS_KEY: True, "verified_user_id": "alice"}
    graph = _Graph(checkpointed)
    refused = asyncio.run(attachment_context.resume_context(graph, "chat-1", False))
    assert VERIFIED_ATTACHMENT_ACCESS_KEY not in refused["context"]
    assert refused["context"]["attachments"] == ["f"] and refused["context"]["verified_user_id"] == "alice"
    assert checkpointed[VERIFIED_ATTACHMENT_ACCESS_KEY] is True  # the snapshot itself is not mutated
    granted = asyncio.run(attachment_context.resume_context(_Graph({"attachments": ["f"]}), "chat-1", True))
    assert granted["context"][VERIFIED_ATTACHMENT_ACCESS_KEY] is True


def test_a_resumer_who_fails_strict_gets_no_file_text_even_though_the_paused_turn_had_a_verdict(world):
    file_id = _seed(world, _ALICE, "report.txt", _FACT.encode())
    paused = {"attachments": [file_id], "verified_user_id": "alice", VERIFIED_ATTACHMENT_ACCESS_KEY: True}
    world.chat.get_or_create_session = AsyncMock(return_value=SimpleNamespace(session_id=_ALICE, metadata={}))
    ctx = SimpleNamespace(session_id=_ALICE, context=paused, selected_model="m", initial_prompt=_BASE)
    assert _FACT in asyncio.run(attachment_context.attachment_prompt(world.chat, ctx))
    update = asyncio.run(attachment_context.resume_context(_Graph(paused), "chat-1", False))
    ctx.context = update["context"]  # what the resumed graph state now holds
    assert asyncio.run(attachment_context.attachment_prompt(world.chat, ctx)) == _BASE


def test_the_resume_route_runs_the_strict_check_and_hands_the_verdict_to_the_graph():
    from api.chat import resume_chat_graph

    seen = {}

    def _stream(manager, chat_id, decision, request_id, attachment_access=False):
        seen["access"] = attachment_access
        return iter(())

    for verdict in (False, True):
        with (
            patch("api.chat.get_chat_workflow_manager", AsyncMock(return_value=MagicMock())),
            patch("api.chat_streaming.attachments_allowed", AsyncMock(return_value=verdict)) as strict,
            patch("api.chat._stream_graph_resume", side_effect=_stream),
            patch("chat_workflow.attachment_context.checkpoint_carries_floor", AsyncMock(return_value=False)),
            patch("chat_workflow.attachment_floor.chat_used_attachment", AsyncMock(return_value=False)),
        ):
            asyncio.run(
                resume_chat_graph(
                    chat_id="chat-1",
                    current_user={"username": "bob"},
                    request_data={"approved": True},
                    request=MagicMock(),
                    ownership={},
                )
            )
        strict.assert_awaited_once()
        assert seen["access"] is verdict


def test_the_manager_overwrites_the_verdict_in_the_command_it_resumes_with():
    from chat_workflow.manager import ChatWorkflowManager

    captured = {}

    class _G(_Graph):
        pass

    def _stream(_manager, graph, session_id, command):
        captured["command"] = command

        async def _gen():
            if False:
                yield None

        return _gen()

    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
    graph = _G({"attachments": ["f"], VERIFIED_ATTACHMENT_ACCESS_KEY: True})
    with (
        patch("chat_workflow.graph.get_compiled_graph", AsyncMock(return_value=graph)),
        patch("chat_workflow.manager.stream_graph_turn", side_effect=_stream),
    ):

        async def _run():
            async for _ in manager.resume_graph("chat-1", {"approved": True}):
                pass

        asyncio.run(_run())
    command = captured["command"]
    assert command.resume == {"approved": True}
    assert VERIFIED_ATTACHMENT_ACCESS_KEY not in command.update["context"]  # default is fail closed


# --- 2. bounds by content -------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["bomb.pdf", "bomb.doc", "bomb.ppt", "bomb.bin", "bomb"])
def test_a_zip_bomb_under_a_non_zip_name_is_refused_before_the_parser_opens_it(world, monkeypatch, name):
    monkeypatch.setattr(limits, "ATTACHMENT_MAX_UNCOMPRESSED_BYTES", 10_000)
    file_id = _seed(world, _ALICE, name, _bomb(), mime="application/octet-stream")
    from utils.document_parser import DocumentParser

    async def _never(*_a, **_k):
        raise AssertionError("the parser must not open a bomb")

    monkeypatch.setattr(DocumentParser, "extract_text", _never)
    params, prompt = _turn(world, [file_id])
    assert prompt == _BASE and _codes(params) == ["over_budget"]


def test_refusal_code_judges_content_not_the_name(tmp_path, monkeypatch):
    monkeypatch.setattr(limits, "ATTACHMENT_MAX_UNCOMPRESSED_BYTES", 10_000)
    bomb = tmp_path / "x.pdf"
    bomb.write_bytes(_bomb())
    plain = tmp_path / "y.docx"
    plain.write_bytes(b"not an archive")
    assert attachment_guards.refusal_code(bomb) == "over_budget"
    assert attachment_guards.refusal_code(plain) is None


# --- 4. a crafted archive is a notice -------------------------------------------------------------------------


@pytest.mark.parametrize("error", [NotImplementedError("compression"), ValueError("bad"), OverflowError("big")])
def test_a_crafted_archive_that_breaks_the_check_is_a_notice_not_a_failed_turn(world, monkeypatch, error):
    file_id = _seed(world, _ALICE, "odd.docx", _bomb(), mime="application/octet-stream")

    def _boom(*_a, **_k):
        raise error

    monkeypatch.setattr(attachment_guards.zipfile, "ZipFile", _boom)
    params, prompt = _turn(world, [file_id])
    assert prompt == _BASE and _codes(params) == ["unreadable"]


# --- 3. bounded extractor, one read per turn -----------------------------------------------------------------


def test_a_full_pool_refuses_instead_of_queueing_and_a_timed_out_thread_keeps_its_slot():
    pool = attachment_extract.BoundedExecutor(1)
    release = threading.Event()

    async def _scenario():
        loop = asyncio.get_running_loop()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(loop.run_in_executor(pool, release.wait), timeout=0.1)
        # the turn gave up waiting, but the thread is still running: the slot is NOT free
        with pytest.raises(attachment_extract.ExtractorBusy):
            pool.submit(lambda: None)
        release.set()
        for _ in range(100):  # the done-callback frees the slot when the thread really ends
            try:
                return pool.submit(lambda: "ran").result(timeout=2)
            except attachment_extract.ExtractorBusy:
                await asyncio.sleep(0.02)
        raise AssertionError("the slot was never released")

    try:
        assert asyncio.run(_scenario()) == "ran"
    finally:
        release.set()
        pool.shutdown(wait=True)


def test_a_saturated_pool_gives_the_user_a_notice_and_the_turn_goes_on(world, monkeypatch):
    pool = attachment_extract.BoundedExecutor(1)
    release = threading.Event()
    pool.submit(release.wait)  # occupies the only slot
    monkeypatch.setattr(attachment_extract, "_executor", pool)
    file_id = _seed(world, _ALICE, "slides.pptx", b"PK-not-really", mime="application/octet-stream")
    try:
        params, prompt = _turn(world, [file_id])
        assert prompt == _BASE and _codes(params) == ["unreadable"]
    finally:
        release.set()
        pool.shutdown(wait=True)


def test_a_file_whose_extraction_failed_is_not_retried_on_every_llm_iteration(world, monkeypatch):
    calls = []

    async def _timeout(coro):
        coro.close()
        calls.append(1)
        raise asyncio.TimeoutError

    monkeypatch.setattr(attachment_guards, "within_extract_deadline", _timeout)
    file_id = _seed(world, _ALICE, "slow.pptx", b"PK-not-really", mime="application/octet-stream")
    for _ in range(3):  # three LLM iterations of one turn
        params, prompt = _turn(world, [file_id])
        assert prompt == _BASE and _codes(params) == ["unreadable"]
    assert len(calls) == 1  # the skip code was remembered; a busy pool (transient) is the one case not remembered


def test_the_pool_is_sized_from_the_configured_limit(monkeypatch):
    monkeypatch.setattr(attachment_extract, "_executor", None)
    monkeypatch.setattr(limits, "ATTACHMENT_EXTRACT_WORKERS", 3)
    try:
        assert attachment_extract.extract_executor()._max_workers == 3
    finally:
        attachment_extract._executor.shutdown(wait=False)
        monkeypatch.setattr(attachment_extract, "_executor", None)


def test_a_file_is_extracted_once_across_a_turns_iterations(world, monkeypatch):
    file_id = _seed(world, _ALICE, "deck.docx", b"stand-in bytes", mime="application/octet-stream")
    from utils.document_parser import DocumentParser

    calls = []

    async def _extract(self, path, mime=None, executor=None):
        calls.append(executor)
        return f"slide text {_FACT}", {}

    monkeypatch.setattr(DocumentParser, "extract_text", _extract)
    first = _turn(world, [file_id])[1]
    second = _turn(world, [file_id])[1]  # the next LLM iteration of the same turn
    assert _FACT in first and _FACT in second
    assert len(calls) == 1 and isinstance(calls[0], attachment_extract.BoundedExecutor)


def test_the_cache_never_outlives_the_file_lookup_or_its_ttl(world, monkeypatch):
    file_id = _seed(world, _ALICE, "report.txt", _FACT.encode())
    assert _FACT in _turn(world, [file_id])[1]
    assert asyncio.run(world.files.delete_session_files(_ALICE)) == 1
    assert _FACT not in _turn(world, [file_id])[1]  # the lookup runs first, so a cached text is not served

    key = ("s", "f", "/p", 1, 1)
    attachment_extract.remember_text(key, "x" * (limits.ATTACHMENT_MAX_CHARS_PER_FILE + 50))
    assert len(attachment_extract.cached_text(key)) == limits.ATTACHMENT_MAX_CHARS_PER_FILE + 1
    real = time.monotonic()
    monkeypatch.setattr(attachment_extract.time, "monotonic", lambda: real + limits.ATTACHMENT_TEXT_CACHE_SECONDS + 1)
    assert attachment_extract.cached_text(key) is None


def test_the_cache_holds_a_bounded_number_of_files(monkeypatch):
    monkeypatch.setattr(limits, "ATTACHMENT_TEXT_CACHE_MAX_ENTRIES", 2)
    for n in range(3):
        attachment_extract.remember_text(("s", str(n), "/p", 1, 1), f"t{n}")
    assert attachment_extract.cached_text(("s", "0", "/p", 1, 1)) is None
    assert attachment_extract.cached_text(("s", "2", "/p", 1, 1)) == "t2"
