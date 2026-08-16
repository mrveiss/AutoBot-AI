# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reading a chat message whichever schema it arrived in (#14259).

Skill distillation read `role`/`content` and filtered on `if msg.get("content")`.
The writer stores `sender`/`text`. So every stored conversation collapsed to an
empty list, was reported as distilled, and had the cursor advanced past it —
#12809's pipeline had never extracted a skill from a real conversation.

The decisive fixture rule here: **messages come from the real writer**, never a
hand-written dict. A hand-written `role`/`content` fixture is precisely what hid
this — the test and the code agreed with each other about a shape the writer
never produces. Same failure as #13686, where L2 read `description` while
entities carry `observations`.
"""

import pytest

from chat_history.message_schema import as_llm_messages, message_role, message_text


def _stored(sender: str, text: str) -> dict:
    """A message in the shape `_build_message_dict` actually writes."""
    from chat_history.messages import MessagesMixin

    return MessagesMixin._build_message_dict(
        None,
        sender=sender,
        text=text,
        message_type="chat",
        raw_data={},
        tool_markers=None,
    )


class TestTheStoredShapeIsReadable:
    """The case that was broken."""

    def test_a_message_from_the_real_writer_yields_its_text(self):
        stored = _stored("user", "deploy the service")

        assert "content" not in stored, "precondition: the writer stores `text`, not `content`"
        assert message_text(stored) == "deploy the service"
        assert message_role(stored) == "user"

    def test_a_stored_conversation_is_not_empty(self):
        """The exact collapse: four real messages, previously zero."""
        conversation = [
            _stored("user", "deploy the service"),
            _stored("assistant", "running code-sync"),
            _stored("user", "now restart it"),
            _stored("assistant", "done"),
        ]

        assert len(as_llm_messages(conversation)) == 4

    def test_the_old_comprehension_would_have_dropped_them_all(self):
        """Pins WHY it failed, so the fix cannot be undone by 'simplifying' it."""
        conversation = [_stored("user", "hello"), _stored("assistant", "hi")]

        old = [m for m in conversation if m.get("content")]

        assert old == [], "precondition: the old filter matched nothing"
        assert len(as_llm_messages(conversation)) == 2


class TestTheApiShapeStillWorks:
    """Both schemas are live; fixing one must not break the other."""

    def test_role_and_content_are_read(self):
        api = {"role": "assistant", "content": "the answer"}

        assert message_role(api) == "assistant"
        assert message_text(api) == "the answer"

    def test_role_wins_when_both_are_present(self):
        assert message_role({"role": "assistant", "sender": "user"}) == "assistant"

    def test_content_wins_when_both_are_present(self):
        assert message_text({"content": "api", "text": "stored"}) == "api"

    def test_an_empty_content_falls_back_to_text(self):
        """The case that makes `is None or == ""` necessary rather than tidy —
        a bare `content or text` gets this right too, so it is the *next* test
        that pins why the narrower check was chosen."""
        assert message_text({"content": "", "text": "real"}) == "real"

    def test_an_empty_list_content_does_NOT_fall_back(self):
        """Pins the deliberate narrowing against a bare `or`.

        An empty multimodal list is a well-formed answer — *this message has no
        text parts* — so there is nothing to look for in `text`. A bare
        `content or text` would fall back here and invent content.
        """
        assert message_text({"content": [], "text": "fallback"}) == ""

    @pytest.mark.parametrize("invalid", [0, False, {"a": 1}], ids=["zero", "false", "dict"])
    def test_an_invalid_content_type_is_treated_as_absent(self, invalid):
        """Neither `str()`-ing it nor trusting it.

        `str(value)` would put the literal "0" / "False" / "{'a': 1}" in front
        of the model. A content field that is not a str or a part-list is not
        content, so the other key is read instead.
        """
        assert message_text({"content": invalid, "text": "fallback"}) == "fallback"

    @pytest.mark.parametrize("invalid", [0, False, 42])
    def test_an_invalid_type_in_BOTH_keys_yields_empty(self, invalid):
        assert message_text({"content": invalid, "text": invalid}) == ""

    def test_a_present_but_null_sender_still_gets_the_default(self):
        """`msg.get("sender", "unknown")` returns None when the key is present
        and null — the default only applies to an absent key. The or-chain
        degrades that to the default, which is what callers expect."""
        assert message_role({"role": None, "sender": None}) == "unknown"


class TestMultimodalContent:
    """`message_text` carries #14065's guard verbatim, not a re-derivation."""

    def test_text_parts_are_joined(self):
        msg = {"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}

        assert message_text(msg) == "a b"

    def test_a_part_with_null_text_is_skipped_not_stringified(self):
        """A shape providers genuinely emit. `str(None)` would put the literal
        "None" in front of the model, and `" ".join` on it raised a TypeError
        that 500'd the live chat path (#14065)."""
        msg = {"role": "user", "content": [{"type": "text", "text": None}, {"type": "text", "text": "real"}]}

        assert message_text(msg) == "real"

    def test_non_text_parts_are_ignored(self):
        msg = {"role": "user", "content": [{"type": "image_url", "image_url": {}}, {"type": "text", "text": "caption"}]}

        assert message_text(msg) == "caption"


class TestMalformedHistoryIsData:
    """Malformed history is data, not a programming error — the same stance
    `context_overflow` already takes."""

    @pytest.mark.parametrize("junk", [None, "a string", 42, []])
    def test_non_dict_entries_are_skipped(self, junk):
        assert as_llm_messages([junk, _stored("user", "real")]) == [{"role": "user", "content": "real"}]

    def test_messages_with_no_text_are_dropped(self):
        assert as_llm_messages([_stored("user", ""), {"role": "user"}, {}]) == []

    def test_a_message_with_neither_key_gets_the_default_role(self):
        assert message_role({}) == "unknown"
