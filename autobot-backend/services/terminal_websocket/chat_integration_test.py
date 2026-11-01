# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pins the behaviour TerminalWebSocket delegates here (#18557)."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from services.terminal_websocket.chat_integration import TerminalChatIntegrator


def _integrator(tmp_path, conversation_id="conv"):
    return TerminalChatIntegrator(conversation_id, AsyncMock(), data_dir=tmp_path)


@pytest.mark.asyncio
async def test_a_saved_buffer_is_stripped_and_reset(tmp_path):
    chat = _integrator(tmp_path)
    await chat.buffer_output("\x1b[31mdone\x1b[0m\n")
    chat.chat_history_manager.add_message.assert_awaited_once_with(
        sender="terminal", text="done", message_type="terminal_output", session_id="conv"
    )
    assert chat._output_buffer == ""


@pytest.mark.asyncio
async def test_a_failed_save_keeps_the_buffer_for_the_next_attempt(tmp_path):
    chat = _integrator(tmp_path)
    chat.chat_history_manager.add_message.side_effect = RuntimeError("store down")
    saved_at = chat._last_output_save_time
    await chat.buffer_output("done\n")
    assert chat._output_buffer == "done\n"
    assert chat._last_output_save_time == saved_at


@pytest.mark.asyncio
async def test_a_prompt_is_dropped_without_saving(tmp_path):
    chat = _integrator(tmp_path)
    await chat.buffer_output("user@host:~$ \n")
    chat.chat_history_manager.add_message.assert_not_awaited()
    assert chat._output_buffer == ""


@pytest.mark.asyncio
async def test_flush_saves_what_is_left_and_clears_a_blank_buffer(tmp_path):
    chat = _integrator(tmp_path)
    chat._output_buffer = "tail"
    await chat.flush_buffer()
    assert chat.chat_history_manager.add_message.await_args.kwargs["text"] == "tail"
    assert chat._output_buffer == ""
    chat._output_buffer = "  \n"
    await chat.flush_buffer()
    chat.chat_history_manager.add_message.assert_awaited_once()
    assert chat._output_buffer == ""


@pytest.mark.asyncio
async def test_a_failed_flush_keeps_the_buffer(tmp_path):
    chat = _integrator(tmp_path)
    chat.chat_history_manager.add_message.side_effect = RuntimeError("store down")
    chat._output_buffer = "tail"
    await chat.flush_buffer()
    assert chat._output_buffer == "tail"


@pytest.mark.asyncio
async def test_transcript_appends_clean_text_under_the_data_dir(tmp_path):
    chat = _integrator(tmp_path)
    assert await chat.write_to_transcript("\x1b[31mone\x1b[0m\ntwo") is True
    assert await chat.write_to_transcript("three") is True
    written = await asyncio.to_thread((tmp_path / "conv_terminal_transcript.txt").read_text, encoding="utf-8")
    assert written.startswith("one\ntwo") and written.endswith("three")


@pytest.mark.asyncio
async def test_transcript_keeps_line_breaks_between_chunks(tmp_path):
    chat = _integrator(tmp_path)
    await chat.write_to_transcript("\x1b[31mls\x1b[0m\n")
    await chat.write_to_transcript("pwd\n")
    written = await asyncio.to_thread((tmp_path / "conv_terminal_transcript.txt").read_text, encoding="utf-8")
    assert written == "ls\npwd\n"


@pytest.mark.asyncio
async def test_transcript_writes_nothing_for_a_chunk_of_only_escapes(tmp_path):
    chat = _integrator(tmp_path)
    assert await chat.write_to_transcript("\x1b[31m\x1b[0m") is False
    assert not (tmp_path / "conv_terminal_transcript.txt").exists()


@pytest.mark.asyncio
async def test_transcript_drops_bracket_artifacts_from_a_pty_read(tmp_path):
    chat = _integrator(tmp_path)
    await chat.write_to_transcript("[?2004hls\n")
    written = await asyncio.to_thread((tmp_path / "conv_terminal_transcript.txt").read_text, encoding="utf-8")
    assert written == "ls\n"


@pytest.mark.asyncio
async def test_transcript_refuses_a_conversation_id_that_leaves_the_data_dir(tmp_path):
    chats = tmp_path / "chats"
    chats.mkdir()
    chat = _integrator(chats, conversation_id="../escaped")
    assert await chat.write_to_transcript("x") is False
    assert not (tmp_path / "escaped_terminal_transcript.txt").exists()


@pytest.mark.asyncio
async def test_no_conversation_means_no_transcript(tmp_path):
    chat = _integrator(tmp_path, conversation_id=None)
    assert await chat.write_to_transcript("x") is False
    assert list(tmp_path.iterdir()) == []
