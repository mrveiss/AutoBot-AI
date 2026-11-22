# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/knowledge/provenance_test.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17527's provenance contract: five intake legs, five dialects, one accessor.

Each case below is the metadata a leg **actually writes**, copied from the leg
rather than invented, so this file is the executable record of what "source
identifiable" means per path today. If a leg's vocabulary changes, the case for it
fails and the change is visible instead of silent.

What this file does **not** prove, stated because the criterion it serves is a
round trip and a contract test is not one: nothing here ingests a document, and
nothing here retrieves one. It pins that each leg's metadata resolves to an
origin, and that the LLC surface exposes it. Whether a document added through a
running system comes back with its origin intact needs a host, and the procedure
for that is `docs/developer/KB_ROUND_TRIP.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from knowledge.provenance import (
    CONNECTOR,
    MANUAL,
    TRANSCRIPT,
    UPLOAD,
    WATCH_FOLDER,
    document_origin,
    document_origins,
)

# ---------------------------------------------------------------------------
# The five dialects, copied from the writers.
# ---------------------------------------------------------------------------

UPLOAD_META = {  # api/knowledge.py:1292
    "title": "Spec v2",
    "source": "spec-v2.pdf",
    "category": "specs",
    "tags": ["spec"],
    "type": "file",
    "filename": "spec-v2.pdf",
}
TRANSCRIPT_META = {  # transcriber/knowledge/kb_push.py (#17536)
    "source_type": "transcript",
    "source": "recording:41",
    "recording_id": 41,
    "recording_filename": "standup.wav",
    "speaker": "Alice",
}
WATCH_META = {  # services/kb_watch_ingest.py (#17531)
    "source": "watch_folder",
    "category": "uploads",
    "tags": ["manual", "watch_folder:f1"],
    "folder_id": "f1",
    "filename": "report.txt",
    "file_path": "/watched/report.txt",
    "collection": "notes",
}
CONNECTOR_META = {  # knowledge/connectors/base.py:596
    "source_type": "connector",
    "source_connector_id": "c-7",
    "connector_type": "confluence",
    "source_id": "page-912",
    "content_type": "text/html",
    "verification_status": "unverified",
}
MANUAL_META = {  # api/knowledge.py:563
    "title": "Deployment note",
    "source": "ops runbook",
    "category": "ops",
    "access_level": "internal",
    "visibility": "company",
}

ALL_LEGS = [
    pytest.param(UPLOAD_META, UPLOAD, "file:spec-v2.pdf", id="upload"),
    pytest.param(TRANSCRIPT_META, TRANSCRIPT, "recording:41", id="transcriber"),
    pytest.param(WATCH_META, WATCH_FOLDER, "file:/watched/report.txt", id="watch-folder"),
    pytest.param(CONNECTOR_META, CONNECTOR, "connector:confluence:page-912", id="connector"),
    pytest.param(MANUAL_META, MANUAL, "ops runbook", id="manual"),
]


@pytest.mark.parametrize("metadata,leg,reference", ALL_LEGS)
def test_every_intake_leg_resolves_to_an_origin(metadata, leg, reference):
    """The criterion, per leg: a stored fact can say where it came from."""
    origin = document_origin(metadata)

    assert origin.leg == leg
    assert origin.reference == reference
    assert origin.known


def test_the_connector_leg_writes_no_source_key_at_all():
    """Why the accessor exists rather than every consumer reading `source`.

    This is the leg that breaks the obvious approach: `metadata["source"]` is a
    KeyError here, so a consumer reading it either crashes or silently gets None
    for an item whose origin is fully recorded under different keys.
    """
    assert "source" not in CONNECTOR_META
    assert document_origin(CONNECTOR_META).known


def test_source_means_something_different_in_each_leg_that_sets_it():
    """The finding this contract records, in one assertion.

    A filename, a URN, a literal category and free text — four meanings of one
    key. Any consumer reading `source` directly is reading a different thing per
    leg without being told which.
    """
    values = {
        "upload": UPLOAD_META["source"],
        "transcriber": TRANSCRIPT_META["source"],
        "watch-folder": WATCH_META["source"],
        "manual": MANUAL_META["source"],
    }

    assert values["upload"].endswith(".pdf")
    assert values["transcriber"].startswith("recording:")
    assert values["watch-folder"] == "watch_folder", "a category, not an identifier"
    assert len(set(values.values())) == 4


# ---------------------------------------------------------------------------
# Not knowing is an answer, and a distinct one from having no source.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("metadata", [None, {}, {"category": "ops"}], ids=["none", "empty", "no-provenance"])
def test_an_unrecognised_shape_yields_no_guess(metadata):
    """The defect class this module exists to avoid.

    A provenance field holding a plausible value from another question is what
    `source: "ecl_pipeline"` and the LLC's tenancy-filled `sources` both are. So
    an unrecognised shape resolves to nothing, and `known` is False.
    """
    origin = document_origin(metadata)

    assert origin.leg is None
    assert origin.reference is None
    assert origin.known is False


def test_a_recognised_leg_with_nothing_identifying_is_not_a_guess_either():
    """`leg` and `reference` are separate on purpose.

    A connector fact with no ids is recognisably a connector fact whose item
    cannot be named. Reporting the leg while admitting no reference is the honest
    pair; inventing `connector:` with nothing after it would not be.
    """
    origin = document_origin({"source_type": "connector"})

    assert origin.leg == CONNECTOR
    assert origin.reference is None
    assert origin.known is False


# ---------------------------------------------------------------------------
# The list form, as retrieval surfaces it.
# ---------------------------------------------------------------------------


def test_origins_are_distinct_and_in_first_seen_order():
    chunks = [
        {"metadata": TRANSCRIPT_META},
        {"metadata": UPLOAD_META},
        {"metadata": TRANSCRIPT_META},
    ]

    assert document_origins(chunks) == ["recording:41", "file:spec-v2.pdf"]


def test_an_unattributable_chunk_is_omitted_rather_than_placeheld():
    """A list of origins containing an invented entry is the defect, not the fix."""
    chunks = [{"metadata": UPLOAD_META}, {"metadata": {}}, {"metadata": None}]

    assert document_origins(chunks) == ["file:spec-v2.pdf"]


def test_chunks_without_metadata_do_not_raise():
    """Retrieval shapes vary by surface; a missing key is not an error here."""
    assert document_origins([{}, {"content": "x"}]) == []


# ---------------------------------------------------------------------------
# The graph leg, which is not fixed yet (#17588, e5).
#
# This is a characterisation test: it pins the DEFECT, so that the fix breaks it
# and forces its own deletion. Marking it xfail would leave the fix silent; this
# way the day the loader stops writing a constant, this test fails and whoever
# lands #17588 removes it. Read the source as text rather than importing the
# loader, which pulls the pipeline's dependency chain.
# ---------------------------------------------------------------------------

_LOADER = Path(__file__).resolve().parent / "pipeline" / "loaders" / "redis_graph_loader.py"


def test_the_graph_loader_still_writes_a_constant_source():
    """DELETE THIS TEST when #17588 lands — its failure is that fix arriving.

    `PipelineContext.document_id` already reaches this loader and is unused, so a
    graph node's `source` says which pipeline wrote it rather than which document
    it came from. That is the same defect as the LLC `sources` field: a plausible
    value under a provenance-shaped name.
    """
    source = _LOADER.read_text(encoding="utf-8")

    assert '"source": "ecl_pipeline"' in source, (
        "the graph loader no longer writes a constant source — #17588 has landed, "
        "so delete this characterisation test and assert the document attribution instead"
    )


def test_the_document_id_the_loader_could_use_exists():
    """The other half of #17588: attribution is occupied, not missing."""
    base = Path(__file__).resolve().parent / "pipeline" / "base.py"

    assert "self.document_id" in base.read_text(encoding="utf-8")
