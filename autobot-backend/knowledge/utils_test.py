# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ChromaDB metadata sanitisation must not lose structure it accepts (#14257)."""

from __future__ import annotations

import json

import pytest

from knowledge.utils import sanitize_metadata_for_chromadb

# The shape that exposed this: page provenance from a PDF upload (#13894/#14239).
_PAGE_SPANS = [
    {"page": 1, "start": 0, "end": 13},
    {"page": 2, "start": 15, "end": 27},
    {"page": 3, "start": 29, "end": 34},
]


def test_a_list_of_dicts_round_trips():
    """The reproduction. Before this fix the value came back as a Python repr
    joined with ', ' — which json.loads rejects, and which no split can undo
    because the commas inside each element are indistinguishable from the
    commas between them."""
    sanitized = sanitize_metadata_for_chromadb({"page_spans": _PAGE_SPANS})

    assert json.loads(sanitized["page_spans"]) == _PAGE_SPANS


def test_the_offsets_survive_individually():
    """Asserting the whole list is equal would still pass if every span were
    reordered or merged; this pins the field a consumer actually indexes with."""
    sanitized = sanitize_metadata_for_chromadb({"page_spans": _PAGE_SPANS})
    decoded = json.loads(sanitized["page_spans"])

    assert [span["start"] for span in decoded] == [0, 15, 29]
    assert decoded[1]["page"] == 2


@pytest.mark.parametrize(
    "value,expected",
    [
        ([1, 2, 3], "1, 2, 3"),
        (["a", "b"], "a, b"),
        ((1.5, 2.5), "1.5, 2.5"),
        ([], ""),
        ([None], "None"),
    ],
)
def test_a_list_of_scalars_keeps_its_historical_form(value, expected):
    """Metadata already stored uses the comma-joined form. Switching every
    sequence to JSON would round-trip beautifully and make every existing
    document unreadable."""
    assert sanitize_metadata_for_chromadb({"k": value})["k"] == expected


def test_one_structured_element_is_enough_to_switch_encoding():
    """A list that is mostly scalars is still unrecoverable if any element is
    structured, so the decision is per-list, not per-element."""
    sanitized = sanitize_metadata_for_chromadb({"k": [1, {"a": 2}, 3]})

    assert json.loads(sanitized["k"]) == [1, {"a": 2}, 3]


def test_a_nested_list_is_structured_too():
    assert json.loads(sanitize_metadata_for_chromadb({"k": [[1, 2], [3]]})["k"]) == [[1, 2], [3]]


def test_a_bare_dict_is_unchanged():
    """This branch was already correct — the bug was that a list OF dicts did
    not reach it."""
    assert json.loads(sanitize_metadata_for_chromadb({"k": {"a": 1}})["k"]) == {"a": 1}


@pytest.mark.parametrize("value", ["text", 7, 1.5, None])
def test_scalars_pass_through_untouched(value):
    assert sanitize_metadata_for_chromadb({"k": value})["k"] == value


def test_an_unserialisable_sequence_says_so_instead_of_pretending(caplog):
    """`str()` is the only option left for a value JSON cannot take. Falling
    back silently is the defect this issue is about, one case further along."""

    class NotSerialisable:
        def __repr__(self) -> str:
            return "<opaque>"

    with caplog.at_level("WARNING"):
        sanitized = sanitize_metadata_for_chromadb({"k": [NotSerialisable()]})

    assert sanitized["k"] == "[<opaque>]"
    assert any("k" in record.message or "k" in str(record.args) for record in caplog.records)


def test_empty_metadata_is_still_empty():
    assert sanitize_metadata_for_chromadb({}) == {}
    assert sanitize_metadata_for_chromadb(None) == {}
