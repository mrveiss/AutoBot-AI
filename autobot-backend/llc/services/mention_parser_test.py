# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``@mention`` parsing (#19582)."""

import pytest

from llc.services import mention_parser
from llc.services.mention_parser import new_mentions, parse_mentions


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("@ceo-acme please look", ["ceo-acme"]),
        ("cc @a.b_c-d, and @e.", ["a.b_c-d", "e"]),  # trailing punctuation is not the slug
        ("(@bot)", ["bot"]),
        ("@bot @bot @other", ["bot", "other"]),  # distinct, first-seen order
        ("mail ops@acme.io now", []),  # an e-mail address is not a mention
        ("@@bot", []),
        ("@ alone", []),
        ("", []),
        (None, []),
    ],
)
def test_parse_mentions(text, expected) -> None:  # noqa: ANN001
    assert parse_mentions(text) == expected


def test_the_number_of_mentions_is_capped(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(mention_parser, "MAX_MENTIONS_PER_TEXT", 2)
    assert parse_mentions("@a @b @c") == ["a", "b"]


def test_an_edit_only_wakes_the_newly_mentioned() -> None:
    assert new_mentions("@a and now @b", "@a") == ["b"]
    assert new_mentions("@a", None) == ["a"]
    assert new_mentions(None, "@a") == []
