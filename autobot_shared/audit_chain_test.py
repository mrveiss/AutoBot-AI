# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pure half of the audit hash chain (#17219): serialization, hash, MAC, verifier."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from autobot_shared import audit_chain as chain

KEY = b"k" * 32
OTHER_KEY = b"o" * 32
WHEN = datetime(2026, 11, 22, 10, 30, 15, 123456, tzinfo=timezone.utc)


def _row(seq: int, **over) -> SimpleNamespace:
    fields = dict(
        id=uuid.UUID(int=seq),
        chain_seq=seq,
        created_at=WHEN + timedelta(seconds=seq),
        category="security",
        actor="alice",
        action="auth.login",
        resource_type="user",
        resource_ref="r",
        resource_id=None,
        outcome="success",
        details={"b": 1, "a": [1.5, "é"]},
        ip_address=None,
        user_agent=None,
        session_id=None,
        org_ref=None,
        prev_hash=None,
        row_hash=None,
        row_mac=None,
    )
    fields.update(over)
    return SimpleNamespace(**fields)


def _chain(count: int, key: bytes = KEY) -> tuple[list[SimpleNamespace], str]:
    genesis = chain.genesis_hash(7, WHEN)
    rows, prev = [], genesis
    for seq in range(1, count + 1):
        row = _row(seq, prev_hash=prev)
        row.row_hash, row.row_mac = chain.seal_row(row, prev, key)
        rows.append(row)
        prev = row.row_hash
    return rows, genesis


def test_serialization_is_stable_under_key_order_and_carries_the_version_byte() -> None:
    first = chain.canonical_bytes({"b": 1, "a": {"y": 2, "x": 3}})
    second = chain.canonical_bytes({"a": {"x": 3, "y": 2}, "b": 1})
    assert first == second
    assert first[0] == chain.FORMAT_VERSION and first[1:].startswith(b'{"a":')


def test_the_hash_covers_the_text_identity_not_the_foreign_keys() -> None:
    row = _row(1, user_id=uuid.uuid4(), org_id=uuid.uuid4())
    assert "user_id" not in chain.covered_values(row) and "org_id" not in chain.covered_values(row)
    assert chain.seal_row(row, "p", KEY) == chain.seal_row(_row(1, user_id=None, org_id=None), "p", KEY)


@pytest.mark.parametrize("value", [1.0, 0.1, 1e-7, 2**63, -3, "é", "☃", None, True, [], {}])
def test_details_values_serialize_the_same_after_a_round_trip(value) -> None:
    import json

    details = {"v": value, "nested": {"v": [value]}}
    assert chain.canonical_bytes({"d": details}) == chain.canonical_bytes({"d": json.loads(json.dumps(details))})


def test_naive_and_aware_times_hash_alike_as_utc() -> None:
    aware = _row(1, created_at=WHEN)
    naive = _row(1, created_at=WHEN.replace(tzinfo=None))
    assert chain.seal_row(aware, "p", KEY) == chain.seal_row(naive, "p", KEY)


def test_a_clean_chain_verifies() -> None:
    rows, genesis = _chain(5)
    assert chain.verify_rows(rows, KEY, genesis=genesis) == []


def test_a_changed_field_is_reported_at_its_sequence_only() -> None:
    rows, genesis = _chain(5)
    rows[2].action = "auth.logout"
    found = chain.verify_rows(rows, KEY, genesis=genesis)
    assert [(f.kind, f.seq) for f in found] == [(chain.MODIFIED, 3)]


def test_a_removed_row_is_a_gap_at_the_missing_sequence() -> None:
    rows, genesis = _chain(5)
    del rows[2]
    kinds = {(f.kind, f.seq) for f in chain.verify_rows(rows, KEY, genesis=genesis)}
    assert (chain.GAP, 3) in kinds and (chain.REORDERED, 4) in kinds


def test_a_changed_prev_hash_is_a_reordered_row() -> None:
    rows, genesis = _chain(4)
    rows[2].prev_hash = rows[0].row_hash
    kinds = {(f.kind, f.seq) for f in chain.verify_rows(rows, KEY, genesis=genesis)}
    assert (chain.REORDERED, 3) in kinds and (chain.MODIFIED, 3) in kinds


def test_two_swapped_rows_are_reported() -> None:
    rows, genesis = _chain(4)
    rows[1], rows[2] = rows[2], rows[1]
    assert chain.verify_rows(rows, KEY, genesis=genesis)


def test_a_chain_recomputed_without_the_key_fails_the_mac_not_the_hash() -> None:
    forged, genesis = _chain(4, key=OTHER_KEY)
    found = chain.verify_rows(forged, KEY, genesis=genesis)
    assert {f.kind for f in found} == {chain.MAC_INVALID}
    assert [f.seq for f in found] == [1, 2, 3, 4]


def test_a_wrong_genesis_breaks_the_first_link() -> None:
    rows, _ = _chain(2)
    found = chain.verify_rows(rows, KEY, genesis=chain.genesis_hash(8, WHEN))
    assert [(f.kind, f.seq) for f in found] == [(chain.REORDERED, 1)]


def test_the_genesis_hash_binds_the_pre_chain_count() -> None:
    assert chain.genesis_hash(1, WHEN) != chain.genesis_hash(2, WHEN)
    assert chain.genesis_hash(0, None) == chain.genesis_hash(0, None)


def test_the_version_byte_is_part_of_what_is_hashed(monkeypatch) -> None:
    row = _row(1)
    before = chain.seal_row(row, "p", KEY)
    monkeypatch.setattr(chain, "FORMAT_VERSION", chain.FORMAT_VERSION + 1)
    assert chain.seal_row(row, "p", KEY) != before


def test_key_id_names_a_key_without_revealing_it() -> None:
    assert chain.key_id(KEY) != chain.key_id(OTHER_KEY)
    assert KEY.hex() not in chain.key_id(KEY) and len(chain.key_id(KEY)) == 16


@pytest.mark.parametrize("field", ["prev_hash", "row_hash", "row_mac"])
@pytest.mark.parametrize("bad", ["é" * 64, "A" * 64, "abc", "", None, "g" * 64])
def test_a_malformed_stored_hash_is_reported_as_modified_and_never_crashes(field: str, bad) -> None:
    rows, genesis = _chain(3)
    setattr(rows[1], field, bad)
    found = chain.verify_rows(rows, KEY, genesis=genesis)
    assert (chain.MODIFIED, 2) in {(f.kind, f.seq) for f in found}


def test_digest_format_and_comparison_are_safe_for_non_ascii() -> None:
    assert chain.is_digest("a" * 64) and not chain.is_digest("é" * 64) and not chain.is_digest(None)
    assert chain.same_digest("a" * 64, "a" * 64) and not chain.same_digest("é", "e")


def test_details_hash_the_way_postgresql_returns_them() -> None:
    """``1e+22`` comes back from JSONB as the integer 10**22; ``1.0`` and ``1e-07`` come back unchanged."""
    assert chain.jsonb_form({"a": [1e22, 1.5e300, 1.0, 1e-07, 5, "x"]}) == {
        "a": [10**22, int("15" + "0" * 299), 1.0, 1e-07, 5, "x"]
    }
    assert chain.canonical_bytes({"d": chain.jsonb_form({"v": 1e22})}) == chain.canonical_bytes({"d": {"v": 10**22}})
