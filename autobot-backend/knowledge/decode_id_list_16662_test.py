# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ID lists read back from ChromaDB metadata are real lists, not strings (#16662)."""

import pytest

from knowledge.utils import decode_id_list, sanitize_metadata_for_chromadb


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (None, []),
        ("", []),
        ([], []),
        (["bob", "alice"], ["bob", "alice"]),
        (("bob",), ["bob"]),
        ("bobby, alice", ["bobby", "alice"]),
        ("bobby,alice", ["bobby", "alice"]),
        ('["bob", "alice"]', ["bob", "alice"]),
        ("[not json", ["[not json"]),
    ],
)
def test_every_stored_shape_decodes_to_a_list(stored, expected):
    assert decode_id_list(stored) == expected


def test_it_round_trips_what_the_chromadb_sanitiser_writes():
    written = sanitize_metadata_for_chromadb({"shared_with": ["bobby", "alice"]})["shared_with"]
    assert isinstance(written, str), "precondition: ChromaDB stores the list as a string"
    assert decode_id_list(written) == ["bobby", "alice"]
