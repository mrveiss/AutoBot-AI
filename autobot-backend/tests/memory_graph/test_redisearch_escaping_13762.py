# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""RediSearch query building treats caller strings as data (#13762).

``_build_redis_search_query`` interpolated every value into the query with no
escaping, so caller punctuation was read as query syntax. The MCP surface
reaches this without the Pydantic bounds the REST surface applies, which is why
the escaping belongs here rather than depending on each caller validating.

Two escapers, deliberately: a TAG value must match exactly, so separators are
escaped there; free text is split on separators, so escaping them there would
turn every multi-word search into one phrase token that matches nothing.
"""

import pytest

from autobot_shared.security.input_sanitizer import escape_redisearch, escape_redisearch_tag


@pytest.fixture
def build():
    """The query builder, bound to a stand-in so no Redis connection is needed."""
    from autobot_memory_graph.queries import QueryOperationsMixin  # noqa: PLC0415

    return QueryOperationsMixin._build_redis_search_query.__get__(object())


# ------------------------------------------------------- free-text query


def test_a_crafted_field_selector_cannot_escape_the_term(build):
    """`@type:{...}` in the query must not override the entity_type filter."""
    rendered = build("@type:{secret}")

    assert "@type:{secret}" not in rendered
    assert rendered == "(\\@type:\\{secret\\})"


@pytest.mark.parametrize("operator", ["|", "*", "~", "%", "(", ")", "[", "]", "@", "{", "}"])
def test_every_structural_operator_is_neutralised(build, operator):
    rendered = build(f"safe{operator}term")
    assert f"safe\\{operator}term" in rendered


def test_a_bare_wildcard_inside_a_term_cannot_force_a_full_scan(build):
    assert build("a*") == "(a\\*)"


# --------------------------------------- free text must keep working


def test_multi_word_search_is_unchanged(build):
    """Escaping whitespace would make this one phrase token and match nothing."""
    assert build("redis config timeout") == "(redis config timeout)"


@pytest.mark.parametrize("query", ["Host: 10.0.0.5", "real-time factor", "severity:high", "what?", "a, b; c"])
def test_ordinary_punctuation_is_left_to_the_tokenizer(build, query):
    """These characters split terms; escaping them changes what matches."""
    assert build(query) == f"({query})"


def test_no_filters_is_match_all(build):
    assert build("*") == "*"
    assert build("") == "*"


# ------------------------------------------------------------ TAG filters


def test_entity_type_cannot_close_its_own_tag_and_add_a_filter(build):
    rendered = build("*", entity_type="person}|@status:{leaked")

    assert "person}|@status:{leaked" not in rendered
    assert rendered == "@type:{person\\}\\|\\@status\\:\\{leaked}"


def test_status_filter_is_escaped(build):
    assert build("*", status="ok|admin") == "@status:{ok\\|admin}"


def test_tag_filter_escapes_each_tag_but_keeps_the_or_separator(build):
    rendered = build("*", tags=["red team", "blue|team"])

    # One real separator between the two tags …
    assert rendered == "@tags:{red\\ team|blue\\|team}"
    # … and the '|' inside a value is escaped, so it cannot add a third tag.
    assert rendered.count("|") == 2


def test_tag_values_escape_whitespace_but_free_text_does_not():
    """The two escapers differ on exactly one thing, and that is the point."""
    assert escape_redisearch_tag("red team") == "red\\ team"
    assert escape_redisearch("red team") == "red team"


def test_escape_redisearch_leaves_ordinary_text_alone():
    assert escape_redisearch("redis config") == "redis config"


def test_filters_and_query_compose(build):
    assert build("timeout", entity_type="incident") == "@type:{incident} (timeout)"
