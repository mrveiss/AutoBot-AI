#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One hyphen-slug rule, and the two details the three forks disagreed on (#18093).

Three sites implemented this independently. In both places they differed, the MINORITY
was right, so the shared rule takes the minority behaviour each time — those two cases
are the first tests here.
"""

import pytest

from autobot_shared.slug import url_slug


def test_truncation_never_leaves_a_trailing_hyphen() -> None:
    """Only `llc/models/company.py` stripped a second time, after truncating.

    `okf_adapter` and `organization_service` did `.strip("-")` and then `[:cap]`, so a
    cut landing mid-run emitted a trailing hyphen. Asserted with a cap that lands
    exactly on a separator.
    """
    assert url_slug("alpha beta gamma", max_length=10) == "alpha-beta"
    assert url_slug("alpha beta gamma", max_length=11) == "alpha-beta"
    assert not url_slug("alpha beta gamma", max_length=11).endswith("-")
    # The pre-consolidation behaviour, as a control.
    naive = "alpha-beta-gamma"[:11]
    assert naive == "alpha-beta-", "control: strip-then-truncate leaves the hyphen"


def test_unicode_is_transliterated_not_treated_as_a_separator() -> None:
    """Only `okf_adapter` NFKD-folded first.

    Without the fold a non-ASCII letter is simply not in `[a-z0-9]`, so it becomes a
    separator and splits the word: "Zürich" -> "z-rich".
    """
    assert url_slug("Zürich") == "zurich"
    assert url_slug("Zürich", fold_unicode=False) == "z-rich"
    assert url_slug("Café Münster") == "cafe-munster"
    # Accents strip and the LETTERS survive -- my first draft of the empty-result test
    # asserted "éè" -> "" and was wrong about its own fixture, not about the code.
    assert url_slug("éè") == "ee"
    # An em dash carries no letter, so it is a separator and nothing survives.
    assert url_slug("——") == ""


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hello, World!", "hello-world"),
        ("already-a-slug", "already-a-slug"),
        ("  leading and trailing  ", "leading-and-trailing"),
        ("multiple   spaces", "multiple-spaces"),
        ("under_scores", "under-scores"),
        ("CamelCaseName", "camelcasename"),
        ("a...b___c---d", "a-b-c-d"),
        ("2026 Q1 Report", "2026-q1-report"),
        ("---edges---", "edges"),
    ],
)
def test_ordinary_slugs(text: str, expected: str) -> None:
    assert url_slug(text) == expected


@pytest.mark.parametrize("text", ["", "!!!", "   ", "---", "***", "——"])
def test_nothing_survivable_gives_an_empty_string(text: str) -> None:
    """Empty is returned, not decided.

    The three callers disagree about what an empty slug means — `okf_adapter` falls back
    to "concept", `llc/models/company` raises, `organization_service` returns it. Baking
    any one of those in would have forced a behaviour change on the other two.
    """
    assert url_slug(text) == ""


def test_the_result_matches_the_contract_the_callers_declare() -> None:
    """`llc/models/company` documents `^[a-z0-9-]+$`; okf_adapter `[a-z0-9][a-z0-9-]*`."""
    import re

    contract = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
    for text in ["Hello, World!", "Zürich", "2026 Q1 Report", "a...b___c---d", "x"]:
        slug = url_slug(text)
        assert contract.match(slug), f"{text!r} -> {slug!r} violates the slug contract"


def test_max_length_is_respected_exactly() -> None:
    long = "a" * 300
    assert len(url_slug(long, max_length=80)) == 80
    assert len(url_slug(long, max_length=100)) == 100


def test_the_underscore_slugify_is_a_different_contract_and_is_left_alone() -> None:
    """`agent_loop/text_utils.slugify` collapses to `_`, not `-`.

    Same word, different output contract — it keeps `\\w` and separates with underscores,
    so flattening it would change identifiers it has already produced. Asserted here so
    a later consolidation pass sees the decision rather than rediscovering it.
    """
    assert url_slug("hello world") == "hello-world"
    assert "_" not in url_slug("hello world")

    # Assert the other side of the boundary directly. Without this the test named a
    # contract it never called, so a change to `slugify` could not fail it — and the
    # whole reason this file exists is that `url_slug` was first written under that
    # helper's name and collided with it.
    from agent_loop.text_utils import slugify

    assert slugify("hello world") == "hello_world"
    assert "-" not in slugify("hello world")
