# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`word_tokens` equals both previous copies on a corpus (#18093)."""

import re

import pytest

from autobot_shared.text_tokens import word_token_list, word_tokens

_CORPUS = [
    "",
    " ",
    "___",
    "analyze this PDF document",
    "Analyze_this PDF-document!",
    "snake_case and kebab-case",
    "Zürich Café 日本語 テキスト",
    "٣٤٥ digits 2² ½",
    "a..b//c\\d\te\nf",
    "UPPER lower MiXeD 123",
    "x" * 300,
    "tab\x00nul\x1besc",
]


def _old_prepared_facts(text):
    return frozenset(t for t in re.split(r"[\W_]+", text.lower()) if t)


def _old_fingerprint(text):
    return re.findall(r"\b\w+\b", text.lower())


def _old_skill_router(text):
    return {t for t in re.split(r"[\W_]+", text.lower()) if t}


@pytest.mark.parametrize("text", _CORPUS)
def test_equals_both_previous_copies(text):
    assert word_tokens(text) == _old_prepared_facts(text) == _old_skill_router(text)
    assert isinstance(word_tokens(text), frozenset)


def test_both_call_sites_use_the_shared_helper():
    from prepared_facts import _tok
    from skills.builtin.skill_router import _tokenize

    assert _tok is word_tokens
    assert _tokenize("Analyze_this PDF") == {"analyze", "this", "pdf"}
    assert isinstance(_tokenize("a b"), set) and not isinstance(_tokenize("a b"), frozenset)


@pytest.mark.parametrize("text", _CORPUS)
def test_fingerprint_behaviour_is_the_underscore_keeping_list(text):
    """Ordered, duplicates kept, `_` stays inside a token -- byte-identical to the old findall."""
    assert word_token_list(text, split_underscore=False) == _old_fingerprint(text)
    assert word_token_list(text) == [t for t in re.split(r"[\W_]+", text.lower()) if t]


def test_the_two_behaviours_differ_only_by_underscore_and_set_view():
    assert word_token_list("a_b a_b") == ["a", "b", "a", "b"]
    assert word_token_list("a_b a_b", split_underscore=False) == ["a_b", "a_b"]
    assert word_tokens("a_b a_b", split_underscore=False) == frozenset({"a_b"})


def test_fingerprint_tokenize_is_a_delegate_not_a_second_implementation():
    from agent_loop.fingerprint import tokenize

    for text in _CORPUS:
        assert tokenize(text) == _old_fingerprint(text)


def test_lowercase_false_is_the_caller_has_already_lowered_mode():
    """`markdown_reference_system` counted `\\b\\w+\\b` runs of the ORIGINAL text; the 3 other
    callers lowered first. `lowercase=False` keeps each byte-identical, including the case
    where lowering splits a run ('İa' -> 'i' + U+0307 + 'a')."""
    for text in _CORPUS + ["İa", "ǅ_x"]:
        assert word_token_list(text, split_underscore=False, lowercase=False) == re.findall(r"\b\w+\b", text)
        low = text.lower()
        assert word_token_list(low, split_underscore=False, lowercase=False) == re.findall(r"\b\w+\b", low)
    assert len(word_token_list("İa", split_underscore=False, lowercase=False)) == 1
    assert len(word_token_list("İa", split_underscore=False)) == 2


def test_migrated_findall_sites_no_longer_hold_the_regex():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for rel in (
        "autobot-backend/knowledge/search_quality.py",
        "autobot-backend/markdown_reference_system.py",
        "autobot-backend/llm_shared/tiered_routing/complexity_scorer.py",
        "autobot-backend/services/skill_management/skill_extractor.py",
        "autobot-backend/agent_loop/fingerprint.py",
    ):
        src = (root / rel).read_text(encoding="utf-8")
        assert "word_token" in src
        assert not any(isinstance(n, ast.Constant) and n.value == r"\b\w+\b" for n in ast.walk(ast.parse(src))), rel
