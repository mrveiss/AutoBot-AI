# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which ownerless facts are ingested documents (#16693): positive markers only.

Owner decision on #16693: documents only. Everything else nobody owns stays private,
including facts whose ``source_type`` is the ``manual_upload`` default every unmarked fact
gets, and transcripts.
"""

from __future__ import annotations

import pytest

from knowledge.ingestion_visibility import (
    BACKFILL_MARK,
    INGESTED_DOCUMENT_VISIBILITY,
    ingested_document_class,
    stamp_if_document,
    system_backfill_class,
)
from knowledge.ownership import VisibilityLevel

_DOCUMENTS = [
    ({"source_type": "connector", "source_connector_id": "c1"}, "connector"),
    ({"type": "file", "filename": "guide.pdf", "source": "guide.pdf"}, "file_upload"),
    ({"source": "manual_pages_population", "type": "manual_page"}, "man_page"),
    ({"source": "man_page_parser", "type": "man_page"}, "man_page"),
    ({"category": "system/manpages", "machine_id": "m1"}, "man_page"),
    ({"source": "autobot_docs_population", "type": "guide_documentation"}, "documentation"),
    ({"source": "system_commands_population", "type": "system_command"}, "system_commands"),
    ({"source": "project-documentation", "category": "user-guide"}, "documentation"),
    ({"source": "project-documentation", "category": "project-overview"}, "documentation"),
]

_NOT_DOCUMENTS = [
    {"source_type": "manual_upload"},  # the provenance default, carried by diaries and extraction too
    {"source_type": "chat", "category": "chat_knowledge"},
    {"category": "AGENT_DIARY", "source": "autobot_docs_population"},  # a diary's source is free text
    {"type": "atomic_facts", "source": "manual_pages_population"},  # extraction spreads caller metadata
    {"type": "audio_transcript", "source": "https://example.invalid/talk"},  # owner: transcripts stay private
    {"category": "system/manpages"},  # no machine it was synced from
    {"type": "file"},  # no filename
    {"source": ["autobot_docs_population"]},  # not a string
    {"source": "project-documentation", "category": "reports"},  # owner: repo reports stay private
    {"source": "project-documentation", "category": "security"},
    {"source": "project-documentation", "category": "source-code"},
    {"source": "project-documentation", "category": ["documentation"]},  # not a string
    {},
]

_CLAIMS = [
    {"owner_id": "u1"},
    {"user_id": "u1"},
    {"visibility": "private"},
    {"organization_id": "o1"},
    {"group_ids": ["g1"]},
    {"shared_with": ["u2"]},
    {"board_id": "b1"},
]


@pytest.mark.parametrize(("metadata", "kind"), _DOCUMENTS)
def test_each_ingestion_class_is_recognised_by_its_marker(metadata, kind):
    assert ingested_document_class(metadata) == kind
    assert system_backfill_class(metadata) == kind


@pytest.mark.parametrize("metadata", _NOT_DOCUMENTS)
def test_no_other_ownerless_fact_is_a_document(metadata):
    assert ingested_document_class(metadata) is None
    assert system_backfill_class(metadata) is None


@pytest.mark.parametrize("claim", _CLAIMS)
def test_a_claimed_fact_is_never_selected_or_stamped(claim):
    metadata = {"source_type": "connector", **claim}
    assert system_backfill_class(metadata) is None
    assert stamp_if_document(dict(metadata)) == metadata


def test_empty_scope_lists_are_not_a_claim():
    assert system_backfill_class({"source_type": "connector", "group_ids": [], "shared_with": []}) == "connector"


def test_an_unclaimed_document_is_stamped_system():
    assert stamp_if_document({"source_type": "connector"})["visibility"] == VisibilityLevel.SYSTEM


@pytest.mark.parametrize("metadata", _NOT_DOCUMENTS)
def test_anything_else_is_left_unstamped(metadata):
    assert "visibility" not in stamp_if_document(dict(metadata))


def test_what_is_written_is_the_system_visibility_level():
    assert INGESTED_DOCUMENT_VISIBILITY == VisibilityLevel.SYSTEM.value
    assert BACKFILL_MARK == {"visibility": VisibilityLevel.SYSTEM.value, "visibility_backfill": "16693"}
