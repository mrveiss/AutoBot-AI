# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit table for the one serving predicate (#18820, #18829).

Each row is one fact and the verdict it must get. Rejected never serves; an
unparseable validity bound fails closed; unverified and pending_review keep
today's behaviour (served) until #18077 decides otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest

from knowledge import serving
from knowledge.serving import (
    SERVING_TRUST_WHERE,
    ServingVerdict,
    is_servable,
    servable,
    servable_response,
    serving_verdict,
)

_NOW = datetime.now(tz=timezone.utc)
_PAST = (_NOW - timedelta(days=1)).isoformat()
_FUTURE = (_NOW + timedelta(days=1)).isoformat()

_TABLE = [
    ({}, ServingVerdict.VALID),
    ({"verification_status": "verified"}, ServingVerdict.VALID),
    ({"verification_status": "rejected"}, ServingVerdict.REJECTED),
    # #18077 open decision: served today, pinned so a flip is a visible change.
    ({"verification_status": "unverified"}, ServingVerdict.VALID),
    ({"verification_status": "pending_review"}, ServingVerdict.VALID),
    # A state outside the enum (e.g. a connector mode name, #18077) is not withheld.
    ({"verification_status": "collaborative"}, ServingVerdict.VALID),
    # Case and padding do not launder a rejected state; an absent or empty one is a legacy fact.
    ({"verification_status": "REJECTED"}, ServingVerdict.REJECTED),
    ({"verification_status": " Rejected\n"}, ServingVerdict.REJECTED),
    ({"verification_status": ""}, ServingVerdict.VALID),
    ({"verification_status": None}, ServingVerdict.VALID),
    # Present but not text: unreadable as a trust state, so withheld (fail closed, like a bad bound).
    ({"verification_status": 1}, ServingVerdict.UNPARSEABLE),
    ({"verification_status": ["rejected"]}, ServingVerdict.UNPARSEABLE),
    ({"verification_status": False}, ServingVerdict.UNPARSEABLE),
    ({"valid_to": None}, ServingVerdict.VALID),
    ({"valid_to": ""}, ServingVerdict.VALID),
    ({"valid_to": _FUTURE}, ServingVerdict.VALID),
    ({"valid_to": _PAST}, ServingVerdict.EXPIRED),
    ({"valid_to": "garbage"}, ServingVerdict.UNPARSEABLE),
    ({"valid_to": 1700000000}, ServingVerdict.UNPARSEABLE),
    ({"valid_until": _PAST}, ServingVerdict.EXPIRED),
    ({"valid_until": "garbage"}, ServingVerdict.UNPARSEABLE),
    ({"valid_from": _PAST}, ServingVerdict.VALID),
    ({"valid_from": _FUTURE}, ServingVerdict.NOT_YET_VALID),
    ({"valid_from": "garbage"}, ServingVerdict.UNPARSEABLE),
    ({"valid_from": _PAST, "valid_to": _FUTURE}, ServingVerdict.VALID),
    ({"is_active": True}, ServingVerdict.VALID),
    ({"is_active": False}, ServingVerdict.INVALIDATED),
    ({"is_active": "False"}, ServingVerdict.INVALIDATED),
    ({"verification_status": "rejected", "valid_to": _FUTURE}, ServingVerdict.REJECTED),
    ({"verification_status": "verified", "valid_to": "garbage"}, ServingVerdict.UNPARSEABLE),
]


def _stable_id(metadata: Dict[str, Any]) -> str:
    """A test id without the run's clock, so every xdist worker collects the same ids."""
    return repr(metadata).replace(_PAST, "PAST").replace(_FUTURE, "FUTURE")


@pytest.mark.parametrize(("metadata", "expected"), _TABLE, ids=[_stable_id(row[0]) for row in _TABLE])
def test_the_unit_table(metadata: Dict[str, Any], expected: ServingVerdict) -> None:
    """Every row, in the search-result shape (``metadata`` nested)."""
    hit = {"content": "c", "score": 0.9, "metadata": metadata}
    assert serving_verdict(hit) is expected
    assert is_servable(hit) is (expected is ServingVerdict.VALID)


def test_z_and_offset_suffixes_compare_as_instants_not_strings() -> None:
    """A string compare orders ``Z`` after ``.ffffff+00:00`` (#18829); parsed instants do not."""
    entity = {"metadata": {"valid_to": "2026-02-01T00:00:00Z"}}
    assert serving_verdict(entity, as_of="2026-02-01T00:00:00.500000+00:00") is ServingVerdict.EXPIRED


