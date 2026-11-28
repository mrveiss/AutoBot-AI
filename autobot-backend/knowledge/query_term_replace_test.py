# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the shared whole-word replacement helper and its two callers (#21525).

Hermetic: the helper is pure and QueryExpander() needs no network or Redis.
"""

import pytest

from knowledge.query_term_replace import match_case, replace_whole_word
from knowledge.search_quality import QueryExpander


@pytest.mark.parametrize(
    ("matched", "expected"),
    [("install", "setup"), ("Install", "Setup"), ("INSTALL", "SETUP"), ("I", "Setup")],
)
def test_match_case(matched, expected):
    assert match_case("setup", matched) == expected


def test_replaces_every_whole_word_in_any_case_and_keeps_the_rest():
    out = replace_whole_word("Install it, then INSTALL more; install", "install", "setup")

    assert out == "Setup it, then SETUP more; setup"


def test_does_not_touch_longer_words():
    query = "installation and reinstall and installing"

    assert replace_whole_word(query, "install", "setup") == query


def test_hyphenated_and_special_characters_are_literal():
    assert replace_whole_word("use sign-in (now)", "sign-in", "login") == "use login (now)"
    assert replace_whole_word("a.b", "a.b", "x\\1") == "x\\1"


class TestQueryExpanderWholeWord:
    """QueryExpander.expand_query shares the helper (the #21525 sibling defect)."""

    def test_capitalised_word_yields_variants(self):
        queries = QueryExpander().expand_query("Login page")

        assert queries[0] == "Login page"
        assert "Signin page" in queries

    def test_upper_case_word_keeps_case(self):
        assert "SIGNIN PAGE" in QueryExpander().expand_query("LOGIN PAGE")

    def test_synonym_key_inside_longer_word_is_not_rewritten(self):
        # "ip" is a synonym key; it must not be rewritten inside "description".
        queries = QueryExpander().expand_query("description of ip")

        assert "description of address" in queries
        assert not any("descraddresstion" in q for q in queries)

    def test_reverse_synonym_is_whole_word(self):
        queries = QueryExpander().expand_query("Cert expiry")

        assert "Certificate expiry" in queries
