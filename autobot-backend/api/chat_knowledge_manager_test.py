# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat-to-knowledge summary prompt must carry the conversation (#15630).

``summary_prompt`` was a plain triple-quoted string holding
``{json.dumps(messages, indent=2)}``. Without the ``f`` prefix that is six
literal tokens, so every knowledge-base entry compiled from a chat was
summarised from a prompt that said "Conversation:" and then showed the model
the source code of its own interpolation.

The ``f`` prefix landed in c2478b6c5a. What did not land is anything that would
notice it going away again: the guard that found this (#15589) checks for the
*syntax* of an unprefixed f-string, so it would pass a prompt that interpolates
correctly and still carries no conversation -- an empty ``messages`` list, a
filter that removed everything, a future refactor that renames the variable.
This asserts the consequence instead: the text handed to the model contains
what the user actually said.
"""

from types import SimpleNamespace
from typing import Any, Dict, List

from api.chat_knowledge_manager import ChatKnowledgeManager

_CHAT_ID = "chat-15630"

#: Distinctive enough that finding it in the prompt cannot be a coincidence.
_USER_LINE = "how do I rotate the deploy credentials"
_ASSISTANT_LINE = "run the rotation task and confirm the epoch advanced"

_MESSAGES = [
    {"role": "system", "content": "you are a helpful assistant"},
    {"role": "user", "content": _USER_LINE},
    {"role": "assistant", "content": _ASSISTANT_LINE},
]


class _RecordingLLM:
    """Captures the prompt handed to the model."""

    def __init__(self) -> None:
        self.prompts: List[str] = []

    async def chat(self, messages: List[Dict[str, Any]], **_kwargs: Any) -> SimpleNamespace:
        self.prompts.append(messages[0]["content"])
        return SimpleNamespace(content="a summary")


def _manager(messages: List[Dict[str, Any]]) -> tuple[ChatKnowledgeManager, _RecordingLLM]:
    """A manager wired to fakes, with everything after the LLM call stubbed out."""
    manager = object.__new__(ChatKnowledgeManager)
    llm = _RecordingLLM()
    manager.llm_interface = llm
    manager.chat_history_manager = SimpleNamespace(
        get_chat_history=lambda _chat_id: {"messages": messages}
    )
    manager.chat_contexts = {}
    manager.file_associations = {}
    manager.knowledge_base = _StubKnowledgeBase()
    return manager, llm


class _StubKnowledgeBase:
    """Accepts the compiled entry so the method can run to completion."""

    async def add_content(self, content: str, metadata: Dict[str, Any]) -> str:
        self.content = content
        self.metadata = metadata
        return "kb-15630"


async def _prompt_for(messages: List[Dict[str, Any]]) -> str:
    """The prompt the summariser handed the model, from a completed run.

    The real ``_build_compiled_knowledge_dict`` and ``_build_chat_kb_metadata``
    are left in place rather than stubbed: they read the same ``messages`` this
    test is about, so stubbing them would hide a regression that empties the
    conversation on its way to them.
    """
    manager, llm = _manager(messages)
    await manager.compile_chat_to_knowledge(_CHAT_ID)
    assert llm.prompts, "the summariser never called the model"
    return llm.prompts[0]


async def test_the_summary_prompt_contains_the_conversation() -> None:
    """The defect exactly: the model was shown the interpolation, not the chat."""
    prompt = await _prompt_for(_MESSAGES)

    assert _USER_LINE in prompt
    assert _ASSISTANT_LINE in prompt


async def test_the_prompt_never_ships_the_interpolation_as_literal_text() -> None:
    """Belt to the braces: the pre-fix string is unmistakable if it returns."""
    prompt = await _prompt_for(_MESSAGES)

    assert "json.dumps" not in prompt
    assert "{json.dumps(messages, indent=2)}" not in prompt


async def test_system_messages_are_excluded_by_default() -> None:
    """The filter is what makes "the conversation reached the model" non-trivial.

    A test that only checked for *some* content would pass on a prompt carrying
    the system preamble and nothing else, which is the emptier-than-it-looks
    case this issue is about.
    """
    prompt = await _prompt_for(_MESSAGES)

    assert "you are a helpful assistant" not in prompt
    assert _USER_LINE in prompt