def test_as_of_judges_validity_at_that_instant_with_an_inclusive_end() -> None:
    entity = {"metadata": {"valid_from": "2026-01-01T00:00:00+00:00", "valid_to": "2026-02-01T00:00:00Z"}}
    assert is_servable(entity, as_of="2026-01-15T00:00:00+00:00") is True
    assert is_servable(entity, as_of="2026-02-01T00:00:00+00:00") is True
    assert is_servable(entity, as_of="2026-02-02T00:00:00+00:00") is False
    assert is_servable(entity, as_of="2025-12-31T00:00:00+00:00") is False


def test_an_unparseable_as_of_raises_rather_than_guessing() -> None:
    with pytest.raises(ValueError):
        serving_verdict({}, as_of="garbage")
    with pytest.raises(ValueError):
        serving_verdict({}, as_of="")


@dataclass
class _Ranked:
    """``RankedResult``-shaped: the fields live in a ``metadata`` attribute."""

    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _Atomic:
    """``AtomicFact``-shaped: top-level datetime attributes, no metadata."""

    valid_from: datetime
    valid_until: datetime | None = None
    is_active: bool = True


class _Row:
    """ORM-row-shaped: ``metadata`` is SQLAlchemy's MetaData, the JSON is ``metadata_json``."""

    metadata = object()

    def __init__(self, metadata_json: Dict[str, Any]) -> None:
        self.metadata_json = metadata_json


@pytest.mark.parametrize(
    ("rejected", "kept"),
    [
        (_Ranked("r", {"verification_status": "rejected"}), _Ranked("k", {"verification_status": "verified"})),
        ({"metadata": {"verification_status": "rejected"}}, {"metadata": {}}),
        (_Row({"verification_status": "rejected"}), _Row({})),
        (_Atomic(valid_from=_NOW - timedelta(days=2), is_active=False), _Atomic(valid_from=_NOW - timedelta(days=2))),
        (_Atomic(valid_from=_NOW - timedelta(days=2), valid_until=_NOW - timedelta(days=1)), _Atomic(_NOW)),
    ],
    ids=["ranked-result", "dict", "orm-row", "atomic-invalidated", "atomic-expired"],
)
def test_every_store_shape_gets_the_same_verdict(rejected: Any, kept: Any) -> None:
    """One predicate for dict, row and dataclass shapes -- never a per-shape fork."""
    assert servable([rejected, kept]) == [kept]


def test_a_naive_datetime_is_taken_as_utc() -> None:
    naive_past = (_NOW - timedelta(days=1)).replace(tzinfo=None)
    assert serving_verdict(_Atomic(valid_from=naive_past, valid_until=naive_past)) is ServingVerdict.EXPIRED


def test_the_18077_seam_is_one_flag_and_it_currently_serves() -> None:
    """#18077 is undecided: unverified/pending_review serve; only rejected is withheld."""
    assert serving.UNDECIDED_TRUST_STATES_SERVE is True
    assert serving.UNDECIDED_TRUST_STATES == frozenset({"unverified", "pending_review"})
    assert serving.WITHHELD_TRUST_STATES == frozenset({"rejected"})
    assert SERVING_TRUST_WHERE == {"verification_status": {"$ne": "rejected"}}


def test_the_seam_when_flipped_withholds_both_states_store_side_too() -> None:
    """What flipping #18077's flag would produce, computed by the same helper."""
    states = frozenset({"rejected"}) | serving.UNDECIDED_TRUST_STATES
    assert serving._trust_where(states) == {
        "verification_status": {"$nin": ["pending_review", "rejected", "unverified"]}
    }


def test_servable_response_filters_a_list() -> None:
    hits = [{"metadata": {"verification_status": "rejected"}}, {"metadata": {}}]
    assert servable_response(hits) == [hits[1]]


def test_servable_response_filters_a_dict_its_clusters_and_the_counts() -> None:
    bad = {"metadata": {"verification_status": "rejected"}}
    good = {"metadata": {}}
    response = {
        "success": True,
        "results": [bad, good],
        "total_count": 2,
        "unclustered_count": 2,
        "clusters": [{"topic": "t", "results": [bad, good], "result_count": 2}],
    }
    out = servable_response(response)
    assert out["results"] == [good]
    assert out["total_count"] == 1
    assert out["unclustered_count"] == 1
    assert out["clusters"] == [{"topic": "t", "results": [good], "result_count": 1}]
    assert response["results"] == [bad, good], "the input is not mutated"


def test_servable_response_leaves_an_error_dict_alone() -> None:
    error = {"success": False, "results": None, "error": "Search failed"}
    assert servable_response(error) == error
    assert servable_response(None) is None


def test_servable_tolerates_none_and_generators() -> None:
    assert servable(None) == []
    assert servable(item for item in [{"metadata": {"valid_to": "garbage"}}, {}]) == [{}]
