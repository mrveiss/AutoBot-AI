# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Topic detection, context-prompt selection and non-exit context in ``intent_classifier``.

These capabilities were carried over from the retired ``chat_intent_detector`` (#21678).
"""

from unittest.mock import patch

import pytest

from intent_classifier import (
    GENERAL_TOPIC,
    NON_EXIT_CONTEXT_PHRASES,
    TOPIC_KEYWORDS,
    TOPIC_PROMPT_MAP,
    ConversationIntent,
    IntentClassifier,
    detect_topic,
    select_context_prompt,
)


@pytest.mark.parametrize(
    "message,expected",
    [
        ("How do I install AutoBot?", "installation"),
        ("getting started with the deployment", "installation"),
        ("What is the system design of the infrastructure?", "architecture"),
        ("the build crashed with a timeout error", "troubleshooting"),
        ("which curl endpoint streams over websocket", "api"),
        ("Hello", GENERAL_TOPIC),
        ("", GENERAL_TOPIC),
    ],
)
def test_detect_topic_keywords(message, expected):
    assert detect_topic(message) == expected


def test_highest_score_wins():
    assert detect_topic("install and setup and configure, but there was an error") == "installation"


def test_history_boosts_a_tie():
    history = [{"user": "q", "assistant": "a timeout is likely"}]
    assert detect_topic("error install", history) == "troubleshooting"


def test_history_alone_selects_topic():
    assert detect_topic("Hello", [{"assistant": "see the docs"}]) == "api"


def test_only_recent_history_counts():
    history = [{"assistant": "curl api"}, {"assistant": "hi"}, {"assistant": "hi"}]
    assert detect_topic("Hello", history) == GENERAL_TOPIC


@pytest.mark.parametrize("history", [None, []])
def test_empty_history_is_safe(history):
    assert detect_topic("Hello", history) == GENERAL_TOPIC


@pytest.mark.parametrize("topic", [GENERAL_TOPIC, "unknown"])
def test_base_prompt_returned_without_topic_prompt(topic):
    with patch("intent_classifier.get_prompt") as get:
        assert select_context_prompt(topic, "base") == "base"
    get.assert_not_called()


@pytest.mark.parametrize("topic", sorted(TOPIC_PROMPT_MAP))
def test_topic_prompt_is_appended(topic):
    with patch("intent_classifier.get_prompt", return_value="EXTRA") as get:
        result = select_context_prompt(topic, "base")
    get.assert_called_once_with(TOPIC_PROMPT_MAP[topic])
    assert result.startswith("base") and "EXTRA" in result and f"this {topic} conversation" in result


def test_prompt_load_failure_falls_back_to_base():
    with patch("intent_classifier.get_prompt", side_effect=KeyError("missing")):
        assert select_context_prompt("api", "base") == "base"


def test_every_topic_has_keywords_and_a_prompt():
    assert set(TOPIC_KEYWORDS) == set(TOPIC_PROMPT_MAP)
    assert all(TOPIC_KEYWORDS.values())


@pytest.mark.parametrize("phrase", sorted(NON_EXIT_CONTEXT_PHRASES))
def test_non_exit_context_phrase_is_not_an_exit(phrase):
    result = IntentClassifier().classify(phrase)
    assert result.intent != ConversationIntent.END
    assert result.signals["has_non_exit_context"] is True


def test_exit_word_naming_a_concept_continues():
    assert IntentClassifier().classify("exit code").intent == ConversationIntent.CONTINUE


@pytest.mark.parametrize("message", ["goodbye", "bye", "exit", "quit", "i'm done"])
def test_plain_exit_still_ends(message):
    assert IntentClassifier().classify(message).intent == ConversationIntent.END
