# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17278: the stable system text leads; the per-turn memory block follows it."""

import os.path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_workflow.llm_handler import LLMHandlerMixin
from chat_workflow.tiered_context_sources import append_memory_context


def _handler():
    handler = LLMHandlerMixin.__new__(LLMHandlerMixin)
    handler.knowledge_service = None
    handler._get_personality_preamble = MagicMock(return_value="PERSONA\n\n---\n\n")
    handler._get_selected_model = MagicMock(return_value="m")
    handler._get_ollama_endpoint_for_model = MagicMock(return_value="http://t")
    handler._build_conversation_context = MagicMock(return_value="")
    handler._build_full_prompt = MagicMock(return_value="p")
    handler._discover_ollama_from_slm = AsyncMock(return_value=None)
    return handler


def _session():
    session = MagicMock()
    session.session_id = "s"
    session.conversation_history = []
    session.metadata = {}
    return session


def _hook(seen):
    async def hook(prompt, _session):
        if seen is not None:
            seen.append(prompt)
        return prompt

    return hook


async def _system_prompt(handler, story: str, seen: list | None = None) -> str:
    gen = MagicMock()
    gen.generate = AsyncMock(return_value=story)
    with (
        patch("chat_history.layers.TIERED_CONTEXT_ENABLED", False),
        patch("memory.essential_story.EssentialStoryGenerator", return_value=gen),
        patch("chat_workflow.llm_handler._emit_system_prompt_ready", new=_hook(seen)),
        patch("chat_workflow.llm_handler._emit_before_prompt_build", new_callable=AsyncMock),
        patch("chat_workflow.llm_handler._emit_after_prompt_build", new_callable=AsyncMock, return_value="p"),
        patch("chat_workflow.llm_handler._emit_full_prompt_ready", new_callable=AsyncMock, return_value="p"),
    ):
        params = await handler._prepare_llm_request_params(_session(), "hi", use_knowledge=False, language="en")
    return params["system_prompt"]


@pytest.mark.asyncio
async def test_two_turns_with_different_memory_share_the_whole_stable_prefix():
    handler = _handler()
    stable = handler._get_system_prompt(language="en", company_id=None)
    one = await _system_prompt(handler, "STORY ranked one way")
    two = await _system_prompt(handler, "STORY re-ranked after a day")

    shared = len(os.path.commonprefix([one, two]))
    assert shared >= len(stable) > 0
    assert one.startswith(stable) and two.startswith(stable)
    assert one != two and one.endswith("STORY ranked one way")


@pytest.mark.asyncio
async def test_hook_sees_the_stable_text_only_and_the_final_prompt_starts_with_it():
    handler, seen = _handler(), []
    final = await _system_prompt(handler, "MEMORY BLOCK", seen)
    stable = handler._get_system_prompt(language="en", company_id=None)
    assert seen == [stable]  # the real call order: hook first, memory appended afterwards
    assert final == stable + "\n\nMEMORY BLOCK"


@pytest.mark.asyncio
async def test_memory_block_follows_the_stable_text():
    gen = MagicMock()
    gen.generate = AsyncMock(return_value="MEMORY")
    with (
        patch("chat_history.layers.TIERED_CONTEXT_ENABLED", False),
        patch("memory.essential_story.EssentialStoryGenerator", return_value=gen),
    ):
        out = await append_memory_context("STABLE", _session(), "hi", "m")
    assert out == "STABLE\n\nMEMORY"
