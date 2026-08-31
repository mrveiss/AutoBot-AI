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

from chat_history.message_schema import as_llm_messages, llm_role, message_role, message_text


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

    def test_an_empty_list_content_DOES_fall_back(self):
        """Reversed deliberately in #14335 — this test previously asserted the
        opposite.

        The old reasoning was that an empty part-list is a well-formed *"this
        message has no text parts"*, so nothing needs looking up elsewhere. That
        holds for a single-schema reader and not for this one: the whole premise
        here is that either key may carry the body, so an empty `content` has
        told us nothing while `text` may still hold everything.

        It also failed in the direction that costs data. Every consumer reads an
        empty result as *absent*: distillation drops the message (the #14259
        defect this module exists to fix), the overflow tracker under-counts
        retained tokens and delays compaction, and the chat path sends an empty
        turn. `context_overflow._message_text` always fell through here, which
        is the divergence #14335 consolidated — toward the forgiving one.
        """
        assert message_text({"content": [], "text": "fallback"}) == "fallback"

    def test_an_empty_list_with_no_other_key_is_still_empty(self):
        """Falling through must not invent content when there is none to find."""
        assert message_text({"content": []}) == ""

    def test_an_image_only_part_list_falls_back_to_the_caption(self):
        """The case that actually occurs, and the one the #14335 reasoning
        originally failed to name.

        A bare `content: []` is barely a real shape. A message carrying an image
        part and a caption under the other key is one a provider can genuinely
        emit — and it behaves the same way here only because the fallback is
        decided on the *resolved* body rather than the raw value. Testing the
        raw value, as the reverted version did, would return "" here and lose
        the caption.
        """
        msg = {"content": [{"type": "image_url", "image_url": {"url": "data:..."}}], "text": "the caption"}

        assert message_text(msg) == "the caption"

    def test_a_mixed_list_keeps_its_text_and_does_NOT_fall_back(self):
        """The boundary on the other side: once a list yields any text, that is
        the body, and a populated `text` must not override it."""
        msg = {
            "content": [{"type": "image_url", "image_url": {}}, {"type": "text", "text": "real body"}],
            "text": "stale",
        }

        assert message_text(msg) == "real body"

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


class TestTheRoleAProviderWillAccept:
    """`llm_role` is the clamped answer; `message_role` is the faithful one.

    A chat session is not written only by the chat turn. Terminal integration,
    the agent terminal and the workflow state machine persist into the *same*
    session under speakers of their own, and forwarding those verbatim builds a
    request the provider rejects — failing the whole turn, where before it
    merely mislabelled it.
    """

    @pytest.mark.parametrize("speaker", ["terminal", "agent_terminal", "main-backend"])
    def test_a_speaker_that_is_not_a_conversational_role_collapses_to_the_caller(self, speaker):
        assert llm_role({"sender": speaker, "text": "$ ls"}) == "user"

    @pytest.mark.parametrize("speaker", ["terminal", "agent_terminal", "main-backend"])
    def test_message_role_still_answers_faithfully_for_those(self, speaker):
        """The clamp belongs to the LLM reader, not to the schema itself —
        anything reporting on a session still needs the real speaker."""
        assert message_role({"sender": speaker, "text": "$ ls"}) == speaker

    def test_the_two_conversational_roles_survive(self):
        assert llm_role({"sender": "assistant", "text": "done"}) == "assistant"
        assert llm_role({"sender": "user", "text": "do it"}) == "user"

    def test_a_stored_system_notice_does_not_reach_the_model_as_a_system_turn(self):
        """Approval notices are persisted under that speaker. An adapter that
        separates the system role out hoists it into the system prompt, so
        passing it through would replace the real instructions with 'Command
        approved'."""
        assert llm_role({"sender": "system", "text": "Command approved"}) == "user"

    def test_a_message_with_no_speaker_at_all_gets_the_caller(self):
        assert llm_role({"text": "orphaned"}) == "user"


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
